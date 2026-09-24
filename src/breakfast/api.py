import datetime
import fnmatch
import math
import os
import random
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from functools import lru_cache
from urllib.parse import quote, urlparse

import click
import requests

from .constants import (
    BREAKFAST_ITEMS,
    GITHUB_API_URL,
    GITHUB_GRAPHQL_URL,
    MAX_GRAPHQL_ERROR_MESSAGE_LENGTH,
    MAX_GRAPHQL_ERROR_TYPES,
    MAX_RETRIES,
    MAX_STORED_GRAPHQL_ERRORS,
    REQUEST_TIMEOUT,
    RETRY_STATUSES,
    SEARCH_EARLIEST_CREATED,
    SEARCH_MAX_REPO_QUERIES,
    SEARCH_PAGE_SIZE,
    SEARCH_REPOS_PER_QUERY,
    SEARCH_RESULT_LIMIT,
    SEARCH_SLICE_TARGET,
    SEARCH_WORKERS,
    SECONDARY_RATE_LIMIT_DEFAULT_WAIT,
)
from .logger import logger

__all__ = [
    "GitHubAuthenticationError",
    "GitHubForbiddenError",
    "GitHubGraphQLError",
    "GitHubGraphQLResourceLimitError",
    "GitHubRateLimitError",
    "GitHubSecondaryRateLimitError",
    "OwnerNotFoundError",
    "fetch_pr_detail",
    "get_api_stats",
    "get_approval_status",
    "get_approval_summary",
    "get_authenticated_user_login",
    "get_check_status",
    "get_github_prs",
    "get_graphql_rate_limit",
    "get_pr_age_days",
    "get_pr_inactive_days",
    "get_required_approving_review_count",
    "make_github_api_request",
    "make_github_graphql_request",
    "make_paginated_github_api_request",
    "match_exclude_repos",
]


def _resolve_github_token_info():
    """Resolve the GitHub auth token and variable name, preferring GH_TOKEN."""
    gh_token = os.getenv("GH_TOKEN")
    if gh_token:
        return gh_token, "GH_TOKEN"
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        return github_token, "GITHUB_TOKEN"
    return None, None


def _resolve_github_token():
    """Resolve the GitHub auth token, preferring GH_TOKEN (gh CLI convention)."""
    token, _ = _resolve_github_token_info()
    return token


SECRET_GITHUB_TOKEN, SECRET_GITHUB_TOKEN_VAR = _resolve_github_token_info()


def _summarize_graphql_errors(errors):
    """Return a bounded summary of GraphQL errors grouped by type.

    Args:
        errors: GraphQL error objects returned by GitHub.

    Returns:
        str: Error counts and one representative message per error type.
    """
    counts = {}
    first_messages = {}
    for error in errors:
        if isinstance(error, dict):
            error_type = str(error.get("type") or "UNKNOWN")
            message = str(error.get("message") or "No message provided")
        else:
            error_type = "UNKNOWN"
            message = str(error)
        counts[error_type] = counts.get(error_type, 0) + 1
        first_messages.setdefault(error_type, " ".join(message.split()))

    summaries = []
    error_types = sorted(counts, key=lambda item: (-counts[item], item))
    for error_type in error_types[:MAX_GRAPHQL_ERROR_TYPES]:
        message = first_messages[error_type]
        if len(message) > MAX_GRAPHQL_ERROR_MESSAGE_LENGTH:
            message = f"{message[: MAX_GRAPHQL_ERROR_MESSAGE_LENGTH - 3]}..."
        summaries.append(f"{error_type}={counts[error_type]}: {message}")

    omitted_types = len(counts) - len(summaries)
    if omitted_types > 0:
        summaries.append(f"{omitted_types} additional error type(s)")
    return "; ".join(summaries) or "no error details"


class GitHubGraphQLError(ValueError):
    """Raised when GitHub returns fatal GraphQL errors.

    Attributes:
        error_count: Total number of errors in the response.
        errors: Bounded tuple of representative original error objects.
        summary: Bounded error summary grouped by type.
    """

    def __init__(self, errors):
        self.error_count = len(errors)
        self.errors = tuple(errors[:MAX_STORED_GRAPHQL_ERRORS])
        self.summary = _summarize_graphql_errors(errors)
        super().__init__(f"GraphQL request failed: {self.summary}")


class GitHubGraphQLResourceLimitError(GitHubGraphQLError):
    """Raised when any GitHub GraphQL error reports exhausted resources."""


