import datetime
import fnmatch
import os
import random
import threading
import time
from concurrent.futures import CancelledError
from functools import lru_cache
from urllib.parse import quote, urlparse

import click
import requests

from .logger import logger
from .ui import BREAKFAST_ITEMS

GITHUB_API_URL = "https://api.github.com"
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
SECRET_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", None)


class GitHubRateLimitError(Exception):
    """Raised when a GitHub API rate limit is exhausted.

    Attributes:
        resource: API resource that was rate limited (``rest`` or ``graphql``).
        remaining: Reported remaining requests or points, if available.
        reset_timestamp: Unix reset timestamp, if available.
        reset_time: UTC datetime when the rate limit resets, or None if unknown.
        retry_after: Retry delay reported by GitHub, if available.
    """

    def __init__(
        self,
        reset_time=None,
        *,
        resource="rest",
        remaining=None,
        reset_timestamp=None,
        retry_after=None,
    ):
        self.resource = resource.lower()
        self.remaining = remaining
        self.reset_timestamp = reset_timestamp
        self.reset_time = reset_time
        self.retry_after = retry_after
        if reset_time:
            super().__init__(
                f"GitHub API rate limit exceeded. Try again after {reset_time} UTC."
            )
        else:
            super().__init__("GitHub API rate limit exceeded.")


class OwnerNotFoundError(Exception):
    """Raised when a GitHub owner (org or user) cannot be resolved."""

    def __init__(self, login):
        self.login = login
        super().__init__(
            f"Could not resolve a GitHub organization or user with the login '{login}'."
            " Check that the owner name is correct and your token has access."
        )


_MAX_RETRIES = 3
_RETRY_STATUSES = {502, 503, 504}
_REQUEST_TIMEOUT = (5, 30)

_api_stats_lock = threading.Lock()
_API_STATS_DEFAULTS = {
    "rest_calls": 0,
    "graphql_calls": 0,
    "rest_rate_limit_remaining": None,
    "rest_rate_limit_reset": None,
    "rest_rate_limit_exhausted": False,
    "graphql_rate_limit_remaining": None,
    "graphql_rate_limit_reset": None,
    "graphql_rate_limit_exhausted": False,
}
_api_stats = dict(_API_STATS_DEFAULTS)
_api_request_stop_event = None
_api_request_stop_lock = threading.Lock()


def get_api_stats():
    """Return a snapshot of the current API call statistics."""
    with _api_stats_lock:
        return dict(_api_stats)


def reset_api_stats():
    """Reset API diagnostics for a new CLI invocation."""
    with _api_stats_lock:
        _api_stats.clear()
        _api_stats.update(_API_STATS_DEFAULTS)


def set_api_request_stop_event(stop_event):
    """Register a shared event used to stop a concurrent API request pool."""
    global _api_request_stop_event
    with _api_request_stop_lock:
        _api_request_stop_event = stop_event


def clear_api_request_stop_event(stop_event):
    """Unregister *stop_event* without clearing a newer pool's event."""
    global _api_request_stop_event
    with _api_request_stop_lock:
        if _api_request_stop_event is stop_event:
            _api_request_stop_event = None


def _signal_api_request_stop():
    """Stop queued and subsequent requests after rate-limit detection."""
    with _api_request_stop_lock:
        stop_event = _api_request_stop_event
    if stop_event is not None:
        stop_event.set()


def _raise_if_api_requests_stopped():
    """Abort before an HTTP send when another worker exhausted the limit."""
    with _api_request_stop_lock:
        stop_event = _api_request_stop_event
    if stop_event is not None and stop_event.is_set():
        raise CancelledError("API request cancelled after rate-limit exhaustion")


def _record_api_attempt(resource):
    """Count one attempted HTTP request for API diagnostics."""
    with _api_stats_lock:
        _api_stats[f"{resource}_calls"] += 1


