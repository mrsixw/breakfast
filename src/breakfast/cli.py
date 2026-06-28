import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse

import click
import requests

from .api import (
    SECRET_GITHUB_TOKEN,
    GitHubRateLimitError,
    OwnerNotFoundError,
    _fetch_pr_detail,
    _match_exclude_repos,
    get_api_stats,
    get_approval_summary,
    get_authenticated_user_login,
    get_check_status,
    get_github_prs,
    get_graphql_rate_limit,
    get_pr_age_days,
)
from .cache import (
    parse_ttl,
    read_cached_user_login,
    read_graphql_cache,
    read_pr_cache,
    read_repo_pr_cache,
    write_cached_user_login,
    write_graphql_cache,
    write_pr_cache,
    write_repo_pr_cache,
)
from .config import (
    filter_pr_details,
    generate_default_config,
    load_config,
    parse_columns_config,
    update_config,
)
from .logger import configure as configure_logging
from .logger import logger
from .renderers import (
    is_legendary,
    render_csv,
    render_json,
    render_markdown,
    render_table,
    render_template,
)
from .ui import (
    BREAKFAST_ITEMS,
    render_colour_diagnostics,
    render_pr_summary,
)
from .updater import check_for_update


def format_cache_age(age_seconds: float) -> str:
    """Format duration in seconds to a user-friendly string."""
    if age_seconds < 60:
        return "less than a minute ago"
    elif age_seconds < 120:
        return "1 minute ago"
    elif age_seconds < 3600:
        return f"{int(age_seconds // 60)} minutes ago"
    elif age_seconds < 7200:
        return "1 hour ago"
    elif age_seconds < 86400:
        return f"{int(age_seconds // 3600)} hours ago"
    elif age_seconds < 172800:
        return "1 day ago"
    else:
        return f"{int(age_seconds // 86400)} days ago"


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


def _finish_run(
    t0_total,
    pr_count,
    *,
    no_update_check,
    show_update_summary,
    api_stats,
    colour,
):
    if not no_update_check:
        update_msg = check_for_update(show_summary=show_update_summary)
        if update_msg:
            logger.info("update_available msg=%r", update_msg)
            click.echo(
                click.style(update_msg, fg="cyan", bold=True),
                err=True,
                color=colour,
            )
    if api_stats:
        _print_debug_summary(
            t0_total, pr_count, get_api_stats(), get_graphql_rate_limit()
        )


def _parse_org_spec(spec: str) -> tuple[str, list[str] | None]:
    """Parse an org spec that may carry a scoped repo filter after a colon.

    Returns (org_name, scoped_filters) where scoped_filters is:
      - None  → no colon; defer to the global -r filters
      - []    → colon present but no filter; match all repos for this org
      - [str] → colon present with filter text; match only that pattern
    """
    if ":" not in spec:
        return spec, None
    org, _, filter_text = spec.partition(":")
    return org, [filter_text] if filter_text else []


def consolidate_org_specs(
    org_specs: list[tuple[str, list[str] | None]],
    global_repo_filters: list[str],
) -> list[tuple[str, list[str] | None]]:
    """Consolidate multiple org specs targeting the same organization.

    Preserves the order of first encounter and the casing of the first encounter.
    """
    grouped: dict[str, tuple[str, list[list[str] | None]]] = {}
    for org, scoped in org_specs:
        low = org.lower()
        if low not in grouped:
            grouped[low] = (org, [])
        grouped[low][1].append(scoped)

    consolidated = []
    for _, (org, scoped_list) in grouped.items():
        # If all specs are None, keep it as None to preserve deferring to global filters
        if all(s is None for s in scoped_list):
            consolidated.append((org, None))
            continue

        # Resolve each scoped filter
        effective_lists = []
        for s in scoped_list:
            if s is None:
                effective_lists.append(global_repo_filters)
            else:
                effective_lists.append(s)

        # If any resolved list is empty, it matches all repos unconditionally
        if any(not lst for lst in effective_lists):
            consolidated.append((org, []))
        else:
            # Combine and deduplicate preserving order
            combined = []
            seen = set()
            for lst in effective_lists:
                for item in lst:
                    if item not in seen:
                        seen.add(item)
                        combined.append(item)
            consolidated.append((org, combined))

    return consolidated