class GitHubRateLimitError(Exception):
    """Raised when the GitHub REST API rate limit is exhausted.

    Attributes:
        reset_time: UTC datetime when the rate limit resets, or None if unknown.
    """

    def __init__(self, reset_time=None):
        self.reset_time = reset_time
        if reset_time:
            super().__init__(
                f"GitHub API rate limit exceeded. Try again after {reset_time} UTC."
            )
        else:
            super().__init__("GitHub API rate limit exceeded.")


class GitHubSecondaryRateLimitError(GitHubRateLimitError):
    """Raised when GitHub's secondary rate limit outlasts every retry."""

    def __init__(self):
        Exception.__init__(
            self,
            "GitHub's secondary rate limit is still in effect after retrying."
            " Wait a few minutes and try again.",
        )
        self.reset_time = None


class GitHubForbiddenError(requests.exceptions.HTTPError):
    """Raised when GitHub refuses a request for a reason other than rate limits.

    Attributes:
        status_code: The HTTP status GitHub returned.
        github_message: GitHub's explanation from the response body.
    """

    def __init__(self, status_code, github_message, response=None):
        self.status_code = status_code
        self.github_message = github_message
        super().__init__(
            f"GitHub refused the request (HTTP {status_code}): {github_message}",
            response=response,
        )


class OwnerNotFoundError(Exception):
    """Raised when a GitHub owner (org or user) cannot be resolved."""

    def __init__(self, login):
        self.login = login
        super().__init__(
            f"Could not resolve a GitHub organization or user with the login '{login}'."
            " Check that the owner name is correct and your token has access."
        )


class GitHubAuthenticationError(requests.exceptions.HTTPError):
    """Raised when GitHub API authentication fails (HTTP 401).

    Attributes:
        token_var: The name of the environment variable used for auth.
    """

    def __init__(self, message=None, token_var=None, response=None):
        if token_var is None:
            _, resolved_var = _resolve_github_token_info()
            token_var = resolved_var or "GITHUB_TOKEN"
        self.token_var = token_var
        if not message:
            message = (
                f"GitHub authentication failed: {token_var} was rejected (HTTP 401). "
                "Refresh or replace the token and try again."
            )
        super().__init__(message, response=response)


_api_stats_lock = threading.Lock()
_api_stats = {
    "rest_calls": 0,
    "graphql_calls": 0,
    "rest_rate_limit_remaining": None,
    "rest_rate_limit_reset": None,
}


