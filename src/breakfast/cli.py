import json
import random
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor

import click
from tabulate import tabulate

from .api import (
    SECRET_GITHUB_TOKEN,
    _fetch_pr_detail,
    get_authenticated_user_login,
    get_check_status,
    get_github_prs,
)
from .cache import parse_ttl, read_pr_cache, write_pr_cache
from .config import filter_pr_details, generate_default_config, load_config
from .ui import (
    BREAKFAST_ITEMS,
    click_colour_grade_number,
    format_check_status,
    format_mergeable_status,
    generate_terminal_url_anchor,
)
from .updater import check_for_update

# Columns dropped as last resort (least important first)
_DROPPABLE_COLUMNS = ["State", "Commits", "Files", "+/-", "Cmt", "Age", "Checks"]

_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;]*[mK]|\]8;;[^\x1b]*\x1b\\)")


def _strip_ansi(s):
    return _ANSI_RE.sub("", str(s))


def _table_width(rows):
    """Return visual table width via the border line (ANSI-stripped for accuracy)."""
    plain_rows = [{k: _strip_ansi(v) for k, v in row.items()} for row in rows]
    table_str = tabulate(
        plain_rows, headers="keys", showindex="always", tablefmt="outline"
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
            key: (
                row[key][: limit - 1] + "…"
                if len(_strip_ansi(row[key])) > limit
                else row[key]
            ),
        }
        for row in pr_data
    ]


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

    # 2. Truncate Repo
    pr_data = _truncate_col(pr_data, "Repo", terminal_width, min_len=8)
    if fits():
        return pr_data

    # 3. Truncate Author
    pr_data = _truncate_col(pr_data, "Author", terminal_width, min_len=8)
    if fits():
        return pr_data

    # 4. Compress Mergeable?: drop the reason suffix
    if "Mergeable?" in pr_data[0]:
        pr_data = [
            {**row, "Mergeable?": re.sub(r" \(.*\)$", "", row["Mergeable?"])}
            for row in pr_data
        ]
    if fits():
        return pr_data

    # 5. Compress Checks: "✅ pass" → "✅", "pending" → "pending"
    if "Checks" in pr_data[0]:
        pr_data = [
            {**row, "Checks": _strip_ansi(row["Checks"]).split()[0]} for row in pr_data
        ]
    if fits():
        return pr_data

    # 6. Rename "Comments" → "Cmt" (shorter header)
    if "Comments" in pr_data[0]:
        pr_data = [
            {("Cmt" if k == "Comments" else k): v for k, v in row.items()}
            for row in pr_data
        ]
    if fits():
        return pr_data

    # 7. Drop low-priority columns as last resort
    for col in _DROPPABLE_COLUMNS:
        if fits():
            break
        if col in pr_data[0]:
            pr_data = [{k: v for k, v in row.items() if k != col} for row in pr_data]

    return pr_data


def _stdout_is_tty():
    return sys.stdout.isatty()


def get_pr_age_days(pr_detail, now=None):
    from datetime import datetime, timezone

    created_at = pr_detail.get("created_at")
    if not created_at:
        return 0

    try:
        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return 0

    if created_dt.tzinfo is None:
        created_dt = created_dt.replace(tzinfo=timezone.utc)
    if now is None:
        now = datetime.now(timezone.utc)

    return max((now - created_dt).days, 0)


