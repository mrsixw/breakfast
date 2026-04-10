import os
import random
import time
from functools import lru_cache
from urllib.parse import quote

import click
import requests

from .logger import logger
from .ui import BREAKFAST_ITEMS

GITHUB_API_URL = "https://api.github.com"
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
SECRET_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)

_MAX_RETRIES = 3
_RETRY_STATUSES = {502, 503, 504}


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
            t0 = time.monotonic()
            req = requests.get(url, headers=headers)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            if req.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                logger.debug(
                    "api_call type=rest url=%s status=%d"
                    " elapsed_ms=%d attempt=%d retrying",
                    url,
                    req.status_code,
                    elapsed_ms,
                    attempt + 1,
                )
                continue
            req.raise_for_status()
            logger.debug(
                "api_call type=rest url=%s status=%d elapsed_ms=%d",
                url,
                req.status_code,
                elapsed_ms,
            )
            return req.json()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as exc:
            logger.warning(
                "api_call type=rest url=%s error=%r attempt=%d",
                url,
                str(exc),
                attempt + 1,
            )
            if attempt == _MAX_RETRIES:
                raise


def _fetch_pr_detail(pr_url):
    url_parts = pr_url.split("/")
    return make_github_api_request(
        f"/repos/{url_parts[3]}/{url_parts[4]}/pulls/{url_parts[6]}"
    )


def make_paginated_github_api_request(query_string, rate=100):
    """Fetch a paginated GitHub REST resource.

    Args:
        query_string: API path relative to ``GITHUB_API_URL``.
        rate: Number of items to request per page.

    Returns:
        list: Aggregated items from every page until a short page is returned.
    """
    page, returned = 1, rate
    all_data = []
    while returned >= rate:
        separator = "&" if "?" in query_string else "?"
        paginated_string = "{}{}page={}&per_page={}".format(
            query_string, separator, page, rate
        )
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
    for attempt in range(_MAX_RETRIES + 1):
        if attempt:
            time.sleep(2 ** (attempt - 1) + random.uniform(0, 0.5))
        try:
            t0 = time.monotonic()
            response = requests.post(GITHUB_GRAPHQL_URL, json=payload, headers=headers)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            if response.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                logger.debug(
                    "api_call type=graphql status=%d elapsed_ms=%d attempt=%d retrying",
                    response.status_code,
                    elapsed_ms,
                    attempt + 1,
                )
                continue
            response.raise_for_status()
            resp_json = response.json()
            if "errors" in resp_json:
                logger.warning(
                    "api_call type=graphql status=%d elapsed_ms=%d errors=%r",
                    response.status_code,
                    elapsed_ms,
                    resp_json["errors"],
                )
                raise ValueError(f"GraphQL request failed: {resp_json['errors']}")
            logger.debug(
                "api_call type=graphql status=%d elapsed_ms=%d",
                response.status_code,
                elapsed_ms,
            )
            return response.json()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as exc:
            logger.warning(
                "api_call type=graphql url=%s error=%r attempt=%d",
                GITHUB_GRAPHQL_URL,
                str(exc),
                attempt + 1,
            )
            if attempt == _MAX_RETRIES:
                raise


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


def get_authenticated_user_login():
    user = make_github_api_request("/user")
    login = user.get("login")
    if not login:
        raise ValueError("Unable to determine authenticated GitHub user login.")
    return login


def _review_status_from_latest_reviews(owner, repo, pr_number):
    """Aggregate approval state from the latest REST review events.

    Args:
        owner: Repository owner login.
        repo: Repository name.
        pr_number: Pull request number.

    Returns:
        str: One of ``approved``, ``changes``, or ``pending``.
    """
    reviews = make_paginated_github_api_request(
        f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    )

    if not reviews:
        return {"status": "pending", "current": 0}

    latest_by_reviewer = {}
    for review in reviews:
        reviewer = review.get("user", {}).get("login")
        state = review.get("state")
        if reviewer and state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest_by_reviewer[reviewer] = state

    states = set(latest_by_reviewer.values())
    approval_count = sum(
        1 for state in latest_by_reviewer.values() if state == "APPROVED"
    )
    if "CHANGES_REQUESTED" in states:
        status = "changes"
    elif approval_count:
        status = "approved"
    else:
        status = "pending"
    return {"status": status, "current": approval_count}


