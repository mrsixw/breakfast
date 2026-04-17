import json
import random
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import click
import requests
from tabulate import tabulate

from .api import (
    SECRET_GITHUB_TOKEN,
    GitHubRateLimitError,
    _fetch_pr_detail,
    get_api_stats,
    get_approval_summary,
    get_authenticated_user_login,
    get_check_status,
    get_github_prs,
    get_graphql_rate_limit,
)
from .cache import (
    parse_ttl,
    read_graphql_cache,
    read_pr_cache,
    write_graphql_cache,
    write_pr_cache,
)
from .config import (
    filter_pr_details,
    generate_default_config,
    load_config,
    update_config,
)
from .logger import configure as configure_logging
from .logger import logger
from .ui import (
    BREAKFAST_ITEMS,
    apply_seasonal_colour,
    click_colour_grade_number,
    format_approval_status,
    format_check_status,
    format_mergeable_status,
    format_pr_state,
    generate_terminal_url_anchor,
    render_pr_summary,
)
from .updater import check_for_update

# Columns dropped as last resort (least important first)
_DROPPABLE_COLUMNS = [
    "State",
    "Commits",
    "Files",
    "+/-",
    "Cmt",
    "Age",
    "Checks",
    "Apr",
    "Head Branch",
    "Base Branch",
]

_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;]*[a-zA-Z]|\]8;;.*?\x1b\\|\]8;;.*?\x07)")
_ANSI_LEADING_RE = re.compile(r"^(?:\x1b\[[0-9;]*[a-zA-Z])*")
_OSC8_FULL_RE = re.compile(
    r"^(?P<prefix>(?:\x1b\[[0-9;]*[a-zA-Z])*)"
    r"\x1b]8;;(?P<url>.*?)(?:\x1b\\|\x07)"
    r"(?P<text>.*?)"
    r"\x1b]8;;(?:\x1b\\|\x07)"
    r"(?P<suffix>(?:\x1b\[[0-9;]*[a-zA-Z])*)$"
)
_OSC8_ANY_RE = re.compile(
    r"\x1b]8;;(?P<url>.*?)(?:\x1b\\|\x07)(?P<text>.*?)\x1b]8;;(?:\x1b\\|\x07)"
)
_ANSI_RESET = "\x1b[0m"


def _strip_ansi(s):
    return _ANSI_RE.sub("", str(s))


def _osc8_to_markdown(s):
    """Convert OSC 8 hyperlinks and ANSI codes in *s* to Markdown link syntax."""
    result = _OSC8_ANY_RE.sub(
        lambda m: f"[{m.group('text')}]({m.group('url')})", str(s)
    )
    return _strip_ansi(result)


def _truncate_formatted_text(value, limit):
    """Truncate visible text while preserving ANSI and OSC 8 wrappers.

    Args:
        value: Cell value that may contain ANSI styling or OSC 8 hyperlinks.
        limit: Maximum visible character count, including the ellipsis.

    Returns:
        The truncated value with any existing formatting preserved.
    """
    plain = _strip_ansi(value)
    if len(plain) <= limit:
        return value

    truncated = plain[: limit - 1] + "…"
    osc_match = _OSC8_FULL_RE.match(str(value))
    if osc_match:
        return (
            osc_match.group("prefix")
            + generate_terminal_url_anchor(osc_match.group("url"), truncated)
            + osc_match.group("suffix")
        )

    if plain != value:
        return str(value).replace(plain, truncated, 1)
    return truncated


def _styled_hyperlink(url, styled_text):
    """Wrap a click.style'd string in an OSC 8 hyperlink.

    Tabulate's OSC 8 parser requires the link text to contain no escape
    sequences. This helper moves leading ANSI colour codes outside the OSC 8
    escape so tabulate measures column width correctly while the terminal
    still renders the text in colour.
    """
    plain = _strip_ansi(styled_text)
    prefix = _ANSI_LEADING_RE.match(styled_text).group()
    suffix = _ANSI_RESET if _ANSI_RESET in styled_text else ""
    return prefix + generate_terminal_url_anchor(url, plain) + suffix


def _table_width(rows):
    """Return visual table width via the border line (ANSI-stripped for accuracy)."""
    plain_rows = [{k: _strip_ansi(v) for k, v in row.items()} for row in rows]
    table_str = tabulate(
        plain_rows,
        headers="keys",
        showindex="always",
        tablefmt="outline",
        disable_numparse=True,
    )
    return len(table_str.splitlines()[0])


def _truncate_col(pr_data, key, terminal_width, min_len=8):
    """Shrink a text column to help the table fit within terminal_width.

    For PR Title, calculates the exact available space from overhead.
    For other columns (Repo, Author), trims by the current excess so that
    even when many other wide columns are present the truncation still fires.
    """
    if key not in pr_data[0]:
        return pr_data

    if key == "PR Title":
        # Exact calculation: measure overhead with a placeholder title
        overhead = _table_width([{**pr_data[0], key: "X" * min_len}]) - min_len
        limit = terminal_width - overhead
    else:
        # Excess-based: shrink the longest value by however much the table overflows
        excess = _table_width(pr_data) - terminal_width
        if excess <= 0:
            return pr_data
        current_max = max(len(_strip_ansi(row[key])) for row in pr_data)
        limit = max(current_max - excess, min_len)

    if limit < min_len:
        return pr_data
    return [
        {
            **row,
            key: _truncate_formatted_text(row[key], limit),
        }
        for row in pr_data
    ]


def _compress_styled(styled_text):
    """Compress styled text to its first visible word, preserving ANSI colour."""
    plain = _strip_ansi(styled_text)
    words = plain.split()
    if len(words) <= 1:
        return styled_text
    if len(words) >= 2 and re.fullmatch(r"\d+/\d+", words[1]):
        compressed = " ".join(words[:2])
    else:
        compressed = words[0]
    return styled_text.replace(plain, compressed, 1)


