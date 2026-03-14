import json
import random
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
    generate_terminal_url_anchor,
)
from .updater import check_for_update


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
    click.echo(f"Processing {repo_filter} PRs...", nl=False, err=json_output)

    pr_details = None
    if not no_cache:
        pr_details = read_pr_cache(organization, repo_filter, cache_ttl_seconds)

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
    pr_details = filter_pr_details(
        pr_details,
        ignore_author,
        mine_only=mine_only,
        current_user_login=current_user_login,
    )

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
            click.echo(random.choices(BREAKFAST_ITEMS)[0], nl=False, err=True)
        click.echo("...Done", err=True)
        click.echo(json.dumps(json_data, indent=2))
        if not no_update_check:
            update_msg = check_for_update()
            if update_msg:
                click.echo(click.style(update_msg, fg="cyan", bold=True), err=True)
        return

    for pr_detail in pr_details:
        mergable = "✅" if pr_detail["mergeable"] else "❌"
        mergable_state = pr_detail["mergeable_state"]
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
                check_statuses.get(pr_detail["id"], "none")
            )
        row["Mergeable?"] = f"{mergable} ({mergable_state})"
        row["Link"] = generate_terminal_url_anchor(
            pr_detail["html_url"],
            f"PR-{pr_detail['number']}",
        )
        pr_data.append(row)
        click.echo(random.choices(BREAKFAST_ITEMS)[0], nl=False)
    click.echo("...Done")
    click.echo(
        tabulate(pr_data, headers="keys", showindex="always", tablefmt="outline")
    )

    if not no_update_check:
        update_msg = check_for_update()
        if update_msg:
            click.echo(click.style(update_msg, fg="cyan", bold=True), err=True)


if __name__ == "__main__":
    breakfast()
