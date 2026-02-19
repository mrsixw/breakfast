#!/usr/bin/env python3

import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import click
import requests
from tabulate import tabulate

GITHUB_API_URL = "https://api.github.com"
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
SECRET_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)

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
    req = requests.get(url, headers=headers)
    req.raise_for_status()
    return req.json()


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


def filter_pr_details(pr_details, ignore_authors):
    ignore_set = normalize_ignore_authors(ignore_authors)
    if not ignore_set:
        return pr_details

    filtered = []
    for pr_detail in pr_details:
        author_login = pr_detail.get("user", {}).get("login", "")
        if author_login.lower() in ignore_set:
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
    "--age",
    is_flag=True,
    default=False,
    help="Include an age column showing PR age in days.",
)
@click.version_option(package_name="breakfast")
def breakfast(organization, repo_filter, ignore_author, age):
    if SECRET_GITHUB_TOKEN is None:
        message = "GITHUB_TOKEN not set in environment - exiting..."
        click.echo(click.style(message, fg="red", bold=True))
        sys.exit(1)
    # grab all the pull requests we are interested in
    prs = get_github_prs(organization, repo_filter)

    pr_data = []
    click.echo(f"Processing {repo_filter} PRs...", nl=False)
    pr_details = []
    if prs:
        max_workers = min(8, len(prs))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            pr_details = list(executor.map(_fetch_pr_detail, prs))
    pr_details = filter_pr_details(pr_details, ignore_author)
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