def _auto_fit(pr_data, terminal_width, explicit_max_title_length):
    """Progressively compress the table to fit within terminal_width."""
    if not pr_data:
        return pr_data

    def fits():
        return _table_width(pr_data) <= terminal_width

    # 1. Auto-truncate PR Title (skip if caller already applied an explicit limit)
    if explicit_max_title_length is None:
        pr_data = _truncate_col(pr_data, "PR Title", terminal_width, min_len=10)

    if fits():
        return pr_data

    # 2. Truncate Author
    pr_data = _truncate_col(pr_data, "Author", terminal_width, min_len=8)
    if fits():
        return pr_data

    # 3. Truncate Head Branch / Base Branch (before Repo — branches matter less)
    pr_data = _truncate_col(pr_data, "Head Branch", terminal_width, min_len=8)
    if fits():
        return pr_data
    pr_data = _truncate_col(pr_data, "Base Branch", terminal_width, min_len=8)
    if fits():
        return pr_data

    # 4. Truncate Repo (last text column — repo identity should stay readable longest)
    pr_data = _truncate_col(pr_data, "Repo", terminal_width, min_len=8)
    if fits():
        return pr_data

    # 5. Compress Mergeable?: drop the reason suffix
    if "Mergeable?" in pr_data[0]:

        def _compress_mergeable(val):
            plain = _strip_ansi(val)
            compressed = re.sub(r" \(.*\)$", "", plain)
            if compressed != plain:
                return val.replace(plain, compressed, 1)
            return val

        pr_data = [
            {**row, "Mergeable?": _compress_mergeable(row["Mergeable?"])}
            for row in pr_data
        ]
    if fits():
        return pr_data

    # 5b. Rename "Mergeable?" → "Mrg" (shorter header)
    if "Mergeable?" in pr_data[0]:
        pr_data = [
            {("Mrg" if k == "Mergeable?" else k): v for k, v in row.items()}
            for row in pr_data
        ]
    if fits():
        return pr_data

    # 6. Compress Checks: "✅ pass" → "✅" (preserving colour)
    if "Checks" in pr_data[0]:
        pr_data = [
            {**row, "Checks": _compress_styled(row["Checks"])} for row in pr_data
        ]
    if fits():
        return pr_data

    # 6b. Compress Approved: "✅ approved" → "✅", "✅ 1/2 approvals" → "✅ 1/2"
    if "Approved" in pr_data[0]:
        pr_data = [
            {**row, "Approved": _compress_styled(row["Approved"])} for row in pr_data
        ]
    if fits():
        return pr_data

    # 7. Rename "Comments" → "Cmt" (shorter header)
    if "Comments" in pr_data[0]:
        pr_data = [
            {("Cmt" if k == "Comments" else k): v for k, v in row.items()}
            for row in pr_data
        ]
    if fits():
        return pr_data

    # 7b. Rename "Approved" → "Apr" (shorter header)
    if "Approved" in pr_data[0]:
        pr_data = [
            {("Apr" if k == "Approved" else k): v for k, v in row.items()}
            for row in pr_data
        ]
    if fits():
        return pr_data

    # 8. Drop low-priority columns as last resort
    for col in _DROPPABLE_COLUMNS:
        if fits():
            break
        if col in pr_data[0]:
            pr_data = [{k: v for k, v in row.items() if k != col} for row in pr_data]

    return pr_data


def _stdout_is_tty():
    return sys.stdout.isatty()


def _handle_rate_limit(exc, json_output=False):
    """Print a friendly rate-limit message and exit non-zero."""
    click.echo(
        click.style(f"🥞 {exc}", fg="red", bold=True),
        err=True,
    )
    sys.exit(1)


def _print_debug_summary(t0, pr_count, api_stats, graphql_rate_limit):
    from datetime import datetime, timezone

    elapsed = time.monotonic() - t0
    total_calls = api_stats["rest_calls"] + api_stats["graphql_calls"]
    lines = [
        click.style("🐛 Debug summary", fg="cyan", bold=True),
        f"  Total elapsed:    {elapsed:.2f}s",
        f"  PRs processed:    {pr_count}",
        f"  API calls:        {total_calls}"
        f" ({api_stats['rest_calls']} REST + {api_stats['graphql_calls']} GraphQL)",
    ]
    remaining = api_stats.get("rest_rate_limit_remaining")
    reset_ts = api_stats.get("rest_rate_limit_reset")
    if remaining is not None:
        lines.append(f"  REST rate limit:  {remaining} requests remaining")
    if reset_ts is not None:
        reset_dt = datetime.fromtimestamp(reset_ts, tz=timezone.utc)
        lines.append(f"  REST rate resets: {reset_dt.strftime('%H:%M:%S UTC')}")
    if graphql_rate_limit:
        gql_remaining = graphql_rate_limit.get("remaining")
        gql_reset = graphql_rate_limit.get("resetAt")
        if gql_remaining is not None:
            lines.append(f"  GQL rate limit:   {gql_remaining} points remaining")
        if gql_reset:
            lines.append(f"  GQL rate resets:  {gql_reset}")
    click.echo("\n".join(lines), err=True)


def get_pr_age_days(pr_detail, now=None):
    from datetime import datetime, timezone

    created_at = pr_detail.get("created_at")
    if not created_at:
        return 0

    try:
        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("get_pr_age_days invalid_date created_at=%r", created_at)
        return 0

    if created_dt.tzinfo is None:
        created_dt = created_dt.replace(tzinfo=timezone.utc)
    if now is None:
        now = datetime.now(timezone.utc)

    return max((now - created_dt).days, 0)


_LEGENDARY_COMMENT_THRESHOLD = 100
_LEGENDARY_AGE_THRESHOLD_DAYS = 30
_LEGENDARY_EMOJI = "⚔️"


def is_legendary(pr_detail, now=None):
    """Return True if a PR qualifies as legendary.

    A PR is legendary if it has 100+ total comments AND has been open 30+ days.
    """
    total_comments = pr_detail.get("comments", 0) + pr_detail.get("review_comments", 0)
    return (
        total_comments >= _LEGENDARY_COMMENT_THRESHOLD
        and get_pr_age_days(pr_detail, now=now) >= _LEGENDARY_AGE_THRESHOLD_DAYS
    )