def _parse_int_header(headers, name):
    """Return integer header *name*, or ``None`` when absent or invalid."""
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_rate_limit_headers(resource, headers, *, exhausted=False):
    """Record rate-limit response headers for REST or GraphQL diagnostics."""
    remaining = _parse_int_header(headers, "X-RateLimit-Remaining")
    reset_timestamp = _parse_int_header(headers, "X-RateLimit-Reset")
    with _api_stats_lock:
        if remaining is not None:
            _api_stats[f"{resource}_rate_limit_remaining"] = remaining
        if reset_timestamp is not None:
            _api_stats[f"{resource}_rate_limit_reset"] = reset_timestamp
        if exhausted or remaining == 0:
            _api_stats[f"{resource}_rate_limit_exhausted"] = True


def _payload_is_rate_limited(payload):
    """Return whether a GitHub REST or GraphQL error payload signals throttling."""
    if not isinstance(payload, dict):
        return False

    messages = [str(payload.get("message", ""))]
    errors = payload.get("errors", [])
    if isinstance(errors, list):
        for error in errors:
            if isinstance(error, dict):
                if str(error.get("type", "")).upper() == "RATE_LIMITED":
                    return True
                messages.append(str(error.get("message", "")))
            else:
                messages.append(str(error))

    text = " ".join(messages).lower()
    return (
        "rate limit exceeded" in text
        or "exceeded a secondary rate limit" in text
        or "secondary rate limit exceeded" in text
    )


def _response_json_or_none(response):
    """Return an error response's JSON body when it can be decoded."""
    try:
        return response.json()
    except (AttributeError, ValueError, requests.exceptions.JSONDecodeError):
        return None


def _rate_limit_error_from_response(response, resource, payload=None):
    """Build a typed rate-limit error when *response* indicates exhaustion."""
    headers = getattr(response, "headers", {})
    status_code = getattr(response, "status_code", None)
    remaining = _parse_int_header(headers, "X-RateLimit-Remaining")
    retry_after = headers.get("Retry-After")
    payload_rate_limited = _payload_is_rate_limited(payload)
    rate_limited = status_code == 429 or (
        status_code == 403
        and (remaining == 0 or retry_after is not None or payload_rate_limited)
    )
    if resource == "graphql" and payload_rate_limited:
        rate_limited = True
    if not rate_limited:
        return None

    reset_timestamp = _parse_int_header(headers, "X-RateLimit-Reset")
    reset_time = None
    if reset_timestamp is not None:
        reset_time = datetime.datetime.fromtimestamp(
            reset_timestamp, tz=datetime.timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")
    elif retry_after is not None:
        try:
            retry_seconds = int(retry_after)
        except (TypeError, ValueError):
            retry_seconds = None
        if retry_seconds is not None:
            reset_time = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=retry_seconds)
            ).strftime("%Y-%m-%d %H:%M:%S")

    return GitHubRateLimitError(
        reset_time,
        resource=resource,
        remaining=remaining,
        reset_timestamp=reset_timestamp,
        retry_after=retry_after,
    )


def get_graphql_rate_limit():
    """Query the current GraphQL API rate limit status."""
    query = """
    query {
      rateLimit {
        cost
        remaining
        resetAt
        used
      }
    }
    """
    try:
        response = make_github_graphql_request(query)
        return response.get("data", {}).get("rateLimit")
    except (ValueError, requests.exceptions.RequestException):
        return None


