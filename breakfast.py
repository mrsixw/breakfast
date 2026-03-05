#!/usr/bin/env python3

import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

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


def generate_terminal_url_anchor(url, url_text="Link"):
    return f"\033]8;;{url}\033\\{url_text}\033]8;;\033\\"


@click.command()
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
    "--mine-only",
    is_flag=True,
    default=False,
    help="Only include PRs authored by the currently authenticated GitHub user.",
)
@click.option(
    "--age",
    is_flag=True,
    default=False,
    help="Include an age column showing PR age in days.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Output results as JSON instead of a table. Progress messages go to stderr.",
)
@click.version_option(package_name="breakfast")
def breakfast(organization, repo_filter, ignore_author, mine_only, age, json_output):
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

    if json_output:
        json_data = []
        for pr_detail in pr_details:
            json_data.append(
                {
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
            )
            click.echo(random.choices(BREAKFAST_ITEMS)[0], nl=False, err=True)
        click.echo("...Done", err=True)
        click.echo(json.dumps(json_data, indent=2))
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


if __name__ == "__main__":
    breakfast()