def _group_prs_by(pr_details, group_by):
    """Group PR details by author login or repo name.

    Args:
        pr_details: List of PR detail dicts.
        group_by: ``"user"`` to group by author login, ``"repo"`` for repo name.

    Returns:
        List of ``(name, url, count, draft_count, oldest_age_days, total_comments)``
        tuples sorted by count descending.
    """
    groups = {}
    for pr in pr_details:
        if group_by == "user":
            author = pr["user"]
            key = author["login"]
            url = author.get("html_url") or f"https://github.com/{key}"
        else:
            repo = pr["base"]["repo"]
            key = repo["name"]
            url = repo.get("html_url") or pr["html_url"].split("/pull/")[0]
        if key not in groups:
            groups[key] = {
                "url": url,
                "count": 0,
                "draft_count": 0,
                "oldest_age": 0,
                "total_comments": 0,
            }
        groups[key]["count"] += 1
        if pr.get("draft", False):
            groups[key]["draft_count"] += 1
        age = get_pr_age_days(pr)
        groups[key]["oldest_age"] = max(groups[key]["oldest_age"], age)
        groups[key]["total_comments"] += pr.get("review_comments", 0)
    return sorted(
        [
            (
                k,
                v["url"],
                v["count"],
                v["draft_count"],
                v["oldest_age"],
                v["total_comments"],
            )  # noqa: E501
            for k, v in groups.items()
        ],
        key=lambda x: x[2],
        reverse=True,
    )


def _fetch_pr_bundle(url, fetch_checks, fetch_approvals):
    """Fetch a PR's detail plus optional check and approval statuses in one shot.

    Propagates RequestException from the detail fetch so the caller can skip
    the PR. Check/approval failures fall back to sentinel values instead.
    """
    pr_detail = _fetch_pr_detail(url)

    check_status = None
    if fetch_checks:
        owner = pr_detail.get("base", {}).get("repo", {}).get("owner", {}).get("login")
        repo_name = pr_detail.get("base", {}).get("repo", {}).get("name")
        head_sha = pr_detail.get("head", {}).get("sha")
        if owner and repo_name and head_sha:
            try:
                check_status = get_check_status(owner, repo_name, head_sha)
            except requests.exceptions.RequestException as exc:
                logger.warning(
                    "check_status_fetch_failed pr_id=%s error=%r",
                    pr_detail.get("id"),
                    str(exc),
                )
                check_status = "none"
        else:
            check_status = "none"

    approval_detail = None
    if fetch_approvals:
        owner = pr_detail.get("base", {}).get("repo", {}).get("owner", {}).get("login")
        repo_name = pr_detail.get("base", {}).get("repo", {}).get("name")
        pr_number = pr_detail.get("number")
        base_branch = pr_detail.get("base", {}).get("ref")
        if owner and repo_name and pr_number is not None:
            try:
                approval_detail = get_approval_summary(
                    owner,
                    repo_name,
                    pr_number,
                    base_branch=base_branch,
                )
            except (ValueError, requests.exceptions.RequestException) as exc:
                logger.warning(
                    "approval_status_fetch_failed pr_id=%s error=%r",
                    pr_detail.get("id"),
                    str(exc),
                )
                approval_detail = {
                    "status": "pending",
                    "current": 0,
                    "required": None,
                }
        else:
            approval_detail = {
                "status": "pending",
                "current": 0,
                "required": None,
            }

    return pr_detail, check_status, approval_detail