def make_github_api_request(query_string):
    url = GITHUB_API_URL + query_string
    headers = {
        "Authorization": f"token {SECRET_GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    for attempt in range(_MAX_RETRIES + 1):
        _raise_if_api_requests_stopped()
        if attempt:
            time.sleep(2 ** (attempt - 1) + random.uniform(0, 0.5))
        try:
            _raise_if_api_requests_stopped()
            t0 = time.monotonic()
            _record_api_attempt("rest")
            req = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            response_headers = getattr(req, "headers", {})
            _record_rate_limit_headers("rest", response_headers)
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
            error_payload = (
                _response_json_or_none(req) if req.status_code in {403, 429} else None
            )
            rate_limit_error = _rate_limit_error_from_response(
                req, "rest", error_payload
            )
            if rate_limit_error is not None:
                _record_rate_limit_headers("rest", response_headers, exhausted=True)
                _signal_api_request_stop()
                logger.warning(
                    "api_call type=rest url=%s rate_limit_exceeded reset=%s",
                    url,
                    rate_limit_error.reset_time,
                )
                raise rate_limit_error
            req.raise_for_status()
            logger.debug(
                "api_call type=rest url=%s status=%d elapsed_ms=%d",
                url,
                req.status_code,
                elapsed_ms,
            )
            result = req.json()
            return result
        except (
            requests.exceptions.ChunkedEncodingError,
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
    parsed = urlparse(pr_url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 4:
        raise ValueError(f"Unexpected PR URL format: {pr_url!r}")
    owner, repo, pr_num = parts[0], parts[1], parts[3]
    return make_github_api_request(f"/repos/{owner}/{repo}/pulls/{pr_num}")


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


def make_github_graphql_request(query, variables=None):
    headers = {
        "Authorization": f"Bearer {SECRET_GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": variables or {}}
    for attempt in range(_MAX_RETRIES + 1):
        _raise_if_api_requests_stopped()
        if attempt:
            time.sleep(2 ** (attempt - 1) + random.uniform(0, 0.5))
        try:
            _raise_if_api_requests_stopped()
            t0 = time.monotonic()
            _record_api_attempt("graphql")
            response = requests.post(
                GITHUB_GRAPHQL_URL,
                json=payload,
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            response_headers = getattr(response, "headers", {})
            _record_rate_limit_headers("graphql", response_headers)
            if response.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                logger.debug(
                    "api_call type=graphql status=%d elapsed_ms=%d attempt=%d retrying",
                    response.status_code,
                    elapsed_ms,
                    attempt + 1,
                )
                continue
            error_payload = (
                _response_json_or_none(response)
                if response.status_code in {403, 429}
                else None
            )
            rate_limit_error = _rate_limit_error_from_response(
                response, "graphql", error_payload
            )
            if rate_limit_error is not None:
                _record_rate_limit_headers("graphql", response_headers, exhausted=True)
                _signal_api_request_stop()
                logger.warning(
                    "api_call type=graphql rate_limit_exceeded reset=%s",
                    rate_limit_error.reset_time,
                )
                raise rate_limit_error
            response.raise_for_status()
            resp_json = response.json()
            rate_limit_error = _rate_limit_error_from_response(
                response, "graphql", resp_json
            )
            if rate_limit_error is not None:
                _record_rate_limit_headers("graphql", response_headers, exhausted=True)
                _signal_api_request_stop()
                logger.warning(
                    "api_call type=graphql rate_limit_exceeded reset=%s",
                    rate_limit_error.reset_time,
                )
                raise rate_limit_error
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
            return resp_json
        except (
            requests.exceptions.ChunkedEncodingError,
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


_GLOB_CHARS = frozenset("*?[")


def _match_repo_filter(repo_name, repo_filters):
    """Match a repo name against one or more filter patterns (OR logic).

    Each filter uses glob matching when it contains ``*``, ``?``, or ``[``,
    otherwise falls back to substring matching for backwards compatibility.
    An empty list matches all repos.
    """
    if not repo_filters:
        return True
    return any(_match_single_filter(repo_name, f) for f in repo_filters)


def _match_single_filter(repo_name, repo_filter):
    if any(c in repo_filter for c in _GLOB_CHARS):
        return fnmatch.fnmatch(repo_name, repo_filter)
    return repo_filter in repo_name


def _match_exclude_repos(repo_name, exclude_repos):
    """Return True if repo_name matches any exclusion pattern (glob or substring)."""
    if not exclude_repos:
        return False
    for pattern in exclude_repos:
        if any(c in pattern for c in _GLOB_CHARS):
            if fnmatch.fnmatch(repo_name, pattern):
                return True
        elif pattern in repo_name:
            return True
    return False


_FETCH_STATE_MAP = {
    "open": ["OPEN"],
    "closed": ["CLOSED"],
    "merged": ["MERGED"],
    "all": ["OPEN", "CLOSED", "MERGED"],
}


def get_github_prs(owner, repo_filters, fetch_state="open"):
    states_list = _FETCH_STATE_MAP.get(fetch_state.lower(), ["OPEN"])
    states_gql = ", ".join(states_list)
    base_query = f"""
    query($owner: String!, $cursor: String){{
      repositoryOwner(login: $owner){{
        repositories(after: $cursor, first:100){{
          nodes{{
            name
            pullRequests(first:100,states: [{states_gql}]){{
                nodes{{
                    url
                 }}
            }}
          }}
          pageInfo {{
            endCursor
            hasNextPage
          }}
        }}
      }}
    }}
        """
    variables = {"owner": owner}

    gql_responses = []

    click.echo(f"Fetching {owner} PRs...", nl=False, err=True)
    while True:
        response = make_github_graphql_request(base_query, variables)
        if response["data"]["repositoryOwner"] is None:
            raise OwnerNotFoundError(owner)
        gql_responses.append(response)
        page_info = response["data"]["repositoryOwner"]["repositories"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        variables["cursor"] = page_info["endCursor"]
        click.echo(random.choices(BREAKFAST_ITEMS)[0], nl=False, err=True)
    click.echo("...Done", err=True)

    prs = []
    for response in gql_responses:
        for repo in response["data"]["repositoryOwner"]["repositories"]["nodes"]:
            if repo is None:
                continue
            if _match_repo_filter(repo["name"], repo_filters):
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


_REVIEW_DECISION_QUERY = """
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      reviewDecision
    }
  }
}
"""

_REVIEW_DECISION_MAP = {
    "APPROVED": "approved",
    "CHANGES_REQUESTED": "changes",
    "REVIEW_REQUIRED": "pending",
}

_REVIEW_DECISION_SENTINEL = object()


def _fetch_review_decision(owner, repo, pr_number):
    """Return GitHub's ``reviewDecision`` for a PR, or None if unavailable."""
    variables = {"owner": owner, "repo": repo, "prNumber": pr_number}
    try:
        response = make_github_graphql_request(_REVIEW_DECISION_QUERY, variables)
        return (
            response.get("data", {})
            .get("repository", {})
            .get("pullRequest", {})
            .get("reviewDecision")
        )
    except (ValueError, requests.exceptions.RequestException):
        return None


def get_approval_summary(
    owner,
    repo,
    pr_number,
    base_branch=None,
    review_decision=_REVIEW_DECISION_SENTINEL,
):
    """Return approval status plus optional obtained/required review counts.

    Args:
        owner: Repository owner login.
        repo: Repository name.
        pr_number: Pull request number.
        base_branch: Base branch name for branch protection lookup.
        review_decision: Optional pre-fetched GitHub ``reviewDecision`` value.
            When provided (including ``None``), skips the internal GraphQL
            query — used by ``get_approval_status`` to avoid a duplicate call.

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

    if review_decision is _REVIEW_DECISION_SENTINEL:
        review_decision = _fetch_review_decision(owner, repo, pr_number)

    status = _REVIEW_DECISION_MAP.get(review_decision, review_summary["status"])

    if required_reviews is not None and review_decision is None and status != "changes":
        status = "approved" if current_reviews >= required_reviews else "pending"

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
    review_decision = _fetch_review_decision(owner, repo, pr_number)
    if review_decision in _REVIEW_DECISION_MAP:
        return _REVIEW_DECISION_MAP[review_decision]

    return get_approval_summary(
        owner, repo, pr_number, base_branch, review_decision=review_decision
    )["status"]


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

    cr_conclusions = {
        cr["conclusion"] for cr in check_runs if cr.get("conclusion") is not None
    }
    cr_fail_states = {"failure", "cancelled", "timed_out", "action_required"}

    # Commit statuses: look for pending or failures
    status_states = {s.get("state") for s in statuses}
    status_fail_states = {"failure", "error"}

    if "pending" in status_states:
        return "pending"

    if (cr_conclusions & cr_fail_states) or (status_states & status_fail_states):
        return "fail"

    return "pass"


def _pr_days_since(timestamp_str, now=None):
    """Return the number of days since the given ISO 8601 timestamp, or 0 on error."""
    if not timestamp_str:
        return 0
    try:
        dt = datetime.datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    return max((now - dt).days, 0)


def get_pr_age_days(pr_detail, now=None):
    """Return the age in days of a PR since it was created."""
    return _pr_days_since(pr_detail.get("created_at"), now=now)


def get_pr_inactive_days(pr_detail, now=None):
    """Return the number of days since a PR was last updated."""
    return _pr_days_since(pr_detail.get("updated_at"), now=now)