def get_api_stats():
    """Return a snapshot of the current API call statistics."""
    with _api_stats_lock:
        return dict(_api_stats)


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
    for attempt in range(MAX_RETRIES + 1):
        if attempt:
            time.sleep(2 ** (attempt - 1) + random.uniform(0, 0.5))
        try:
            t0 = time.monotonic()
            req = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            if req.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                logger.debug(
                    "api_call type=rest url=%s status=%d"
                    " elapsed_ms=%d attempt=%d retrying",
                    url,
                    req.status_code,
                    elapsed_ms,
                    attempt + 1,
                )
                continue
            if req.status_code == 401:
                _, token_var = _resolve_github_token_info()
                token_var = token_var or "GITHUB_TOKEN"
                logger.warning(
                    "api_call type=rest url=%s auth_failed status=401 token_var=%s",
                    url,
                    token_var,
                )
                raise GitHubAuthenticationError(token_var=token_var, response=req)
            if (
                req.status_code == 403
                and req.headers.get("X-RateLimit-Remaining") == "0"
            ):
                reset_ts = req.headers.get("X-RateLimit-Reset")
                reset_time = None
                if reset_ts:
                    reset_time = datetime.datetime.fromtimestamp(
                        int(reset_ts), tz=datetime.timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S")
                logger.warning(
                    "api_call type=rest url=%s rate_limit_exceeded reset=%s",
                    url,
                    reset_time,
                )
                raise GitHubRateLimitError(reset_time)
            req.raise_for_status()
            logger.debug(
                "api_call type=rest url=%s status=%d elapsed_ms=%d",
                url,
                req.status_code,
                elapsed_ms,
            )
            result = req.json()
            with _api_stats_lock:
                _api_stats["rest_calls"] += 1
                resp_headers = getattr(req, "headers", {})
                remaining = resp_headers.get("X-RateLimit-Remaining")
                reset_ts = resp_headers.get("X-RateLimit-Reset")
                if remaining is not None:
                    _api_stats["rest_rate_limit_remaining"] = int(remaining)
                if reset_ts is not None:
                    _api_stats["rest_rate_limit_reset"] = int(reset_ts)
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
            if attempt == MAX_RETRIES:
                raise


def fetch_pr_detail(pr_url):
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


def _github_error_message(response):
    """Return GitHub's ``message`` from an error response body, if any."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()
    if isinstance(body, dict) and body.get("message"):
        return body["message"]
    return response.text.strip()


def _primary_rate_limit_error(response):
    """Return a rate-limit error if the response exhausted the primary limit."""
    if response.headers.get("X-RateLimit-Remaining") != "0":
        return None
    reset_ts = response.headers.get("X-RateLimit-Reset")
    reset_time = None
    if reset_ts:
        reset_time = datetime.datetime.fromtimestamp(
            int(reset_ts), tz=datetime.timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")
    return GitHubRateLimitError(reset_time)


def _secondary_rate_limit_wait(response):
    """Return seconds to wait out a secondary rate limit, or None if it is not one.

    Follows GitHub's guidance: honour ``retry-after`` when present, otherwise
    wait at least a minute.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return max(int(retry_after), 1)
        except ValueError:
            return SECONDARY_RATE_LIMIT_DEFAULT_WAIT
    if response.status_code == 429:
        return SECONDARY_RATE_LIMIT_DEFAULT_WAIT
    if "secondary rate limit" in _github_error_message(response).lower():
        return SECONDARY_RATE_LIMIT_DEFAULT_WAIT
    return None


# One pause shared by every worker: once GitHub signals a secondary rate limit,
# no GraphQL request goes out until the wait it asked for has passed.
_throttle_lock = threading.Lock()
_throttle_until = 0.0


def _wait_for_slow_down():
    """Sleep until any pause GitHub asked for has passed.

    Re-checks after each sleep, because another worker may have extended the
    pause in the meantime.
    """
    while True:
        with _throttle_lock:
            remaining = _throttle_until - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(remaining)


def _slow_down_for(seconds):
    """Pause every GraphQL request for ``seconds``.

    Returns:
        bool: True if this call started a pause, False if one was already
        running (it is extended if needed), so only one notice is shown when
        several workers hit the limit together.
    """
    global _throttle_until
    with _throttle_lock:
        now = time.monotonic()
        started = _throttle_until <= now
        _throttle_until = max(_throttle_until, now + seconds)
        return started


def make_github_graphql_request(query, variables=None):
    headers = {
        "Authorization": f"Bearer {SECRET_GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": variables or {}}
    back_off = False
    for attempt in range(MAX_RETRIES + 1):
        if back_off:
            time.sleep(2 ** (attempt - 1) + random.uniform(0, 0.5))
        # Every retry backs off unless a slow-down pause already covers it.
        back_off = True
        _wait_for_slow_down()
        try:
            t0 = time.monotonic()
            response = requests.post(
                GITHUB_GRAPHQL_URL,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                logger.debug(
                    "api_call type=graphql status=%d elapsed_ms=%d attempt=%d retrying",
                    response.status_code,
                    elapsed_ms,
                    attempt + 1,
                )
                continue
            if response.status_code == 401:
                _, token_var = _resolve_github_token_info()
                token_var = token_var or "GITHUB_TOKEN"
                logger.warning(
                    "api_call type=graphql auth_failed status=401 token_var=%s",
                    token_var,
                )
                raise GitHubAuthenticationError(token_var=token_var, response=response)
            if response.status_code in (403, 429):
                primary = _primary_rate_limit_error(response)
                if primary is not None:
                    logger.warning(
                        "api_call type=graphql rate_limit_exceeded reset=%s",
                        primary.reset_time,
                    )
                    raise primary
                wait = _secondary_rate_limit_wait(response)
                if wait is None:
                    message = _github_error_message(response)
                    logger.warning(
                        "api_call type=graphql status=%d forbidden message=%r",
                        response.status_code,
                        message,
                    )
                    raise GitHubForbiddenError(
                        response.status_code, message, response=response
                    )
                logger.warning(
                    "api_call type=graphql status=%d secondary_rate_limit"
                    " wait=%ss attempt=%d",
                    response.status_code,
                    wait,
                    attempt + 1,
                )
                started_pause = _slow_down_for(wait)
                if attempt == MAX_RETRIES:
                    raise GitHubSecondaryRateLimitError()
                if started_pause:
                    click.echo(
                        f"\n🐢 GitHub asked breakfast to slow down; waiting {wait}s...",
                        nl=False,
                        err=True,
                    )
                back_off = False
                continue
            response.raise_for_status()
            resp_json = response.json()
            if "errors" in resp_json:
                errors = resp_json["errors"]
                summary = _summarize_graphql_errors(errors)
                logger.warning(
                    "api_call type=graphql status=%d elapsed_ms=%d"
                    " error_count=%d errors=%s",
                    response.status_code,
                    elapsed_ms,
                    len(errors),
                    summary,
                )
                error_types = {
                    error.get("type") if isinstance(error, dict) else None
                    for error in errors
                }
                error_class = GitHubGraphQLError
                if error_types == {"RESOURCE_LIMITS_EXCEEDED"}:
                    error_class = GitHubGraphQLResourceLimitError
                raise error_class(errors)
            logger.debug(
                "api_call type=graphql status=%d elapsed_ms=%d",
                response.status_code,
                elapsed_ms,
            )
            with _api_stats_lock:
                _api_stats["graphql_calls"] += 1
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
            if attempt == MAX_RETRIES:
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


def match_exclude_repos(repo_name, exclude_repos):
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


# Search qualifiers per --fetch-state. GraphQL's CLOSED state means closed
# without merging, which search spells as two qualifiers.
_FETCH_STATE_QUALIFIERS = {
    "open": ["is:open"],
    "closed": ["is:closed", "is:unmerged"],
    "merged": ["is:merged"],
    "all": [],
}

_SEARCH_QUERY = """
query($owner: String!, $searchQuery: String!, $cursor: String,
      $pageSize: Int!, $checkOwner: Boolean!) {
  owner: repositoryOwner(login: $owner) @include(if: $checkOwner) {
    login
  }
  search(type: ISSUE, query: $searchQuery, first: $pageSize, after: $cursor) {
    issueCount
    nodes {
      ... on PullRequest {
        url
        repository { name }
      }
    }
    pageInfo {
      endCursor
      hasNextPage
    }
  }
}
"""

_REPOSITORY_NAMES_QUERY = """
query($owner: String!, $cursor: String, $pageSize: Int!, $archived: Boolean) {
  repositoryOwner(login: $owner) {
    repositories(first: $pageSize, after: $cursor, isArchived: $archived) {
      nodes { name }
      pageInfo {
        endCursor
        hasNextPage
      }
    }
  }
}
"""

_SEARCH_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _build_search_string(scope, fetch_state, include_archived, created=None):
    """Return a GitHub search string for pull requests within a scope.

    Args:
        scope: Search terms naming where to look: ``["org:<owner>"]`` (which
            matches users too) or one ``repo:<owner>/<name>`` term per repo.
        fetch_state: Pull-request state selector.
        include_archived: Whether PRs in archived repositories are included.
        created: Optional inclusive ``(low, high)`` datetime range.

    Returns:
        str: Search qualifiers, oldest PR first so PRs opened mid-run append
        to the last page rather than shifting earlier ones.
    """
    terms = list(scope) + ["is:pr"]
    terms += _FETCH_STATE_QUALIFIERS.get(fetch_state.lower(), ["is:open"])
    if not include_archived:
        terms.append("archived:false")
    if created is not None:
        low, high = (moment.strftime(_SEARCH_TIMESTAMP_FORMAT) for moment in created)
        terms.append(f"created:{low}..{high}")
    terms.append("sort:created-asc")
    return " ".join(terms)


def _request_search_page(owner, search_string, cursor=None, check_owner=False):
    """Return one page of search results as the GraphQL ``data`` object."""
    variables = {
        "owner": owner,
        "searchQuery": search_string,
        "cursor": cursor,
        "pageSize": SEARCH_PAGE_SIZE,
        "checkOwner": check_owner,
    }
    return make_github_graphql_request(_SEARCH_QUERY, variables)["data"]


def _drain_search(owner, search_string, page, on_page=None):
    """Return every node of a search, starting from its already-fetched first page.

    Args:
        owner: GitHub organization or user login.
        search_string: The search the first page was fetched with.
        page: The ``search`` object of the first page.
        on_page: Optional callback run after each further page is fetched.

    Returns:
        list[dict]: Pull-request nodes from every page.
    """
    nodes = list(page["nodes"])
    while page["pageInfo"]["hasNextPage"]:
        cursor = page["pageInfo"]["endCursor"]
        page = _request_search_page(owner, search_string, cursor)["search"]
        nodes.extend(page["nodes"])
        if on_page:
            on_page()
    return nodes


def _search_created_range(owner, scope, fetch_state, include_archived, created):
    """Fetch one ``created:`` slice, or report that it should be split.

    Args:
        owner: GitHub organization or user login.
        scope: Search terms naming where to look.
        fetch_state: Pull-request state selector.
        include_archived: Whether PRs in archived repositories are included.
        created: Inclusive ``(low, high)`` datetime range.

    Returns:
        tuple: ``(nodes, issue_count)``, where ``nodes`` is ``None`` when the
        slice holds more than ``SEARCH_SLICE_TARGET`` results and can still be
        split.
    """
    search_string = _build_search_string(scope, fetch_state, include_archived, created)
    page = _request_search_page(owner, search_string)["search"]
    issue_count = page["issueCount"]
    low, high = created
    if issue_count > SEARCH_SLICE_TARGET and high > low:
        return None, issue_count
    if issue_count > SEARCH_RESULT_LIMIT:
        logger.warning(
            "search_slice_over_cap owner=%s created=%s issue_count=%d limit=%d",
            owner,
            low.strftime(_SEARCH_TIMESTAMP_FORMAT),
            issue_count,
            SEARCH_RESULT_LIMIT,
        )
        click.echo(
            f"\n⚠️  GitHub search can return only {SEARCH_RESULT_LIMIT} of "
            f"{issue_count} {owner} PRs created at "
            f"{low.strftime(_SEARCH_TIMESTAMP_FORMAT)}; the rest are missing.",
            err=True,
        )
    return _drain_search(owner, search_string, page), issue_count


def _split_created_range(created, issue_count):
    """Split an inclusive whole-second range into slices near the target size.

    Args:
        created: Inclusive ``(low, high)`` datetime range, at least two seconds.
        issue_count: Results the range holds, which sets the number of slices.

    Returns:
        list[tuple]: Non-overlapping inclusive ranges covering ``created``.
    """
    low, high = created
    seconds = int((high - low).total_seconds()) + 1
    pieces = min(max(2, math.ceil(issue_count / SEARCH_SLICE_TARGET)), seconds)
    slices = []
    start = 0
    for piece in range(1, pieces + 1):
        end = seconds * piece // pieces - 1
        slices.append(
            (
                low + datetime.timedelta(seconds=start),
                low + datetime.timedelta(seconds=end),
            )
        )
        start = end + 1
    return slices


def _search_in_created_slices(owner, scope, fetch_state, include_archived, count):
    """Collect a large search by fetching ``created:`` slices in parallel.

    A slice that turns out to hold too many results is split again and its
    pieces queued straight away, so no slice waits on an unrelated one.
    """
    earliest = datetime.datetime.fromisoformat(SEARCH_EARLIEST_CREATED)
    # A day of headroom covers clock skew and PRs opened during the run.
    latest = datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0
    ) + datetime.timedelta(days=1)
    nodes = []
    executor = ThreadPoolExecutor(max_workers=SEARCH_WORKERS)

    def submit(created):
        return executor.submit(
            _search_created_range, owner, scope, fetch_state, include_archived, created
        )

    try:
        futures = {
            submit(created): created
            for created in _split_created_range((earliest, latest), count)
        }
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                created = futures.pop(future)
                slice_nodes, slice_count = future.result()
                if slice_nodes is None:
                    for piece in _split_created_range(created, slice_count):
                        futures[submit(piece)] = piece
                    continue
                nodes.extend(slice_nodes)
                click.echo(random.choices(BREAKFAST_ITEMS)[0], nl=False, err=True)
    finally:
        executor.shutdown(cancel_futures=True)
    return nodes


def _collect_search(owner, scope, fetch_state, include_archived, check_owner=False):
    """Return every pull-request node a scoped search matches.

    Raises:
        OwnerNotFoundError: If ``check_owner`` is set and the owner does not
            resolve to a GitHub account.
    """
    search_string = _build_search_string(scope, fetch_state, include_archived)
    data = _request_search_page(owner, search_string, check_owner=check_owner)
    # Search returns nothing, not an error, for an unknown owner.
    if check_owner and data.get("owner") is None:
        raise OwnerNotFoundError(owner)
    page = data["search"]
    if page["issueCount"] > SEARCH_SLICE_TARGET:
        return _search_in_created_slices(
            owner, scope, fetch_state, include_archived, page["issueCount"]
        )
    return _drain_search(
        owner,
        search_string,
        page,
        on_page=lambda: click.echo(
            random.choices(BREAKFAST_ITEMS)[0], nl=False, err=True
        ),
    )


def _list_repository_names(owner, include_archived):
    """Return the names of an owner's repositories.

    Listing costs a request per 100 repositories and does not count against
    GitHub's search limits.

    Raises:
        OwnerNotFoundError: If the owner does not resolve to a GitHub account.
    """
    names = []
    cursor = None
    while True:
        variables = {
            "owner": owner,
            "cursor": cursor,
            "pageSize": SEARCH_PAGE_SIZE,
            # null lists every repository; false leaves archived ones out.
            "archived": None if include_archived else False,
        }
        data = make_github_graphql_request(_REPOSITORY_NAMES_QUERY, variables)["data"]
        if data["repositoryOwner"] is None:
            raise OwnerNotFoundError(owner)
        repositories = data["repositoryOwner"]["repositories"]
        names.extend(node["name"] for node in repositories["nodes"] if node)
        if not repositories["pageInfo"]["hasNextPage"]:
            return names
        cursor = repositories["pageInfo"]["endCursor"]
        click.echo(random.choices(BREAKFAST_ITEMS)[0], nl=False, err=True)


def _repository_names(owner, include_archived, names_cache):
    """Return an owner's repository names, from ``names_cache`` when it has them."""
    if names_cache is not None:
        names = names_cache.read(owner, include_archived)
        if names is not None:
            return names
    names = _list_repository_names(owner, include_archived)
    if names_cache is not None:
        names_cache.write(owner, include_archived, names)
    return names


def _search_scopes(owner, repo_filters, include_archived, names_cache):
    """Return the search scopes that cover an owner's filtered repositories.

    Without filters, or when so many repositories match that per-repo terms
    would cost more requests than searching the owner, the owner is searched
    as a whole and the filters applied to the results.

    Returns:
        list[list[str]]: Search scopes; empty when no repository matches.
    """
    owner_scope = [f"org:{owner}"]
    if not repo_filters:
        return [owner_scope]
    names = _repository_names(owner, include_archived, names_cache)
    matched = [name for name in names if _match_repo_filter(name, repo_filters)]
    if len(matched) > SEARCH_REPOS_PER_QUERY * SEARCH_MAX_REPO_QUERIES:
        return [owner_scope]
    scopes = []
    for start in range(0, len(matched), SEARCH_REPOS_PER_QUERY):
        chunk = matched[start : start + SEARCH_REPOS_PER_QUERY]
        scopes.append([f"repo:{owner}/{name}" for name in chunk])
    return scopes


def get_github_prs(
    owner, repo_filters, fetch_state="open", include_archived=False, names_cache=None
):
    """Return pull-request URLs for an owner using GraphQL search.

    Search costs a request per 100 PRs however many repositories the owner has.
    With repo filters, the owner's repository names are listed first so only
    matching repositories are searched, which keeps busy owners clear of
    GitHub's search rate limits.

    Args:
        owner: GitHub organization or user login.
        repo_filters: Repository name filters, or an empty value for all repos.
        fetch_state: Pull-request state selector.
        include_archived: Whether PRs in archived repositories are included.
        names_cache: Optional store with ``read(owner, include_archived)`` and
            ``write(owner, include_archived, names)`` for repository names.

    Returns:
        list[str]: Matching pull-request URLs, without duplicates.

    Raises:
        OwnerNotFoundError: If the owner does not resolve to a GitHub account.
    """
    click.echo(f"Fetching {owner} PRs...", nl=False, err=True)
    scopes = _search_scopes(owner, repo_filters, include_archived, names_cache)
    nodes = []
    for index, scope in enumerate(scopes):
        # The first search also confirms the owner exists; cached repository
        # names can outlive it.
        check_owner = index == 0
        nodes.extend(
            _collect_search(owner, scope, fetch_state, include_archived, check_owner)
        )
    click.echo("...Done", err=True)

    prs = []
    seen = set()
    for node in nodes:
        repository = (node or {}).get("repository")
        if repository is None or node["url"] in seen:
            continue
        seen.add(node["url"])
        if _match_repo_filter(repository["name"], repo_filters):
            prs.append(node["url"])
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