@click.command()
@click.option("--config", help="Path to config file.")
@click.option("--show-config", is_flag=True, help="Print the resolved config and exit.")
@click.option(
    "--init-config", is_flag=True, help="Generate a default config file and exit."
)
@click.option(
    "--update-config",
    "update_config_cmd",
    is_flag=True,
    help=(
        "Append any options missing from the existing config file and exit."
        " Creates a timestamped backup before modifying."
    ),
)
@click.option("--organization", "-o", help="One or multiple organizations to report on")
@click.option("--repo-filter", "-r", help="Filter for specific repp(s)")
@click.option(
    "--ignore-author",
    multiple=True,
    help=(
        "Ignore PRs raised by one or more authors (case-insensitive). "
        "Repeat for multiple authors, e.g. --ignore-author dependabot[bot]."
    ),
)
@click.option(
    "--no-ignore-author",
    is_flag=True,
    help="Clear config defaults for ignore-author.",
)
@click.option(
    "--mine-only/--no-mine-only",
    default=None,
    help="Only include PRs authored by the currently authenticated GitHub user.",
)
@click.option(
    "--no-drafts",
    is_flag=True,
    default=False,
    help="Exclude draft PRs from results.",
)
@click.option(
    "--drafts-only",
    is_flag=True,
    default=False,
    help="Show only draft PRs.",
)
@click.option(
    "--age/--no-age",
    default=None,
    help="Include an age column showing PR age in days.",
)
@click.option(
    "--json/--no-json",
    "json_output",
    default=None,
    help="Output results as JSON. Alias for --format json / --format table.",
)
@click.option(
    "--format",
    "output_format",
    default=None,
    type=click.Choice(["table", "json", "markdown"], case_sensitive=False),
    help=(
        "Output format: table (default), json, or markdown. "
        "Overrides --json/--no-json when both are given."
    ),
)
@click.option(
    "--checks/--no-checks",
    default=None,
    help="Include a checks column showing CI/check status for each PR.",
)
@click.option(
    "--approvals/--no-approvals",
    default=None,
    help="Include an approvals column showing review approval status for each PR.",
)
@click.option(
    "--head-branch/--no-head-branch",
    default=None,
    help="Include a column showing the source branch the PR was raised from.",
)
@click.option(
    "--base-branch/--no-base-branch",
    default=None,
    help="Include a column showing the target branch the PR merges into.",
)
@click.option(
    "--status-style",
    type=click.Choice(["emoji", "ascii"], case_sensitive=False),
    default=None,
    help="Render status cells with emoji (default) or ASCII labels.",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Cap the number of PRs shown. Unset means show all results.",
)
@click.option(
    "--workers",
    type=int,
    default=None,
    help="Number of parallel workers for fetching PR data. Default: 64.",
)
@click.option(
    "--max-title-length",
    type=int,
    default=None,
    help="Truncate PR titles to this many characters. Unset means no truncation.",
)
@click.option(
    "--no-update-check",
    is_flag=True,
    default=False,
    envvar="BREAKFAST_NO_UPDATE_CHECK",
    help="Disable the automatic update check.",
)
@click.option(
    "--cache-ttl",
    type=str,
    default=None,
    help=(
        "How long to cache PR results (seconds, or suffix: 5m, 2h, 30s)."
        " Default: 300."
    ),
)
@click.option(
    "--cache/--no-cache",
    default=None,
    help=(
        "Enable disk cache for PR results."
        " Off by default; use --cache or set cache = true in config."
    ),
)
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help=(
        "Ignore the cache for this run but write fresh results back to it."
        " Requires --cache or cache = true in config."
    ),
)
@click.option(
    "--refresh-prs",
    is_flag=True,
    default=False,
    help=(
        "Re-fetch PR details using the cached repo list."
        " Faster than --refresh when only PR state has changed."
        " Requires --cache or cache = true in config."
    ),
)
@click.option(
    "--filter-state",
    type=click.Choice(["open", "closed", "draft"], case_sensitive=False),
    multiple=True,
    help=(
        "Only show PRs with this state. Repeat for multiple values."
        " 'draft' matches PRs where draft=true."
    ),
)
@click.option(
    "--filter-check",
    type=click.Choice(["pass", "fail", "pending", "none"], case_sensitive=False),
    multiple=True,
    help="Only show PRs with this CI check result. Repeat for multiple values.",
)
@click.option(
    "--filter-approval",
    type=click.Choice(["approved", "pending", "changes"], case_sensitive=False),
    multiple=True,
    help="Only show PRs with this review approval status. Repeat for multiple values.",
)
@click.option(
    "--legendary/--no-legendary",
    default=None,
    help=(
        "Append ⚔️ to the state of PRs with 100+ comments and open 30+ days."
        " Off by default."
    ),
)
@click.option(
    "--legendary-only",
    is_flag=True,
    default=False,
    help=(
        "Show only legendary PRs (100+ comments and open 30+ days)."
        " Implies --legendary."
    ),
)
@click.option(
    "--search",
    "-s",
    default=None,
    help=(
        "Filter PRs by title. Accepts a plain string or regex pattern;"
        " matching is case-insensitive."
    ),
)
@click.option(
    "--api-stats",
    is_flag=True,
    default=False,
    help=(
        "Print API diagnostics to stderr after output: call counts,"
        " rate-limit remaining, and total elapsed time."
    ),
)
@click.option(
    "--no-colour",
    "--no-color",
    "no_colour",
    is_flag=True,
    default=False,
    envvar="NO_COLOR",
    help=(
        "Disable ANSI colour in all output."
        " Also honoured via the NO_COLOR environment variable (no-color.org)."
    ),
)
@click.option(
    "--summarise-user-prs",
    "--summarize-user-prs",
    "summarise_user_prs",
    is_flag=True,
    default=False,
    help=(
        "Instead of the PR table, print a summary grouped by author:"
        " PR count, oldest age, and total comments per person."
    ),
)
@click.option(
    "--summarise-repo-prs",
    "--summarize-repo-prs",
    "summarise_repo_prs",
    is_flag=True,
    default=False,
    help=(
        "Instead of the PR table, print a summary grouped by repository:"
        " PR count, oldest age, and total comments per repo."
    ),
)
@click.version_option(package_name="breakfast")
def breakfast(
    config,
    show_config,
    init_config,
    update_config_cmd,
    organization,
    repo_filter,
    ignore_author,
    no_ignore_author,
    mine_only,
    no_drafts,
    drafts_only,
    age,
    json_output,
    output_format,
    checks,
    approvals,
    head_branch,
    base_branch,
    status_style,
    limit,
    workers,
    max_title_length,
    no_update_check,
    cache_ttl,
    cache,
    refresh,
    refresh_prs,
    filter_state,
    filter_check,
    filter_approval,
    legendary,
    legendary_only,
    search,
    api_stats,
    no_colour,
    summarise_user_prs,
    summarise_repo_prs,
):
    t0_total = time.monotonic()
    configure_logging()

    if search is not None:
        try:
            re.compile(search)
        except re.error as exc:
            click.echo(
                click.style(
                    f"Error: --search pattern is not valid regex: {exc}",
                    fg="red",
                    bold=True,
                ),
                err=True,
                color=not no_colour,
            )
            sys.exit(1)

    if init_config:
        generate_default_config()
        sys.exit(0)

    if update_config_cmd:
        update_config()
        sys.exit(0)

    cfg = load_config(config)

    organization = organization if organization is not None else cfg.get("organization")
    repo_filter = repo_filter if repo_filter is not None else cfg.get("repo-filter", "")

    if no_ignore_author:
        merged_ignore_authors = list(ignore_author)
    else:
        merged_ignore_authors = list(ignore_author) + cfg.get("ignore-author", [])
    ignore_author = merged_ignore_authors

    mine_only = mine_only if mine_only is not None else cfg.get("mine-only", False)
    no_drafts = no_drafts or cfg.get("no-drafts", False)
    drafts_only = drafts_only or cfg.get("drafts-only", False)
    age = age if age is not None else cfg.get("age", False)
    if output_format is not None:
        fmt = output_format.lower()
    elif json_output is not None:
        fmt = "json" if json_output else "table"
    else:
        cfg_format = cfg.get("format")
        if cfg_format is not None and cfg_format not in {"table", "json", "markdown"}:
            click.echo(
                click.style(
                    f"Warning: unrecognised format '{cfg_format}' in config"
                    " — expected 'table', 'json', or 'markdown'."
                    " Falling back to 'table'.",
                    fg="yellow",
                ),
                err=True,
            )
            cfg_format = "table"
        fmt = cfg_format or "table"
    json_output = fmt == "json"
    checks = checks if checks is not None else cfg.get("checks", False)
    approvals = approvals if approvals is not None else cfg.get("approvals", False)
    head_branch = (
        head_branch if head_branch is not None else cfg.get("head-branch", False)
    )
    base_branch = (
        base_branch if base_branch is not None else cfg.get("base-branch", False)
    )
    if status_style is None:
        status_style = str(cfg.get("status-style", "emoji")).lower()
    max_title_length = (
        max_title_length
        if max_title_length is not None
        else cfg.get("max-title-length")
    )
    workers = workers if workers is not None else cfg.get("workers", 64)
    if status_style not in {"emoji", "ascii"}:
        status_style = "emoji"
    legendary = legendary if legendary is not None else cfg.get("legendary", False)
    legendary_only = legendary_only or cfg.get("legendary-only", False)
    if legendary_only:
        legendary = True  # --legendary-only implies marking
    api_stats = api_stats or cfg.get("api-stats", False)
    no_colour = no_colour or cfg.get("no-colour", False)
    colour = not no_colour
    seasonal_colours = cfg.get("seasonal-colours", True)
    summarise_user_prs = summarise_user_prs or cfg.get("summarise-user-prs", False)
    summarise_repo_prs = summarise_repo_prs or cfg.get("summarise-repo-prs", False)

    if summarise_user_prs and summarise_repo_prs:
        click.echo(
            click.style(
                "Error: --summarise-user-prs and --summarise-repo-prs"
                " are mutually exclusive.",
                fg="red",
                bold=True,
            ),
            err=True,
            color=colour,
        )
        sys.exit(1)

    # Cache is opt-in: CLI flag > config > default off.
    cache_enabled = cache if cache is not None else cfg.get("cache", False)

    if refresh and not cache_enabled:
        click.echo(
            click.style(
                "Error: --refresh requires the cache to be enabled."
                " Pass --cache or set cache = true in config.",
                fg="red",
                bold=True,
            ),
            err=True,
            color=colour,
        )
        sys.exit(1)
    if refresh_prs and not cache_enabled:
        click.echo(
            click.style(
                "Error: --refresh-prs requires the cache to be enabled."
                " Pass --cache or set cache = true in config.",
                fg="red",
                bold=True,
            ),
            err=True,
            color=colour,
        )
        sys.exit(1)

    # Resolve effective cache TTL: CLI > config > default 300
    raw_ttl = cache_ttl if cache_ttl is not None else cfg.get("cache-ttl", 300)
    try:
        cache_ttl_seconds = parse_ttl(raw_ttl)
    except ValueError as exc:
        logger.error("invalid_cache_ttl value=%r error=%s", raw_ttl, exc)
        msg = f"Error: invalid --cache-ttl value: {exc}"
        click.echo(click.style(msg, fg="red", bold=True), err=True, color=colour)
        sys.exit(1)

    if show_config:
        click.echo("Resolved config:")
        resolved = {
            "organization": organization,
            "repo-filter": repo_filter,
            "ignore-author": ignore_author,
            "mine-only": mine_only,
            "no-drafts": no_drafts,
            "drafts-only": drafts_only,
            "age": age,
            "format": fmt,
            "checks": checks,
            "approvals": approvals,
            "status-style": status_style,
            "max-title-length": max_title_length,
            "workers": workers,
            "cache": cache_enabled,
            "cache-ttl": cache_ttl_seconds,
            "refresh": refresh,
            "refresh-prs": refresh_prs,
            "filter-state": filter_state,
            "filter-check": filter_check,
            "filter-approval": filter_approval,
            "legendary": legendary,
            "legendary-only": legendary_only,
            "search": search,
            "api-stats": api_stats,
            "no-colour": no_colour,
        }
        for k, v in resolved.items():
            click.echo(f"  {k}: {v}")
        sys.exit(0)

    logger.info(
        "startup org=%s repo_filter=%r mine_only=%s ignore_author=%r"
        " cache_enabled=%s cache_ttl=%ss refresh=%s refresh_prs=%s"
        " checks=%s approvals=%s age=%s legendary=%s legendary_only=%s"
        " limit=%s max_title_length=%s status_style=%s format=%s"
        " filter_state=%r filter_check=%r filter_approval=%r search=%r api_stats=%s",
        organization,
        repo_filter,
        mine_only,
        ignore_author,
        cache_enabled,
        cache_ttl_seconds,
        refresh,
        refresh_prs,
        checks,
        approvals,
        age,
        legendary,
        legendary_only,
        limit,
        max_title_length,
        status_style,
        fmt,
        filter_state,
        filter_check,
        filter_approval,
        search,
        api_stats,
    )

    if no_drafts and drafts_only:
        click.echo(
            click.style(
                "Error: --no-drafts and --drafts-only are mutually exclusive.",
                fg="red",
                bold=True,
            ),
            err=True,
            color=colour,
        )
        sys.exit(1)

    if not organization:
        message = (
            "Organization must be provided via CLI (-o) "
            "or config file (organization)."
        )
        click.echo(click.style(message, fg="red", bold=True), err=True, color=colour)
        sys.exit(1)

    if SECRET_GITHUB_TOKEN is None:
        message = "GITHUB_TOKEN not set in environment - exiting..."
        click.echo(click.style(message, fg="red", bold=True), err=True, color=colour)
        sys.exit(1)
    current_user_login = None
    if mine_only:
        try:
            current_user_login = get_authenticated_user_login()
        except GitHubRateLimitError as exc:
            _handle_rate_limit(exc, json_output)

    # grab all the pull requests we are interested in
    pr_data = []
    t_acquire = time.monotonic()

    # --- Layer 1: full PR detail cache (skip on --refresh or --refresh-prs) ---
    pr_details = None
    cached_check_statuses = None
    cached_approval_statuses = None
    cached_approval_details = None
    needs_cache_write = False
    if cache_enabled and not refresh and not refresh_prs:
        cache_result = read_pr_cache(organization, repo_filter, cache_ttl_seconds)
        if cache_result is not None:
            pr_details = cache_result["prs"]
            cached_check_statuses = cache_result["check_statuses"]
            cached_approval_statuses = cache_result["approval_statuses"]
            cached_approval_details = cache_result.get("approval_details")

    # Resolve implied flags before fetch so bundle knows what to fetch per PR.
    if filter_check:
        checks = True
    if filter_approval:
        approvals = True

    check_statuses = {}
    approval_statuses = {}
    approval_details = {}
    statuses_from_bundle = False

    if pr_details is None:
        # --- Layer 2: GraphQL URL list cache (skip only on --refresh) ---
        prs = None
        if cache_enabled and not refresh:
            prs = read_graphql_cache(organization, repo_filter, cache_ttl_seconds)

        if prs is None:
            try:
                prs = get_github_prs(organization, repo_filter)
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ) as exc:
                logger.exception(
                    "graphql_fetch_failed org=%s repo_filter=%r error=%r",
                    organization,
                    repo_filter,
                    str(exc),
                )
                msg = (
                    "🥞 Couldn't reach GitHub — "
                    "check your network connection and try again.\n"
                    f"  ({type(exc).__name__}: {exc})"
                )
                click.echo(
                    click.style(msg, fg="red", bold=True), err=True, color=colour
                )
                sys.exit(1)
            if cache_enabled:
                write_graphql_cache(organization, repo_filter, prs)
        else:
            click.echo(f"Fetching {organization} PRs...⚡...Done", err=True)

        pr_details = []
        failed_urls = []
        click.echo(f"Processing {repo_filter} PRs...", nl=False, err=True)
        if prs:
            max_workers = min(workers, len(prs))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_url = {
                    executor.submit(_fetch_pr_bundle, url, checks, approvals): url
                    for url in prs
                }
                for future in as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        pr_detail, check_status, approval_detail = future.result()
                        pr_details.append(pr_detail)
                        if check_status is not None:
                            check_statuses[pr_detail["id"]] = check_status
                        if approval_detail is not None:
                            approval_statuses[pr_detail["id"]] = approval_detail[
                                "status"
                            ]
                            approval_details[pr_detail["id"]] = approval_detail
                        click.echo(
                            random.choices(BREAKFAST_ITEMS)[0],
                            nl=False,
                            err=True,
                        )
                    except GitHubRateLimitError as exc:
                        click.echo("", err=True)  # end the progress line
                        _handle_rate_limit(exc, json_output)
                    except requests.exceptions.RequestException as exc:
                        logger.warning(
                            "pr_detail_fetch_failed url=%s error=%r", url, str(exc)
                        )
                        failed_urls.append(url)
        statuses_from_bundle = True
        click.echo("...Done", err=True)
        if failed_urls:
            examples = ", ".join(failed_urls[:3])
            suffix = " ..." if len(failed_urls) > 3 else ""
            msg = (
                f"Warning: {len(failed_urls)} PR(s) could not be fetched"
                f" after retries: {examples}{suffix}"
            )
            click.echo(click.style(msg, fg="yellow"), err=True, color=colour)
        if cache_enabled:
            needs_cache_write = True
    else:
        click.echo(f"Processing {repo_filter} PRs...⚡...Done", err=True)

    # Fetch check statuses for cache-hit paths where statuses are absent.
    # In the live-fetch path statuses are already populated by _fetch_pr_bundle.
    if checks and pr_details and not statuses_from_bundle:
        if cached_check_statuses is not None:
            check_statuses = cached_check_statuses
        else:
            max_workers = min(workers, len(pr_details))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                check_futures = []
                for pr_detail in pr_details:
                    owner = pr_detail["base"]["repo"]["owner"]["login"]
                    repo_name = pr_detail["base"]["repo"]["name"]
                    sha = pr_detail["head"]["sha"]
                    future = executor.submit(get_check_status, owner, repo_name, sha)
                    check_futures.append((pr_detail["id"], future))
            for pr_id, future in check_futures:
                try:
                    check_statuses[pr_id] = future.result()
                except requests.exceptions.RequestException as exc:
                    logger.warning(
                        "check_status_fetch_failed pr_id=%s error=%r",
                        pr_id,
                        str(exc),
                    )
                    check_statuses[pr_id] = "none"
            needs_cache_write = True

    # Fetch approval statuses for cache-hit paths where statuses are absent.
    # In the live-fetch path statuses are already populated by _fetch_pr_bundle.
    if approvals and pr_details and not statuses_from_bundle:
        if cached_approval_statuses is not None and cached_approval_details is not None:
            approval_statuses = cached_approval_statuses
            approval_details = cached_approval_details
        else:
            max_workers = min(workers, len(pr_details))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                approval_futures = []
                for pr_detail in pr_details:
                    owner = pr_detail["base"]["repo"]["owner"]["login"]
                    repo_name = pr_detail["base"]["repo"]["name"]
                    pr_number = pr_detail["number"]
                    base_branch = pr_detail.get("base", {}).get("ref")
                    future = executor.submit(
                        get_approval_summary, owner, repo_name, pr_number, base_branch
                    )
                    approval_futures.append((pr_detail["id"], future))
            for pr_id, future in approval_futures:
                try:
                    approval_detail = future.result()
                    approval_statuses[pr_id] = approval_detail["status"]
                    approval_details[pr_id] = approval_detail
                except (ValueError, requests.exceptions.RequestException) as exc:
                    logger.warning(
                        "approval_status_fetch_failed pr_id=%s error=%r",
                        pr_id,
                        str(exc),
                    )
                    approval_statuses[pr_id] = "pending"
                    approval_details[pr_id] = {
                        "status": "pending",
                        "current": 0,
                        "required": None,
                    }
            needs_cache_write = True

    logger.info(
        "data_acquired pr_count=%d elapsed_ms=%d",
        len(pr_details),
        int((time.monotonic() - t_acquire) * 1000),
    )

    if needs_cache_write:
        write_pr_cache(
            organization,
            repo_filter,
            pr_details,
            check_statuses=check_statuses or None,
            approval_statuses=approval_statuses or None,
            approval_details=approval_details or None,
        )
        if refresh or refresh_prs:
            click.echo("🔄 Cache refreshed.", err=True)

    before_filter = len(pr_details)
    pr_details = filter_pr_details(
        pr_details,
        ignore_author,
        mine_only=mine_only,
        current_user_login=current_user_login,
        no_drafts=no_drafts,
        drafts_only=drafts_only,
        filter_state=filter_state,
        filter_check=filter_check,
        filter_approval=filter_approval,
        check_statuses=check_statuses,
        approval_statuses=approval_statuses,
        search_title=search,
    )
    logger.info(
        "filter_result before=%d after=%d",
        before_filter,
        len(pr_details),
    )

    if search is not None and not pr_details:
        click.echo(
            click.style(
                f"🔍 No PRs matched '{search}'",
                fg="yellow",
            ),
            err=True,
            color=colour,
        )
    pr_details.sort(key=lambda pr: pr["base"]["repo"]["name"])
    if legendary_only:
        pr_details = [pr for pr in pr_details if is_legendary(pr)]
    if limit is not None:
        pr_details = pr_details[:limit]

    if summarise_user_prs or summarise_repo_prs:
        group_by = "user" if summarise_user_prs else "repo"
        title = (
            "👤 PR Summary by Author" if summarise_user_prs else "📦 PR Summary by Repo"
        )
        label_header = "Author" if summarise_user_prs else "Repo"
        groups = _group_prs_by(pr_details, group_by)
        logger.info(
            "render format=summary group_by=%s groups=%d", group_by, len(groups)
        )
        click.echo(
            render_pr_summary(groups, title, label_header, colour, seasonal_colours),
            color=colour and _stdout_is_tty(),
        )
        if not no_update_check:
            update_msg = check_for_update()
            if update_msg:
                logger.info("update_available msg=%r", update_msg)
                click.echo(
                    click.style(update_msg, fg="cyan", bold=True),
                    err=True,
                    color=colour,
                )
        if api_stats:
            _print_debug_summary(
                t0_total, len(pr_details), get_api_stats(), get_graphql_rate_limit()
            )
        return

    logger.info(
        "render format=%s row_count=%d",
        fmt,
        len(pr_details),
    )
    t_render = time.monotonic()

    if json_output:
        json_data = []
        for pr_detail in pr_details:
            entry = {
                "repo": pr_detail["base"]["repo"]["name"],
                "pr_number": pr_detail["number"],
                "title": pr_detail["title"],
                "author": pr_detail["user"]["login"],
                "url": pr_detail["html_url"],
                "state": pr_detail["state"],
                "draft": pr_detail.get("draft", False),
                "created_at": pr_detail.get("created_at"),
                "updated_at": pr_detail.get("updated_at"),
                "additions": pr_detail.get("additions"),
                "deletions": pr_detail.get("deletions"),
                "changed_files": pr_detail.get("changed_files"),
                "commits": pr_detail.get("commits"),
                "review_comments": pr_detail.get("review_comments"),
                "labels": [lb["name"] for lb in pr_detail.get("labels", [])],
                "requested_reviewers": [
                    r["login"] for r in pr_detail.get("requested_reviewers", [])
                ],
            }
            if checks:
                entry["checks"] = check_statuses.get(pr_detail["id"], "none")
            if approvals:
                entry["approval"] = approval_statuses.get(pr_detail["id"], "pending")
                approval_detail = approval_details.get(pr_detail["id"], {})
                if approval_detail.get("current") is not None:
                    entry["approval_current"] = approval_detail["current"]
                if approval_detail.get("required") is not None:
                    entry["approval_required"] = approval_detail["required"]
            json_data.append(entry)
        click.echo(json.dumps(json_data, indent=2))
        logger.info(
            "render_complete elapsed_ms=%d", int((time.monotonic() - t_render) * 1000)
        )
        if not no_update_check:
            update_msg = check_for_update()
            if update_msg:
                logger.info("update_available msg=%r", update_msg)
                click.echo(
                    click.style(update_msg, fg="cyan", bold=True),
                    err=True,
                    color=colour,
                )
        if api_stats:
            _print_debug_summary(
                t0_total, len(json_data), get_api_stats(), get_graphql_rate_limit()
            )
        return

    if fmt == "markdown":
        md_data = []
        for pr_detail in pr_details:
            repo = pr_detail["base"]["repo"]
            repo_url = repo.get("html_url") or pr_detail["html_url"].split("/pull/")[0]
            author = pr_detail["user"]
            author_url = (
                author.get("html_url") or f"https://github.com/{author['login']}"
            )
            state_str = pr_detail["state"]
            if pr_detail.get("draft"):
                state_str = "draft"
            adds = pr_detail["additions"]
            subs = pr_detail["deletions"]
            row = {
                "Repo": f"[{repo['name']}]({repo_url})",
                "PR Title": pr_detail["title"],
                "Author": f"[{author['login']}]({author_url})",
                "State": state_str,
                "Files": str(pr_detail["changed_files"]),
                "Commits": str(pr_detail["commits"]),
                "+/-": f"+{adds}/-{subs}",
                "Comments": str(pr_detail["review_comments"]),
            }
            if age:
                row["Age"] = str(get_pr_age_days(pr_detail))
            if checks:
                row["Checks"] = _osc8_to_markdown(
                    format_check_status(
                        check_statuses.get(pr_detail["id"], "none"),
                        style=status_style,
                    )
                )
            if approvals:
                approval_detail = approval_details.get(pr_detail["id"], {})
                row["Approved"] = _osc8_to_markdown(
                    format_approval_status(
                        approval_statuses.get(pr_detail["id"], "pending"),
                        style=status_style,
                        current_reviews=approval_detail.get("current"),
                        required_reviews=approval_detail.get("required"),
                    )
                )
            if head_branch:
                _hb_name = pr_detail["head"]["ref"]
                _hb_owner = pr_detail["base"]["repo"]["owner"]["login"]
                _hb_repo = pr_detail["base"]["repo"]["name"]
                _hb_url = f"https://github.com/{_hb_owner}/{_hb_repo}/tree/{_hb_name}"
                row["Head Branch"] = f"[{_hb_name}]({_hb_url})"
            if base_branch:
                _bb_name = pr_detail["base"]["ref"]
                _bb_owner = pr_detail["base"]["repo"]["owner"]["login"]
                _bb_repo = pr_detail["base"]["repo"]["name"]
                _bb_url = f"https://github.com/{_bb_owner}/{_bb_repo}/tree/{_bb_name}"
                row["Base Branch"] = f"[{_bb_name}]({_bb_url})"
            row["Mergeable?"] = _osc8_to_markdown(
                format_mergeable_status(
                    pr_detail["mergeable"],
                    pr_detail["mergeable_state"],
                    style=status_style,
                )
            )
            row["Link"] = f"[PR-{pr_detail['number']}]({pr_detail['html_url']})"
            md_data.append(row)
        click.echo(
            tabulate(
                md_data,
                headers="keys",
                tablefmt="github",
                disable_numparse=True,
            )
        )
        logger.info(
            "render_complete elapsed_ms=%d", int((time.monotonic() - t_render) * 1000)
        )
        if not no_update_check:
            update_msg = check_for_update()
            if update_msg:
                logger.info("update_available msg=%r", update_msg)
                click.echo(
                    click.style(update_msg, fg="cyan", bold=True),
                    err=True,
                    color=colour,
                )
        if api_stats:
            _print_debug_summary(
                t0_total, len(md_data), get_api_stats(), get_graphql_rate_limit()
            )
        return

    for pr_detail in pr_details:
        adds = click.style("+" + str(pr_detail["additions"]), fg="green", bold=True)
        subs = click.style("-" + str(pr_detail["deletions"]), fg="red", bold=True)

        state_label = format_pr_state(pr_detail["state"], pr_detail.get("draft", False))
        if legendary and is_legendary(pr_detail):
            state_label = state_label + " " + _LEGENDARY_EMOJI

        repo = pr_detail["base"]["repo"]
        repo_url = repo.get("html_url") or pr_detail["html_url"].split("/pull/")[0]
        author = pr_detail["user"]
        author_url = author.get("html_url") or f"https://github.com/{author['login']}"
        pr_num = pr_detail["number"]

        if seasonal_colours and colour:
            title_text = apply_seasonal_colour(pr_detail["title"], pr_num)
            author_cell = _styled_hyperlink(
                author_url,
                apply_seasonal_colour(author["login"], pr_num),
            )
        else:
            title_text = pr_detail["title"]
            author_cell = generate_terminal_url_anchor(author_url, author["login"])

        row = {
            "Repo": generate_terminal_url_anchor(repo_url, repo["name"]),
            "PR Title": title_text,
            "Author": author_cell,
            "State": state_label,
            "Files": click_colour_grade_number(pr_detail["changed_files"]),
            "Commits": click_colour_grade_number(pr_detail["commits"]),
            "+/-": f"{adds}/{subs}",
            "Comments": click_colour_grade_number(pr_detail["review_comments"]),
        }
        if age:
            row["Age"] = click_colour_grade_number(get_pr_age_days(pr_detail))
        if checks:
            row["Checks"] = _styled_hyperlink(
                f"{pr_detail['html_url']}/checks",
                format_check_status(
                    check_statuses.get(pr_detail["id"], "none"),
                    style=status_style,
                ),
            )
        if approvals:
            approval_detail = approval_details.get(pr_detail["id"], {})
            row["Approved"] = format_approval_status(
                approval_statuses.get(pr_detail["id"], "pending"),
                style=status_style,
                current_reviews=approval_detail.get("current"),
                required_reviews=approval_detail.get("required"),
            )
        if head_branch:
            _hb_name = pr_detail["head"]["ref"]
            _hb_owner = pr_detail["base"]["repo"]["owner"]["login"]
            _hb_repo = pr_detail["base"]["repo"]["name"]
            _hb_url = f"https://github.com/{_hb_owner}/{_hb_repo}/tree/{_hb_name}"
            row["Head Branch"] = generate_terminal_url_anchor(_hb_url, _hb_name)
        if base_branch:
            _bb_name = pr_detail["base"]["ref"]
            _bb_owner = pr_detail["base"]["repo"]["owner"]["login"]
            _bb_repo = pr_detail["base"]["repo"]["name"]
            _bb_url = f"https://github.com/{_bb_owner}/{_bb_repo}/tree/{_bb_name}"
            row["Base Branch"] = generate_terminal_url_anchor(_bb_url, _bb_name)
        row["Mergeable?"] = format_mergeable_status(
            pr_detail["mergeable"],
            pr_detail["mergeable_state"],
            style=status_style,
        )
        row["Link"] = generate_terminal_url_anchor(
            pr_detail["html_url"],
            f"PR-{pr_detail['number']}",
        )
        pr_data.append(row)

    # Apply explicit title truncation, then auto-fit to terminal if interactive
    if max_title_length:
        pr_data = [
            {
                **row,
                "PR Title": _truncate_formatted_text(row["PR Title"], max_title_length),
            }
            for row in pr_data
        ]
    if _stdout_is_tty() and pr_data:
        terminal_width = shutil.get_terminal_size().columns
        pr_data = _auto_fit(pr_data, terminal_width, max_title_length)

    click.echo(
        tabulate(
            pr_data,
            headers="keys",
            showindex="always",
            tablefmt="outline",
            disable_numparse=True,
        ),
        color=_stdout_is_tty() and colour,
    )

    logger.info(
        "render_complete elapsed_ms=%d", int((time.monotonic() - t_render) * 1000)
    )

    if not no_update_check:
        update_msg = check_for_update()
        if update_msg:
            logger.info("update_available msg=%r", update_msg)
            click.echo(
                click.style(update_msg, fg="cyan", bold=True), err=True, color=colour
            )

    if api_stats:
        _print_debug_summary(
            t0_total, len(pr_data), get_api_stats(), get_graphql_rate_limit()
        )


if __name__ == "__main__":
    breakfast()