@lru_cache(maxsize=None)
def get_required_approving_review_count(owner, repo, branch):
    """Return the required approval count for a protected branch.

    Args:
        owner: Repository owner login.
        repo: Repository name.
        branch: Base branch name.

    Returns:
        int | None: Required approval count, or ``None`` when it cannot be
        determined from branch protection data.
    """
    encoded_branch = quote(branch, safe="")
    query_string = (
        f"/repos/{owner}/{repo}/branches/{encoded_branch}"
        "/protection/required_pull_request_reviews"
    )
    try:
        data = make_github_api_request(query_string)
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in (403, 404):
            return None
        raise

    required_count = data.get("required_approving_review_count")
    if isinstance(required_count, int) and required_count > 0:
        return required_count
    return None


def get_approval_summary(owner, repo, pr_number, base_branch=None):
    """Return approval status plus optional obtained/required review counts.

    Args:
        owner: Repository owner login.
        repo: Repository name.
        pr_number: Pull request number.
        base_branch: Base branch name for branch protection lookup.

    Returns:
        dict: Summary with ``status`` and optional ``current`` / ``required``
        review counts.
    """
    review_summary = _review_status_from_latest_reviews(owner, repo, pr_number)
    current_reviews = review_summary["current"]
    required_reviews = None

    if base_branch:
        try:
            required_reviews = get_required_approving_review_count(
                owner, repo, base_branch
            )
        except requests.exceptions.RequestException:
            required_reviews = None

    query = """
    query($owner: String!, $repo: String!, $prNumber: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
          reviewDecision
        }
      }
    }
    """
    variables = {"owner": owner, "repo": repo, "prNumber": pr_number}

    try:
        response = make_github_graphql_request(query, variables)
        review_decision = (
            response.get("data", {})
            .get("repository", {})
            .get("pullRequest", {})
            .get("reviewDecision")
        )
    except (ValueError, requests.exceptions.RequestException):
        review_decision = None

    decision_map = {
        "APPROVED": "approved",
        "CHANGES_REQUESTED": "changes",
        "REVIEW_REQUIRED": "pending",
    }
    status = decision_map.get(review_decision, review_summary["status"])

    if required_reviews is not None and review_decision is None and status != "changes":
        status = "approved" if current_reviews >= required_reviews else "pending"

    if required_reviews is not None and status == "approved":
        current_reviews = max(current_reviews, required_reviews)

    return {
        "status": status,
        "current": current_reviews,
        "required": required_reviews,
    }


def get_approval_status(owner, repo, pr_number, base_branch=None):
    """Get GitHub's current review decision for a pull request.

    Args:
        owner: Repository owner login.
        repo: Repository name.
        pr_number: Pull request number.
        base_branch: Base branch name for branch protection lookup.

    Returns:
        str: One of ``approved``, ``changes``, or ``pending``.

    Notes:
        This prefers GitHub's ``reviewDecision`` so multi-review branch rules do
        not get flattened into a misleading single-approval green state. If the
        GraphQL signal is unavailable, it falls back to the latest REST review
        events.
    """
    query = """
    query($owner: String!, $repo: String!, $prNumber: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
          reviewDecision
        }
      }
    }
    """
    variables = {"owner": owner, "repo": repo, "prNumber": pr_number}

    try:
        response = make_github_graphql_request(query, variables)
        review_decision = (
            response.get("data", {})
            .get("repository", {})
            .get("pullRequest", {})
            .get("reviewDecision")
        )
    except (ValueError, requests.exceptions.RequestException):
        review_decision = None

    decision_map = {
        "APPROVED": "approved",
        "CHANGES_REQUESTED": "changes",
        "REVIEW_REQUIRED": "pending",
    }
    if review_decision in decision_map:
        return decision_map[review_decision]

    return get_approval_summary(owner, repo, pr_number, base_branch)["status"]


def get_check_status(owner, repo, sha):
    # Check Runs API (GitHub Actions, newer CI integrations)
    cr_data = make_github_api_request(f"/repos/{owner}/{repo}/commits/{sha}/check-runs")
    check_runs = cr_data.get("check_runs", [])

    # Commit Status API (Jenkins, older CI integrations)
    status_data = make_github_api_request(f"/repos/{owner}/{repo}/commits/{sha}/status")
    statuses = status_data.get("statuses", [])

    if not check_runs and not statuses:
        return "none"

    # Check runs: look for pending or failures
    for cr in check_runs:
        if cr.get("status") in ("queued", "in_progress"):
            return "pending"

    cr_conclusions = {cr.get("conclusion") for cr in check_runs}
    cr_fail_states = {"failure", "cancelled", "timed_out", "action_required"}

    # Commit statuses: look for pending or failures
    status_states = {s.get("state") for s in statuses}
    status_fail_states = {"failure", "error"}

    if "pending" in status_states:
        return "pending"

    if (cr_conclusions & cr_fail_states) or (status_states & status_fail_states):
        return "fail"

    return "pass"
