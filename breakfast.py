#!/usr/bin/env python3

import json
import os
import random
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path

import click
import requests
from tabulate import tabulate

GITHUB_API_URL = "https://api.github.com"
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
SECRET_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)

_MAX_RETRIES = 3
_RETRY_STATUSES = {502, 503, 504}

BREAKFAST_ITEMS = [
    "☕️",
    "🥐",
    "🥞",
    "🍳",
    "🥓",
    "🥯",
    "🍩",
    "🍪",
    "🥛",
    "🍵",
    "🍎",
    "🍌",
    "🍉",
    "🍇",
    "🍓",
    "🍒",
    "🍑",
    "🍍",
    "🥖",
    "🥨",
    "🥯",
    "🥞",
    "🧇",
    "🧀",
    "🍗",
    "🥩",
    "🥓",
    "🍔",
    "🍟",
    "🍕",
    "🌭",
    "🥪",
    "🌮",
    "🌯",
    "🥙",
]


def make_github_api_request(query_string):
    url = GITHUB_API_URL + query_string
    headers = {
        "Authorization": f"token {SECRET_GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    for attempt in range(_MAX_RETRIES + 1):
        if attempt:
            time.sleep(2 ** (attempt - 1) + random.uniform(0, 0.5))
        try:
            req = requests.get(url, headers=headers)
            if req.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                continue
            req.raise_for_status()
            return req.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == _MAX_RETRIES:
                raise


def _fetch_pr_detail(pr_url):
    url_parts = pr_url.split("/")
    return make_github_api_request(
        f"/repos/{url_parts[3]}/{url_parts[4]}/pulls/{url_parts[6]}"
    )


def make_paginated_github_api_requst(query_string, rate=100):
    page, returned = 1, rate
    all_data = []
    while returned >= rate:
        paginated_string = "{}&page={}&per_page={}".format(query_string, page, rate)
        data = make_github_api_request(paginated_string)
        returned = len(data)
        page = page + 1
        for x in data:
            all_data.append(x)
    return all_data


def make_github_graphql_request(query, variables={}):
    headers = {
        "Authorization": f"Bearer {SECRET_GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": variables or {}}
    response = requests.post(GITHUB_GRAPHQL_URL, json=payload, headers=headers)
    response.raise_for_status()

    resp_json = response.json()
    if "errors" in resp_json:
        raise ValueError(f"GraphQL request failed: {resp_json['errors']}")

    return response.json()


def make_paginated_github_graphql_request():
    pass


def get_github_prs(organization, repo_filter):
    base_query = """
    query($organization: String!, $cursor: String){
      organization(login: $organization){
        repositories(after: $cursor, first:100){
          nodes{
            name
            pullRequests(first:100,states: [OPEN]){
                nodes{
                    url
                 }
            }
          }
          pageInfo {
            endCursor
            hasNextPage
          }
        }
      }
    }
        """
    variables = {"organization": organization}

    gql_responses = []

    click.echo(f"Fetching {organization} PRs...", nl=False)
    while True:
        response = make_github_graphql_request(base_query, variables)
        gql_responses.append(response)
        page_info = response["data"]["organization"]["repositories"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        variables["cursor"] = page_info["endCursor"]
        click.echo(random.choices(BREAKFAST_ITEMS)[0], nl=False)
    click.echo("...Done")

    prs = []
    for response in gql_responses:
        for repo in response["data"]["organization"]["repositories"]["nodes"]:
            if repo_filter in repo["name"]:
                for pr in repo["pullRequests"]["nodes"]:
                    prs.append(pr["url"])
    return prs


def normalize_ignore_authors(ignore_authors):
    if not ignore_authors:
        return set()
    return {
        author.strip().lower() for author in ignore_authors if author and author.strip()
    }


def get_authenticated_user_login():
    user = make_github_api_request("/user")
    login = user.get("login")
    if not login:
        raise ValueError("Unable to determine authenticated GitHub user login.")
    return login


def filter_pr_details(
    pr_details,
    ignore_authors,
    mine_only=False,
    current_user_login=None,
):
    ignore_set = normalize_ignore_authors(ignore_authors)
    current_user_login_normalized = (
        current_user_login.lower()
        if mine_only and current_user_login and current_user_login.strip()
        else None
    )

    if not ignore_set and not current_user_login_normalized:
        return pr_details

    filtered = []
    for pr_detail in pr_details:
        author_login = pr_detail.get("user", {}).get("login", "")
        author_login_normalized = author_login.lower()
        if author_login_normalized in ignore_set:
            continue
        if (
            current_user_login_normalized
            and author_login_normalized != current_user_login_normalized
        ):
            continue
        filtered.append(pr_detail)
    return filtered


def click_colour_grade_number(num):
    colour = "red"
    if num < 10:
        colour = "green"
    elif num < 20:
        colour = "yellow"
    elif num < 50:
        colour = (255, 165, 0)  # orange

    return click.style(str(num), fg=colour, bold=True)


def get_pr_age_days(pr_detail, now=None):
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


def get_check_status(owner, repo, sha):
    data = make_github_api_request(f"/repos/{owner}/{repo}/commits/{sha}/check-runs")
    check_runs = data.get("check_runs", [])
    if not check_runs:
        return "none"

    for cr in check_runs:
        if cr.get("status") in ("queued", "in_progress"):
            return "pending"

    conclusions = {cr.get("conclusion") for cr in check_runs}
    fail_states = {"failure", "cancelled", "timed_out", "action_required"}
    if conclusions & fail_states:
        return "fail"

    return "pass"


def format_check_status(status):
    styles = {
        "pass": ("green", "✅ pass"),
        "fail": ("red", "❌ fail"),
        "pending": ("yellow", "⚠️ pending"),
        "none": ("white", "➖ none"),
    }
    colour, text = styles.get(status, ("white", status))
    return click.style(text, fg=colour, bold=True)


_UPDATE_CHECK_REPO = "mrsixw/breakfast"
_CACHE_DIR = Path.home() / ".cache" / "breakfast"
_CACHE_TTL_SECONDS = 86400  # 24 hours


def _read_version_cache():
    cache_file = _CACHE_DIR / "latest_version.json"
    try:
        if not cache_file.exists():
            return None
        data = json.loads(cache_file.read_text())
        cached_at = datetime.fromisoformat(data["checked_at"])
        age = (datetime.now(timezone.utc) - cached_at).total_seconds()
        if age > _CACHE_TTL_SECONDS:
            return None
        return data.get("latest_version")
    except Exception:
        return None


def _write_version_cache(latest_version):
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = _CACHE_DIR / "latest_version.json"
        cache_file.write_text(
            json.dumps(
                {
                    "latest_version": latest_version,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
    except Exception:
        pass


def get_latest_version():
    cached = _read_version_cache()
    if cached:
        return cached
    try:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if SECRET_GITHUB_TOKEN:
            headers["Authorization"] = f"token {SECRET_GITHUB_TOKEN}"
        resp = requests.get(
            f"https://api.github.com/repos/{_UPDATE_CHECK_REPO}/releases/latest",
            headers=headers,
            timeout=5,
        )
        resp.raise_for_status()
        tag = resp.json().get("tag_name", "")
        latest = tag.lstrip("v")
        _write_version_cache(latest)
        return latest
    except Exception:
        return None


def _parse_version_tuple(version_str):
    try:
        return tuple(int(x) for x in version_str.split("."))
    except (ValueError, AttributeError):
        return ()


def check_for_update():
    try:
        current = pkg_version("breakfast")
        latest = get_latest_version()
        if not latest:
            return None
        if _parse_version_tuple(latest) > _parse_version_tuple(current):
            return (
                f"🍳 A fresh breakfast is ready! "
                f"v{current} → v{latest} "
                f"— update at https://github.com/{_UPDATE_CHECK_REPO}/releases/latest"
            )
        return None
    except Exception:
        return None


def load_config(config_path=None):
    if config_path:
        paths = [Path(config_path)]
    else:
        paths = [
            Path(".breakfast.toml"),
            Path.home() / ".config" / "breakfast" / "config.toml",
        ]

    merged = {}
    for path in reversed(paths):
        if path.exists():
            with open(path, "rb") as f:
                try:
                    data = tomllib.load(f)
                except Exception as e:
                    msg = f"Warning: Failed to parse config {path}: {e}"
                    click.echo(click.style(msg, fg="yellow"), err=True)
                    continue
            for key, value in data.items():
                if isinstance(value, list) and isinstance(merged.get(key), list):
                    merged[key] = value + merged[key]
                else:
                    merged[key] = value
    return merged


def generate_terminal_url_anchor(url, url_text="Link"):
    return f"\033]8;;{url}\033\\{url_text}\033]8;;\033\\"


@click.command()
@click.option("--config", help="Path to config file.")
@click.option("--show-config", is_flag=True, help="Print the resolved config and exit.")
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
@click.version_option(package_name="breakfast")
def breakfast(
    config,
    show_config,
    organization,
    repo_filter,
    ignore_author,
    no_ignore_author,
    mine_only,
    age,
    json_output,
    checks,
    no_update_check,
):
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
    prs = get_github_prs(organization, repo_filter)

    pr_data = []
    click.echo(f"Processing {repo_filter} PRs...", nl=False, err=json_output)
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
                check_futures.append((pr_detail["number"], future))
        for pr_number, future in check_futures:
            try:
                check_statuses[pr_number] = future.result()
            except Exception:
                check_statuses[pr_number] = "none"

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
                entry["checks"] = check_statuses.get(pr_detail["number"], "none")
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

        # For compat with python versions < 3.12, f-strings get more powerful.
        # Until then, we'll preformat some of the strings in advance.
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
                check_statuses.get(pr_detail["number"], "none")
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
