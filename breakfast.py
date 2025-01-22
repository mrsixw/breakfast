#!/usr/bin/env python3

import os
import random

import click
import requests
from tabulate import tabulate

GITHUB_API_URL = "https://api.github.com"
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
SECRET_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)

BREAKFAST_ITEMS = [
    "☕️","🥐","🥞","🍳","🥓","🥯","🍩","🍪","🥛","🍵","🍎","🍌",
    "🍉","🍇","🍓","🍒","🍑","🍍","🥖","🥨","🥯","🥞","🧇","🧀",
    "🍗","🥩","🥓","🍔","🍟","🍕","🌭","🥪","🌮","🌯","🥙"]

def make_github_api_request(query_string):
    url = GITHUB_API_URL+query_string
    headers = {
        "Authorization": f"token {SECRET_GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    req = requests.get(url,  headers=headers)
    req.raise_for_status()
    return req.json()

def make_paginated_github_api_requst(query_string, rate=100):
    page, returned = 1, rate
    all_data = []
    while returned >= rate:
        paginated_string = '{}&page={}&per_page={}'.format(query_string, page, rate)
        data = make_github_api_request(paginated_string)
        returned = len(data)
        page = page + 1
        for x in data:
            all_data.append(x)
    return all_data

def make_github_graphql_request(query, variables={}):
    headers = {
        "Authorization": f"Bearer {SECRET_GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "query": query,
        "variables": variables or {}
    }
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
        if not response["data"]["organization"]["repositories"]["pageInfo"]["hasNextPage"]:
            break
        variables["cursor"] = response["data"]["organization"]["repositories"]["pageInfo"]["endCursor"]
        click.echo(random.choices(BREAKFAST_ITEMS)[0], nl=False)
    click.echo("...Done")

    prs = []
    for response in gql_responses:
        for repo in response["data"]["organization"]["repositories"]["nodes"]:
            if repo_filter in repo["name"]:
                for pr in repo["pullRequests"]["nodes"]:
                    prs.append(pr["url"])
    return prs


def click_colour_grade_number(num):
    colour = "red"
    if num < 10:
        colour="green"
    elif num < 20:
        colour="yellow"
    elif num < 50:
        colour=(255, 165,0) # orange

    return click.style(str(num), fg=colour, bold=True)

def generate_terminal_url_anchor(url, url_text="Link"):
    return f"\033]8;;{url}\033\\{url_text}\033]8;;\033\\"


@click.command()
@click.option("--organization", "-o", help="One or multiple organizations to report on")
@click.option("--repo-filter", "-r", help="Filter for specific repp(s)")
def breakfast(organization, repo_filter):
    if SECRET_GITHUB_TOKEN == None:
        click.echo(click.style("GITHUB_TOKEN not set in environment - exiting...", fg="red", bold=True))

    # grab all the pull requests we are interested in
    prs = get_github_prs(organization, repo_filter)

    pr_data = []
    click.echo(f"Processing {repo_filter} PRs...", nl=False)
    for pr in prs:
        url_parts = pr.split("/")
        pr_detail = make_github_api_request(f"/repos/{url_parts[3]}/{url_parts[4]}/pulls/{url_parts[6]}")
        pr_data.append({
                    "Repo": url_parts[4],
                    "PR Title": pr_detail["title"],
                    "Author": pr_detail["user"]["login"],
                    "State": pr_detail["state"],
                    "Files": click_colour_grade_number(pr_detail["changed_files"]),
                    "Commits": click_colour_grade_number(pr_detail["commits"]),
                    "+/-": f"{click.style(f"+{pr_detail["additions"]}", fg="green", bold=True)}/{click.style(f"-{pr_detail['deletions']}", fg="red", bold=True)}",
                    "Comments": click_colour_grade_number(pr_detail["review_comments"]),
                    "Mergeable?": f"{"✅" if pr_detail["mergeable"] else "❌"} ({pr_detail["mergeable_state"]})",
                    "Link": generate_terminal_url_anchor(pr_detail["html_url"],f"PR-{pr_detail['number']}")
                })
        click.echo(random.choices(BREAKFAST_ITEMS)[0], nl=False)
    click.echo("...Done")
    click.echo(tabulate(pr_data, headers="keys", showindex="always", tablefmt="outline"))

if __name__ == '__main__':
    breakfast()