@click.command()
@click.option("--config", help="Path to config file.")
@click.option("--show-config", is_flag=True, help="Print the resolved config and exit.")
@click.option(
    "--init-config", is_flag=True, help="Generate a default config file and exit."
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
    "--age/--no-age",
    default=None,
    help="Include an age column showing PR age in days.",
)
@click.option(
    "--json/--no-json",
    "json_output",
    default=None,
    help="Output results as JSON instead of a table. Progress messages go to stderr.",
)
@click.option(
    "--checks/--no-checks",
    default=None,
    help="Include a checks column showing CI/check status for each PR.",
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
    "--no-cache",
    is_flag=True,
    default=False,
    help="Skip reading and writing the PR cache; always fetch fresh.",
)
@click.version_option(package_name="breakfast")
def breakfast(
    config,
    show_config,
    init_config,
    organization,
    repo_filter,
    ignore_author,
    no_ignore_author,
    mine_only,
    age,
    json_output,
    checks,
    status_style,
    limit,
    max_title_length,
    no_update_check,
    cache_ttl,
    no_cache,
):
    if init_config:
        generate_default_config()
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
    age = age if age is not None else cfg.get("age", False)
    if json_output is None:
        json_output = cfg.get("format") == "json"
    checks = checks if checks is not None else cfg.get("checks", False)
    if status_style is None:
        status_style = str(cfg.get("status-style", "emoji")).lower()
    max_title_length = (
        max_title_length
        if max_title_length is not None
        else cfg.get("max-title-length")
    )
    if status_style not in {"emoji", "ascii"}:
        status_style = "emoji"

    # Resolve effective cache TTL: CLI > config > default 300
    raw_ttl = cache_ttl if cache_ttl is not None else cfg.get("cache-ttl", 300)
    try:
        cache_ttl_seconds = parse_ttl(raw_ttl)
    except ValueError as exc:
        msg = f"Error: invalid --cache-ttl value: {exc}"
        click.echo(click.style(msg, fg="red", bold=True))
        sys.exit(1)

    if show_config:
        click.echo("Resolved config:")
        resolved = {
            "organization": organization,
            "repo-filter": repo_filter,
            "ignore-author": ignore_author,
            "mine-only": mine_only,
            "age": age,
            "json": json_output,
            "checks": checks,
            "status-style": status_style,
            "max-title-length": max_title_length,
            "cache-ttl": cache_ttl_seconds,
            "no-cache": no_cache,
        }
        for k, v in resolved.items():
            click.echo(f"  {k}: {v}")
        sys.exit(0)

    if not organization:
        message = (
            "Organization must be provided via CLI (-o) "
            "or config file (organization)."
        )
        click.echo(click.style(message, fg="red", bold=True))
        sys.exit(1)

    if SECRET_GITHUB_TOKEN is None:
        message = "GITHUB_TOKEN not set in environment - exiting..."
        click.echo(click.style(message, fg="red", bold=True))
        sys.exit(1)
    current_user_login = None
    if mine_only:
        current_user_login = get_authenticated_user_login()

    # grab all the pull requests we are interested in
    pr_data = []

    pr_details = None
    served_from_cache = False
    if not no_cache:
        pr_details = read_pr_cache(organization, repo_filter, cache_ttl_seconds)
        served_from_cache = pr_details is not None

    if pr_details is None:
        prs = get_github_prs(organization, repo_filter)
        pr_details = []
        failed_urls = []
        if prs:
            max_workers = min(8, len(prs))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [(url, executor.submit(_fetch_pr_detail, url)) for url in prs]
            for url, future in futures:
                try:
                    pr_details.append(future.result())
                except Exception:
                    failed_urls.append(url)
        if failed_urls:
            examples = ", ".join(failed_urls[:3])
            suffix = " ..." if len(failed_urls) > 3 else ""
            msg = (
                f"\nWarning: {len(failed_urls)} PR(s) could not be fetched"
                f" after retries: {examples}{suffix}"
            )
            click.echo(click.style(msg, fg="yellow"), err=True)
        if not no_cache:
            write_pr_cache(organization, repo_filter, pr_details)

    click.echo(f"Processing {repo_filter} PRs...", nl=False, err=json_output)
    pr_details = filter_pr_details(
        pr_details,
        ignore_author,
        mine_only=mine_only,
        current_user_login=current_user_login,
    )
    if limit is not None:
        pr_details = pr_details[:limit]

    check_statuses = {}
    if checks and pr_details:
        max_workers = min(8, len(pr_details))
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
            except Exception:
                check_statuses[pr_id] = "none"

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
            json_data.append(entry)
            if not served_from_cache:
                click.echo(random.choices(BREAKFAST_ITEMS)[0], nl=False, err=True)
        click.echo("⚡...Done" if served_from_cache else "...Done", err=True)
        click.echo(json.dumps(json_data, indent=2))
        if not no_update_check:
            update_msg = check_for_update()
            if update_msg:
                click.echo(click.style(update_msg, fg="cyan", bold=True), err=True)
        return

    for pr_detail in pr_details:
        adds = click.style("+" + str(pr_detail["additions"]), fg="green", bold=True)
        subs = click.style("-" + str(pr_detail["deletions"]), fg="red", bold=True)

        row = {
            "Repo": pr_detail["base"]["repo"]["name"],
            "PR Title": pr_detail["title"],
            "Author": pr_detail["user"]["login"],
            "State": pr_detail["state"],
            "Files": click_colour_grade_number(pr_detail["changed_files"]),
            "Commits": click_colour_grade_number(pr_detail["commits"]),
            "+/-": f"{adds}/{subs}",
            "Comments": click_colour_grade_number(pr_detail["review_comments"]),
        }
        if age:
            row["Age"] = click_colour_grade_number(get_pr_age_days(pr_detail))
        if checks:
            row["Checks"] = format_check_status(
                check_statuses.get(pr_detail["id"], "none"),
                style=status_style,
            )
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
        if not served_from_cache:
            click.echo(random.choices(BREAKFAST_ITEMS)[0], nl=False)
    click.echo("⚡...Done" if served_from_cache else "...Done")

    # Apply explicit title truncation, then auto-fit to terminal if interactive
    if max_title_length:
        pr_data = [
            {
                **row,
                "PR Title": (
                    row["PR Title"][: max_title_length - 1] + "…"
                    if len(row["PR Title"]) > max_title_length
                    else row["PR Title"]
                ),
            }
            for row in pr_data
        ]
    if _stdout_is_tty() and pr_data:
        terminal_width = shutil.get_terminal_size().columns
        pr_data = _auto_fit(pr_data, terminal_width, max_title_length)

    click.echo(
        tabulate(pr_data, headers="keys", showindex="always", tablefmt="outline")
    )

    if not no_update_check:
        update_msg = check_for_update()
        if update_msg:
            click.echo(click.style(update_msg, fg="cyan", bold=True), err=True)


if __name__ == "__main__":
    breakfast()