def _org_spec_cache_segment(org: str, scoped: list[str] | None) -> str:
    """Cache key encodes each org with its effective scoped filter for determinism."""
    if scoped is None:
        return org.lower()
    filter_str = ",".join(sorted(f.lower() for f in scoped)) if scoped else ""
    return org.lower() + ":" + filter_str


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
        groups[key]["total_comments"] += pr.get("comments", 0) + pr.get(
            "review_comments", 0
        )
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


def _extract_repo_name(url):
    parts = urlparse(url).path.strip("/").split("/")
    return parts[1] if len(parts) >= 2 else ""


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
@click.option(
    "--completion",
    "completion_shell",
    type=click.Choice(["bash", "zsh", "fish"]),
    default=None,
    is_eager=True,
    expose_value=True,
    help="Print shell completion script for SHELL and exit. Eval in your shell config.",
)
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
@click.option(
    "--owner",
    "-o",
    "owner",
    multiple=True,
    help=(
        "GitHub owner (organization or personal account) to query for PRs."
        " Repeat for multiple owners, e.g. -o my-org -o my-user."
        " Optionally append a scoped repo filter with a colon:"
        " -o my-org:api (only 'api' repos for that owner),"
        " -o my-org: (all repos for that owner, ignoring global -r)."
    ),
)
@click.option(
    "--org",
    "org_deprecated",
    multiple=True,
    hidden=True,
    help="Deprecated. Use --owner instead.",
)
@click.option(
    "--organization",
    "organization_deprecated",
    multiple=True,
    hidden=True,
    help="Deprecated. Use --owner instead.",
)
@click.option(
    "--repo-filter",
    "-r",
    multiple=True,
    help=(
        "Filter PRs to repos matching this pattern. Repeat for multiple"
        " filters, e.g. -r api -r platform (OR logic)."
    ),
)
@click.option(
    "--exclude-repo",
    "exclude_repo",
    multiple=True,
    help=(
        "Exclude repos matching this pattern (repeatable). "
        "Supports glob patterns, e.g. --exclude-repo 'old-*'."
    ),
)
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
    "--needs-my-review/--no-needs-my-review",
    default=None,
    help="Only show PRs where you are a requested reviewer.",
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
    "--markdown/--no-markdown",
    "markdown_flag",
    default=None,
    help="Output results as a Markdown table. Alias for --format markdown.",
)
@click.option(
    "--format",
    "output_format",
    default=None,
    type=click.Choice(
        ["table", "json", "markdown", "csv", "template"], case_sensitive=False
    ),
    help=(
        "Output format: table (default), json, markdown, csv, or template. "
        "Overrides --json/--no-json/--markdown when both are given."
    ),
)
@click.option(
    "--template",
    "template_str",
    default=None,
    help=(
        "Format string for --format template. "
        "Fields: {repo}, {title}, {author}, {url}, {state}, {number},"
        " {created_at}, {updated_at}, {additions}, {deletions},"
        " {changed_files}, {commits}, {review_comments}, {labels},"
        " {requested_reviewers}."
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
    "--offline",
    is_flag=True,
    default=False,
    help="Force offline mode using the most recent cached data (even if expired).",
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
    "--fetch-state",
    type=click.Choice(["open", "closed", "merged", "all"], case_sensitive=False),
    default=None,
    help=(
        "Which PR states to fetch from GitHub. 'open' fetches only open PRs"
        " (default). Use 'closed', 'merged', or 'all' to include other states."
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
    "--filter-mergeable",
    type=click.Choice(["clean", "conflict", "unknown"], case_sensitive=False),
    multiple=True,
    help=(
        "Only show PRs with this mergeable status. Repeat for multiple values"
        " (OR logic). Values: clean, conflict, unknown."
    ),
)
@click.option(
    "--filter-reviewer",
    multiple=True,
    help=(
        "Only show PRs that have this user as a requested reviewer"
        " (repeatable, case-insensitive). e.g. --filter-reviewer alice"
    ),
)
@click.option(
    "--label",
    "filter_label",
    multiple=True,
    help=(
        "Only show PRs that have this label (repeatable, case-insensitive)."
        " e.g. --label bug --label enhancement"
    ),
)
@click.option(
    "--exclude-label",
    multiple=True,
    help=(
        "Exclude PRs that have this label (repeatable, case-insensitive)."
        " e.g. --exclude-label wip"
    ),
)
@click.option(
    "--filter-stale",
    type=int,
    default=None,
    help="Only show PRs older than N days (by creation date).",
)
@click.option(
    "--filter-inactive",
    type=int,
    default=None,
    help="Only show PRs not updated in the last N days.",
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
    "--sort",
    "sort_by",
    type=click.Choice(
        ["repo", "age", "updated", "author", "comments", "reviews", "size", "files"],
        case_sensitive=False,
    ),
    default=None,
    help=(
        "Sort PRs by field. Choices: repo (default), age, updated,"
        " author, comments, reviews, size, files."
    ),
)
@click.option(
    "--reverse",
    "sort_reverse",
    is_flag=True,
    default=False,
    help="Reverse the sort order.",
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
    "--colour-diagnostics",
    "--color-diagnostics",
    "colour_diagnostics",
    is_flag=True,
    default=False,
    help=(
        "Print a colour swatch page showing every colour and gradient used in"
        " the breakfast UI, then exit. Useful for tuning palette choices in"
        " your terminal."
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
    completion_shell,
    config,
    show_config,
    init_config,
    update_config_cmd,
    owner,
    org_deprecated,
    organization_deprecated,
    repo_filter,
    exclude_repo,
    ignore_author,
    no_ignore_author,
    mine_only,
    needs_my_review,
    no_drafts,
    drafts_only,
    age,
    json_output,
    markdown_flag,
    output_format,
    template_str,
    checks,
    approvals,
    head_branch,
    base_branch,
    status_style,
    limit,
    workers,
    max_title_length,
    no_update_check,
    offline,
    cache_ttl,
    cache,
    refresh,
    refresh_prs,
    fetch_state,
    filter_state,
    filter_check,
    filter_approval,
    filter_mergeable,
    filter_reviewer,
    filter_label,
    exclude_label,
    filter_stale,
    filter_inactive,
    legendary,
    legendary_only,
    search,
    api_stats,
    no_colour,
    colour_diagnostics,
    summarise_user_prs,
    summarise_repo_prs,
    sort_by,
    sort_reverse,
):
    t0_total = time.monotonic()
    configure_logging()

    if completion_shell:
        from click.shell_completion import get_completion_class

        comp_cls = get_completion_class(completion_shell)
        comp = comp_cls(
            cli=breakfast,
            ctx_args={},
            prog_name="breakfast",
            complete_var="_BREAKFAST_COMPLETE",
        )
        click.echo(comp.source(), nl=False)
        sys.exit(0)

    if colour_diagnostics:
        click.echo(render_colour_diagnostics(), color=True)
        sys.exit(0)

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

    column_specs = parse_columns_config(cfg.get("columns"))
    if column_specs:
        _spec_names = {s["name"] for s in column_specs}
        if "age" in _spec_names and age is None:
            age = True
        if "checks" in _spec_names and checks is None:
            checks = True
        if "approvals" in _spec_names and approvals is None:
            approvals = True
        if "head-branch" in _spec_names and head_branch is None:
            head_branch = True
        if "base-branch" in _spec_names and base_branch is None:
            base_branch = True

    # --owner / deprecated --org / --organization flags; merge and warn on deprecated
    if org_deprecated:
        click.echo(
            click.style(
                "⚠️  --org is deprecated and will be removed in a future release."
                " Use --owner instead.",
                fg="yellow",
            ),
            err=True,
        )
    if organization_deprecated:
        click.echo(
            click.style(
                "⚠️  --organization is deprecated and will be removed in a future"
                " release. Use --owner instead.",
                fg="yellow",
            ),
            err=True,
        )
    effective_owner = (
        tuple(owner) + tuple(org_deprecated) + tuple(organization_deprecated)
    )
    if effective_owner:
        organizations = list(effective_owner)
    else:
        cfg_org = cfg.get("owner")
        if isinstance(cfg_org, list):
            organizations = cfg_org
        elif cfg_org:
            organizations = [cfg_org]
        else:
            organizations = []
    # Parse org:filter scoped syntax
    org_specs = [_parse_org_spec(s) for s in organizations]
    # repo_filter is a tuple from multiple=True; merge with config
    if repo_filter:
        repo_filters = list(repo_filter)
    else:
        cfg_rf = cfg.get("repo-filter", [])
        if isinstance(cfg_rf, list):
            repo_filters = cfg_rf
        elif cfg_rf:
            repo_filters = [cfg_rf]
        else:
            repo_filters = []
    # Consolidate duplicate organization fetches and group their scoped filters
    org_specs = consolidate_org_specs(org_specs, repo_filters)
    organizations = [org for org, _ in org_specs]
    repo_cache_key = (
        "|".join(sorted(f.lower() for f in repo_filters)) if repo_filters else ""
    )
    exclude_repos = list(exclude_repo) + cfg.get("exclude-repos", [])

    if no_ignore_author:
        merged_ignore_authors = list(ignore_author)
    else:
        merged_ignore_authors = list(ignore_author) + cfg.get("ignore-author", [])
    ignore_author = merged_ignore_authors

    mine_only = mine_only if mine_only is not None else cfg.get("mine-only", False)
    needs_my_review = (
        needs_my_review
        if needs_my_review is not None
        else cfg.get("needs-my-review", False)
    )
    no_drafts = no_drafts or cfg.get("no-drafts", False)
    drafts_only = drafts_only or cfg.get("drafts-only", False)
    age = age if age is not None else cfg.get("age", False)
    cli_template = template_str
    template_str = cli_template if cli_template is not None else cfg.get("template")
    if output_format is not None:
        fmt = output_format.lower()
    elif json_output is not None:
        fmt = "json" if json_output else "table"
    elif markdown_flag is not None:
        fmt = "markdown" if markdown_flag else "table"
    elif cli_template is not None:
        fmt = "template"
    else:
        cfg_format = cfg.get("format")
        if cfg_format is not None and cfg_format not in {
            "table",
            "json",
            "markdown",
            "csv",
            "template",
        }:
            click.echo(
                click.style(
                    f"Warning: unrecognised format '{cfg_format}' in config"
                    " — expected 'table', 'json', 'markdown', 'csv', or 'template'."
                    " Falling back to 'table'.",
                    fg="yellow",
                ),
                err=True,
            )
            cfg_format = "table"

        if cfg_format is not None:
            fmt = cfg_format
        elif template_str is not None:
            fmt = "template"
        else:
            fmt = "table"
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
    fetch_state = (
        fetch_state if fetch_state is not None else cfg.get("fetch-state", "open")
    )
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
    seasonal_calendar = cfg.get("seasonal-calendar", "western")
    if not seasonal_colours:
        seasonal_calendar = "off"
    colour_index = cfg.get("colour-index", False)
    summarise_user_prs = summarise_user_prs or cfg.get("summarise-user-prs", False)
    summarise_repo_prs = summarise_repo_prs or cfg.get("summarise-repo-prs", False)
    show_update_summary = cfg.get("update-summary", False)
    sort_by = sort_by if sort_by is not None else cfg.get("sort", "repo")
    sort_reverse = sort_reverse or cfg.get("sort-reverse", False)

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

    offline = offline or cfg.get("offline", False)
    # Cache is opt-in: CLI flag > config > default off.
    cache_enabled = cache if cache is not None else cfg.get("cache", False)
    if offline:
        cache_enabled = True

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
            "owner": [
                org if scoped is None else (org + ":" + (scoped[0] if scoped else ""))
                for org, scoped in org_specs
            ],
            "repo-filter": repo_filters,
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
        "startup org_specs=%s repo_filters=%r mine_only=%s ignore_author=%r"
        " cache_enabled=%s cache_ttl=%ss refresh=%s refresh_prs=%s"
        " checks=%s approvals=%s age=%s legendary=%s legendary_only=%s"
        " limit=%s max_title_length=%s status_style=%s format=%s"
        " filter_state=%r filter_check=%r filter_approval=%r search=%r api_stats=%s",
        org_specs,
        repo_filters,
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

    if not organizations:
        message = (
            "Owner must be provided via CLI (-o / --owner) " "or config file (owner)."
        )
        click.echo(click.style(message, fg="red", bold=True), err=True, color=colour)
        sys.exit(1)

    if SECRET_GITHUB_TOKEN is None:
        message = "GITHUB_TOKEN not set in environment - exiting..."
        click.echo(click.style(message, fg="red", bold=True), err=True, color=colour)
        sys.exit(1)
    current_user_login = None
    if mine_only or needs_my_review:
        if not offline:
            try:
                current_user_login = get_authenticated_user_login()
                write_cached_user_login(current_user_login)
            except GitHubRateLimitError as exc:
                _handle_rate_limit(exc, json_output)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                pass
        else:
            current_user_login = read_cached_user_login()
    t_acquire = time.monotonic()

    # Cache key encodes each org with its effective scoped filter for determinism
    org_cache_key = "|".join(
        sorted(_org_spec_cache_segment(o, s) for o, s in org_specs)
    )

    # --- Layer 1: full cache (skip on --refresh/--refresh-prs unless offline) ---
    pr_details = None
    cached_check_statuses = None
    cached_approval_statuses = None
    cached_approval_details = None
    needs_cache_write = False
    offline_mode = False

    if offline:
        cache_result = read_pr_cache(
            org_cache_key, repo_cache_key, cache_ttl_seconds, ignore_ttl=True
        )
        if cache_result is not None:
            pr_details = cache_result["prs"]
            cached_check_statuses = cache_result["check_statuses"]
            cached_approval_statuses = cache_result["approval_statuses"]
            cached_approval_details = cache_result.get("approval_details")
            offline_mode = True
            no_update_check = True
            fetched_at = datetime.fromisoformat(cache_result["fetched_at"])
            cache_age_seconds = (
                datetime.now(timezone.utc) - fetched_at
            ).total_seconds()
            formatted_age = format_cache_age(cache_age_seconds)
            click.echo(
                click.style(
                    f"🔌 Offline Mode: Displaying cached data from {formatted_age}.",
                    fg="yellow",
                    bold=True,
                ),
                err=True,
                color=colour,
            )
        else:
            click.echo(
                click.style(
                    "Error: Offline mode enabled, but no cached data was found.",
                    fg="red",
                    bold=True,
                ),
                err=True,
                color=colour,
            )
            sys.exit(1)

    if pr_details is None and cache_enabled and not refresh and not refresh_prs:
        cache_result = read_pr_cache(org_cache_key, repo_cache_key, cache_ttl_seconds)
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
        try:
            # --- Layer 2: GraphQL URL list cache (skip only on --refresh) ---
            prs = None
            if cache_enabled and not refresh:
                prs = read_graphql_cache(
                    org_cache_key, repo_cache_key, cache_ttl_seconds
                )

            if prs is None:
                prs = []
                for org, scoped_filters in org_specs:
                    effective_filters = (
                        repo_filters if scoped_filters is None else scoped_filters
                    )
                    try:
                        prs.extend(get_github_prs(org, effective_filters, fetch_state))
                    except OwnerNotFoundError as exc:
                        logger.warning(
                            "graphql_owner_not_found owner=%s error=%r",
                            org,
                            str(exc),
                        )
                        click.echo(
                            click.style(
                                f"🍳 Owner not found: '{org}' could not be "
                                "resolved as a GitHub organization or user account."
                                " Check the name and your token's access.",
                                fg="red",
                                bold=True,
                            ),
                            err=True,
                            color=colour,
                        )
                        sys.exit(1)
                # Deduplicate by URL
                seen: set[str] = set()
                unique_prs = []
                for url in prs:
                    if url not in seen:
                        seen.add(url)
                        unique_prs.append(url)
                prs = unique_prs
                if cache_enabled:
                    write_graphql_cache(org_cache_key, repo_cache_key, prs)
            else:
                org_display = ", ".join(organizations)
                click.echo(f"Fetching {org_display} PRs...⚡...Done", err=True)

            if exclude_repos and prs:
                prs = [
                    url
                    for url in prs
                    if not _match_exclude_repos(_extract_repo_name(url), exclude_repos)
                ]

            # --- Layer 2.5: per-repo PR cache ---
            urls_to_fetch = list(prs) if prs else []
            repo_hit_prs: list = []
            repo_hit_checks: dict = {}
            repo_hit_approvals: dict = {}
            repo_hit_approval_details: dict = {}

            if cache_enabled and not refresh_prs and prs:
                repos_to_urls: dict[tuple[str, str], list[str]] = {}
                for url in prs:
                    parts = urlparse(url).path.strip("/").split("/")
                    if len(parts) >= 4:
                        repos_to_urls.setdefault((parts[0], parts[1]), []).append(url)

                uncached_urls: list[str] = []
                for (org_name, rname), repo_urls in repos_to_urls.items():
                    cached = read_repo_pr_cache(org_name, rname, cache_ttl_seconds)
                    if cached is not None:
                        repo_hit_prs.extend(cached["prs"])
                        if cached["check_statuses"]:
                            repo_hit_checks.update(cached["check_statuses"])
                        if cached["approval_statuses"]:
                            repo_hit_approvals.update(cached["approval_statuses"])
                        if cached["approval_details"]:
                            repo_hit_approval_details.update(cached["approval_details"])
                    else:
                        uncached_urls.extend(repo_urls)
                urls_to_fetch = uncached_urls

            pr_details = []
            failed_urls = []
            newly_fetched_by_repo: dict[str, dict] = {}
            repo_display = ", ".join(repo_filters) if repo_filters else "all repos"
            click.echo(f"Processing {repo_display} PRs...", nl=False, err=True)

            if not urls_to_fetch and repo_hit_prs:
                click.echo("⚡", nl=False, err=True)

            if urls_to_fetch:
                max_workers = min(workers, len(urls_to_fetch))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_url = {
                        executor.submit(_fetch_pr_bundle, url, checks, approvals): url
                        for url in urls_to_fetch
                    }
                    for future in as_completed(future_to_url):
                        url = future_to_url[future]
                        try:
                            pr_detail, check_status, approval_detail = future.result()
                            pr_details.append(pr_detail)
                            rname = pr_detail["base"]["repo"]["name"]
                            url_parts = urlparse(url).path.strip("/").split("/")
                            org_name = url_parts[0] if len(url_parts) >= 2 else ""
                            rd = newly_fetched_by_repo.setdefault(
                                (org_name, rname),
                                {
                                    "prs": [],
                                    "checks": {},
                                    "approvals": {},
                                    "approval_details": {},
                                },
                            )
                            rd["prs"].append(pr_detail)
                            if check_status is not None:
                                check_statuses[pr_detail["id"]] = check_status
                                rd["checks"][pr_detail["id"]] = check_status
                            if approval_detail is not None:
                                approval_statuses[pr_detail["id"]] = approval_detail[
                                    "status"
                                ]
                                approval_details[pr_detail["id"]] = approval_detail
                                rd["approvals"][pr_detail["id"]] = approval_detail[
                                    "status"
                                ]
                                rd["approval_details"][
                                    pr_detail["id"]
                                ] = approval_detail
                            click.echo(
                                random.choices(BREAKFAST_ITEMS)[0],
                                nl=False,
                                err=True,
                            )
                        except GitHubRateLimitError as exc:
                            click.echo("", err=True)
                            _handle_rate_limit(exc, json_output)
                        except requests.exceptions.RequestException as exc:
                            logger.warning(
                                "pr_detail_fetch_failed url=%s error=%r", url, str(exc)
                            )
                            failed_urls.append(url)

            # Write per-repo cache for repos fetched in this run
            if cache_enabled and newly_fetched_by_repo:
                for (org_name, rname), rdata in newly_fetched_by_repo.items():
                    write_repo_pr_cache(
                        org_name,
                        rname,
                        rdata["prs"],
                        check_statuses=rdata["checks"] or None,
                        approval_statuses=rdata["approvals"] or None,
                        approval_details=rdata["approval_details"] or None,
                    )

            # Merge per-repo cache hits into the main collections
            pr_details.extend(repo_hit_prs)
            check_statuses.update(repo_hit_checks)
            approval_statuses.update(repo_hit_approvals)
            approval_details.update(repo_hit_approval_details)

            # When all PRs came from per-repo cache, use cached statuses path
            statuses_from_bundle = bool(urls_to_fetch)
            if not statuses_from_bundle and repo_hit_prs:
                cached_check_statuses = repo_hit_checks or None
                cached_approval_statuses = repo_hit_approvals or None
                cached_approval_details = repo_hit_approval_details or None

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

        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as exc:
            # Fall back to expired cache
            cache_result = read_pr_cache(
                org_cache_key,
                repo_cache_key,
                cache_ttl_seconds,
                ignore_ttl=True,
            )
            if cache_result is not None:
                pr_details = cache_result["prs"]
                cached_check_statuses = cache_result["check_statuses"]
                cached_approval_statuses = cache_result["approval_statuses"]
                cached_approval_details = cache_result.get("approval_details")
                offline_mode = True
                no_update_check = True
                fetched_at = datetime.fromisoformat(cache_result["fetched_at"])
                cache_age_seconds = (
                    datetime.now(timezone.utc) - fetched_at
                ).total_seconds()
                formatted_age = format_cache_age(cache_age_seconds)
                # Ensure we end the progress line if we started it
                click.echo("", err=True)
                click.echo(
                    click.style(
                        "🔌 Offline Mode: Displaying cached data from "
                        f"{formatted_age}.",
                        fg="yellow",
                        bold=True,
                    ),
                    err=True,
                    color=colour,
                )
            else:
                logger.exception(
                    "graphql_fetch_failed org_cache_key=%s error=%r",
                    org_cache_key,
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
    else:
        if not offline_mode:
            repo_display = ", ".join(repo_filters) if repo_filters else "all repos"
            click.echo(f"Processing {repo_display} PRs...⚡...Done", err=True)

    # Fetch check statuses for cache-hit paths where statuses are absent.
    # In the live-fetch path statuses are already populated by _fetch_pr_bundle.
    if checks and pr_details and not statuses_from_bundle:
        if cached_check_statuses is not None:
            check_statuses = cached_check_statuses
            # Ensure all PRs are in check_statuses
            for pr_detail in pr_details:
                if pr_detail["id"] not in check_statuses:
                    check_statuses[pr_detail["id"]] = "none"
        elif offline_mode:
            # Skip fetching if offline
            for pr_detail in pr_details:
                check_statuses[pr_detail["id"]] = "none"
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
                except (
                    KeyError,
                    ValueError,
                    AttributeError,
                    requests.exceptions.RequestException,
                ) as exc:
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
            # Ensure all PRs are in approval_statuses and approval_details
            for pr_detail in pr_details:
                if pr_detail["id"] not in approval_statuses:
                    approval_statuses[pr_detail["id"]] = "pending"
                if pr_detail["id"] not in approval_details:
                    approval_details[pr_detail["id"]] = {
                        "status": "pending",
                        "current": 0,
                        "required": None,
                    }
        elif offline_mode:
            # Skip fetching if offline
            for pr_detail in pr_details:
                approval_statuses[pr_detail["id"]] = "pending"
                approval_details[pr_detail["id"]] = {
                    "status": "pending",
                    "current": 0,
                    "required": None,
                }
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

    if needs_cache_write and not offline_mode:
        write_pr_cache(
            org_cache_key,
            repo_cache_key,
            pr_details,
            check_statuses=check_statuses or None,
            approval_statuses=approval_statuses or None,
            approval_details=approval_details or None,
        )
        if refresh or refresh_prs:
            click.echo("🔄 Cache refreshed.", err=True)

    if (mine_only or needs_my_review) and offline_mode and current_user_login is None:
        click.echo(
            click.style(
                "⚠️  Offline mode: no cached login found — "
                "--mine-only / --needs-my-review skipped. "
                "Run online once to cache your login.",
                fg="yellow",
            ),
            err=True,
            color=colour,
        )

    effective_filter_reviewer = list(filter_reviewer)
    if needs_my_review and current_user_login:
        effective_filter_reviewer.append(current_user_login)

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
        filter_mergeable=filter_mergeable,
        check_statuses=check_statuses,
        approval_statuses=approval_statuses,
        search_title=search,
        filter_reviewer=effective_filter_reviewer,
        filter_label=filter_label,
        exclude_label=exclude_label,
        filter_stale=filter_stale,
        filter_inactive=filter_inactive,
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
    _SORT_KEYS = {
        "repo": lambda pr: pr["base"]["repo"]["name"],
        "age": lambda pr: get_pr_age_days(pr),
        "updated": lambda pr: pr.get("updated_at", ""),
        "author": lambda pr: pr.get("user", {}).get("login", "").lower(),
        "comments": lambda pr: pr.get("comments", 0) + pr.get("review_comments", 0),
        "reviews": lambda pr: pr.get("review_comments", 0),
        "size": lambda pr: pr.get("additions", 0) + pr.get("deletions", 0),
        "files": lambda pr: pr.get("changed_files", 0),
    }
    pr_details.sort(
        key=_SORT_KEYS.get(sort_by or "repo", _SORT_KEYS["repo"]),
        reverse=sort_reverse,
    )
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
            render_pr_summary(groups, title, label_header, colour, seasonal_calendar),
            color=colour and _stdout_is_tty(),
        )
        _finish_run(
            t0_total,
            len(pr_details),
            no_update_check=no_update_check,
            show_update_summary=show_update_summary,
            api_stats=api_stats,
            colour=colour,
        )
        return

    if json_output:
        render_json(
            pr_details,
            checks=checks,
            approvals=approvals,
            check_statuses=check_statuses,
            approval_statuses=approval_statuses,
            approval_details=approval_details,
        )
    elif fmt == "markdown":
        render_markdown(
            pr_details,
            age=age,
            checks=checks,
            approvals=approvals,
            check_statuses=check_statuses,
            approval_statuses=approval_statuses,
            approval_details=approval_details,
            head_branch=head_branch,
            base_branch=base_branch,
            status_style=status_style,
        )
    elif fmt == "csv":
        render_csv(
            pr_details,
            age=age,
            checks=checks,
            approvals=approvals,
            check_statuses=check_statuses,
            approval_statuses=approval_statuses,
            approval_details=approval_details,
        )
    elif fmt == "template":
        render_template(
            pr_details,
            template_str=template_str,
            colour=colour,
        )
    else:
        render_table(
            pr_details,
            organizations=organizations,
            legendary=legendary,
            age=age,
            checks=checks,
            approvals=approvals,
            check_statuses=check_statuses,
            approval_statuses=approval_statuses,
            approval_details=approval_details,
            head_branch=head_branch,
            base_branch=base_branch,
            status_style=status_style,
            seasonal_calendar=seasonal_calendar,
            colour=colour,
            colour_index=colour_index,
            max_title_length=max_title_length,
            column_specs=column_specs,
            stdout_is_tty=_stdout_is_tty(),
        )

    _finish_run(
        t0_total,
        len(pr_details),
        no_update_check=no_update_check,
        show_update_summary=show_update_summary,
        api_stats=api_stats,
        colour=colour,
    )


if __name__ == "__main__":
    breakfast()
