import pytest
import requests

from breakfast import api


def test_make_github_api_request_retries_on_connection_error(monkeypatch):
    attempts = []
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    class GoodResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def fake_get(url, headers):
        attempts.append(1)
        if len(attempts) < 3:
            raise requests.exceptions.ConnectionError("reset")
        return GoodResponse()

    monkeypatch.setattr(api.requests, "get", fake_get)

    result = api.make_github_api_request("/repos/org/repo")

    assert result == {"ok": True}
    assert len(attempts) == 3


def test_make_github_api_request_raises_after_max_retries_connection_error(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    def fake_get(url, headers):
        raise requests.exceptions.ConnectionError("reset")

    monkeypatch.setattr(api.requests, "get", fake_get)

    with pytest.raises(requests.exceptions.ConnectionError):
        api.make_github_api_request("/repos/org/repo")


def test_make_github_api_request_retries_on_502(monkeypatch):
    attempts = []
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    class BadGateway:
        status_code = 502

        def raise_for_status(self):
            raise requests.exceptions.HTTPError("502")

        def json(self):
            return {}

    class GoodResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def fake_get(url, headers):
        attempts.append(1)
        return BadGateway() if len(attempts) < 3 else GoodResponse()

    monkeypatch.setattr(api.requests, "get", fake_get)

    result = api.make_github_api_request("/repos/org/repo")

    assert result == {"ok": True}
    assert len(attempts) == 3


def test_make_github_api_request_raises_after_max_retries_502(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    class BadGateway:
        status_code = 502

        def raise_for_status(self):
            raise requests.exceptions.HTTPError("502")

        def json(self):
            return {}

    monkeypatch.setattr(api.requests, "get", lambda url, headers: BadGateway())

    with pytest.raises(requests.exceptions.HTTPError):
        api.make_github_api_request("/repos/org/repo")


def test_make_github_api_request_builds_headers_and_url(monkeypatch):
    calls = {}

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_get(url, headers):
        calls["url"] = url
        calls["headers"] = headers
        return DummyResponse()

    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.requests, "get", fake_get)

    result = api.make_github_api_request("/repos/org/repo")

    assert result == {"ok": True}
    assert calls["url"] == f"{api.GITHUB_API_URL}/repos/org/repo"
    assert calls["headers"]["Authorization"] == "token token-123"
    assert calls["headers"]["Accept"] == "application/vnd.github.v3+json"


def test_get_github_prs_filters_and_paginates(monkeypatch):
    responses = [
        {
            "data": {
                "organization": {
                    "repositories": {
                        "nodes": [
                            {
                                "name": "app-one",
                                "pullRequests": {
                                    "nodes": [
                                        {
                                            "url": "https://example.com/app-one/1",
                                        }
                                    ]
                                },
                            },
                            {
                                "name": "other",
                                "pullRequests": {
                                    "nodes": [
                                        {
                                            "url": "https://example.com/other/2",
                                        }
                                    ]
                                },
                            },
                        ],
                        "pageInfo": {"endCursor": "cursor-1", "hasNextPage": True},
                    }
                }
            }
        },
        {
            "data": {
                "organization": {
                    "repositories": {
                        "nodes": [
                            {
                                "name": "app-two",
                                "pullRequests": {
                                    "nodes": [
                                        {
                                            "url": "https://example.com/app-two/3",
                                        }
                                    ]
                                },
                            }
                        ],
                        "pageInfo": {"endCursor": "cursor-2", "hasNextPage": False},
                    }
                }
            }
        },
    ]
    iterator = iter(responses)

    def fake_graphql_request(_query, _variables):
        return next(iterator)

    monkeypatch.setattr(api, "make_github_graphql_request", fake_graphql_request)
    monkeypatch.setattr(api, "BREAKFAST_ITEMS", ["*"])

    prs = api.get_github_prs("org", "app")

    assert prs == [
        "https://example.com/app-one/1",
        "https://example.com/app-two/3",
    ]


def test_get_authenticated_user_login(monkeypatch):
    monkeypatch.setattr(
        api,
        "make_github_api_request",
        lambda _path: {"login": "alice"},
    )

    assert api.get_authenticated_user_login() == "alice"


def test_get_authenticated_user_login_missing_login(monkeypatch):
    monkeypatch.setattr(api, "make_github_api_request", lambda _path: {})

    with pytest.raises(
        ValueError,
        match="Unable to determine authenticated GitHub user",
    ):
        api.get_authenticated_user_login()


def test_make_paginated_github_api_request_adds_initial_query_separator(monkeypatch):
    calls = []

    def fake_api(path):
        calls.append(path)
        if path.endswith("page=1&per_page=2"):
            return [{"id": 1}, {"id": 2}]
        if path.endswith("page=2&per_page=2"):
            return [{"id": 3}]
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(api, "make_github_api_request", fake_api)

    result = api.make_paginated_github_api_request(
        "/repos/org/repo/pulls/1/reviews",
        rate=2,
    )

    assert result == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert calls == [
        "/repos/org/repo/pulls/1/reviews?page=1&per_page=2",
        "/repos/org/repo/pulls/1/reviews?page=2&per_page=2",
    ]


def test_get_check_status_all_success(monkeypatch):
    def fake_api(path):
        if "check-runs" in path:
            return {
                "check_runs": [
                    {"status": "completed", "conclusion": "success"},
                    {"status": "completed", "conclusion": "skipped"},
                ]
            }
        return {"statuses": []}

    monkeypatch.setattr(api, "make_github_api_request", fake_api)
    assert api.get_check_status("org", "repo", "abc123") == "pass"


def test_get_check_status_failure(monkeypatch):
    def fake_api(path):
        if "check-runs" in path:
            return {
                "check_runs": [
                    {"status": "completed", "conclusion": "success"},
                    {"status": "completed", "conclusion": "failure"},
                ]
            }
        return {"statuses": []}

    monkeypatch.setattr(api, "make_github_api_request", fake_api)
    assert api.get_check_status("org", "repo", "abc123") == "fail"


def test_get_check_status_pending(monkeypatch):
    def fake_api(path):
        if "check-runs" in path:
            return {
                "check_runs": [
                    {"status": "completed", "conclusion": "success"},
                    {"status": "in_progress", "conclusion": None},
                ]
            }
        return {"statuses": []}

    monkeypatch.setattr(api, "make_github_api_request", fake_api)
    assert api.get_check_status("org", "repo", "abc123") == "pending"


def test_get_check_status_none(monkeypatch):
    def fake_api(path):
        if "check-runs" in path:
            return {"check_runs": []}
        return {"statuses": []}

    monkeypatch.setattr(api, "make_github_api_request", fake_api)
    assert api.get_check_status("org", "repo", "abc123") == "none"


def test_get_check_status_commit_status_failure(monkeypatch):
    """Jenkins-style CI uses the commit status API, not check runs."""

    def fake_api(path):
        if "check-runs" in path:
            return {"check_runs": []}
        return {
            "statuses": [
                {"context": "ci/jenkins/branch", "state": "success"},
                {"context": "ci/jenkins/pr-merge", "state": "error"},
            ]
        }

    monkeypatch.setattr(api, "make_github_api_request", fake_api)
    assert api.get_check_status("org", "repo", "abc123") == "fail"


def test_get_check_status_commit_status_pending(monkeypatch):
    def fake_api(path):
        if "check-runs" in path:
            return {"check_runs": []}
        return {"statuses": [{"context": "ci/jenkins/branch", "state": "pending"}]}

    monkeypatch.setattr(api, "make_github_api_request", fake_api)
    assert api.get_check_status("org", "repo", "abc123") == "pending"


def test_get_check_status_commit_status_all_success(monkeypatch):
    def fake_api(path):
        if "check-runs" in path:
            return {"check_runs": []}
        return {"statuses": [{"context": "ci/jenkins/branch", "state": "success"}]}

    monkeypatch.setattr(api, "make_github_api_request", fake_api)
    assert api.get_check_status("org", "repo", "abc123") == "pass"


def test_get_approval_status_approved(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {"repository": {"pullRequest": {"reviewDecision": "APPROVED"}}}
        },
    )
    assert api.get_approval_status("org", "repo", 1) == "approved"


def test_get_approval_status_changes_requested(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {
                "repository": {"pullRequest": {"reviewDecision": "CHANGES_REQUESTED"}}
            }
        },
    )
    assert api.get_approval_status("org", "repo", 1) == "changes"


def test_get_approval_status_pending_no_reviews(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {
                "repository": {"pullRequest": {"reviewDecision": "REVIEW_REQUIRED"}}
            }
        },
    )
    assert api.get_approval_status("org", "repo", 1) == "pending"


def test_get_approval_status_latest_review_per_reviewer_wins(monkeypatch):
    """If a reviewer approves then requests changes, changes_requested wins."""
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    reviews = [
        {"user": {"login": "alice"}, "state": "APPROVED"},
        {"user": {"login": "alice"}, "state": "CHANGES_REQUESTED"},
    ]

    def fake_get(url, headers):
        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return reviews

        return Resp()

    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {"repository": {"pullRequest": {"reviewDecision": None}}}
        },
    )
    monkeypatch.setattr(api.requests, "get", fake_get)
    assert api.get_approval_status("org", "repo", 1) == "changes"


def test_get_approval_status_pending_only_comments(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    reviews = [
        {"user": {"login": "alice"}, "state": "COMMENTED"},
    ]

    def fake_get(url, headers):
        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return reviews

        return Resp()

    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {"repository": {"pullRequest": {"reviewDecision": None}}}
        },
    )
    monkeypatch.setattr(api.requests, "get", fake_get)
    assert api.get_approval_status("org", "repo", 1) == "pending"


def test_get_approval_status_falls_back_to_rest_reviews_on_graphql_error(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    reviews = [
        {"user": {"login": "alice"}, "state": "APPROVED"},
    ]

    def fake_get(url, headers):
        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return reviews

        return Resp()

    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: (_ for _ in ()).throw(ValueError("graphql failed")),
    )
    monkeypatch.setattr(api.requests, "get", fake_get)

    assert api.get_approval_status("org", "repo", 1) == "approved"


def test_get_required_approving_review_count(monkeypatch):
    monkeypatch.setattr(
        api,
        "make_github_api_request",
        lambda path: {"required_approving_review_count": 2},
    )

    assert api.get_required_approving_review_count("org", "repo", "main") == 2


def test_get_approval_summary_includes_counts_for_multi_review_branch(monkeypatch):
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {
                "repository": {"pullRequest": {"reviewDecision": "REVIEW_REQUIRED"}}
            }
        },
    )
    monkeypatch.setattr(
        api,
        "make_paginated_github_api_request",
        lambda path: [{"user": {"login": "alice"}, "state": "APPROVED"}],
    )
    monkeypatch.setattr(
        api,
        "get_required_approving_review_count",
        lambda owner, repo, branch: 2,
    )

    summary = api.get_approval_summary("org", "repo", 1, base_branch="main")

    assert summary == {"status": "pending", "current": 1, "required": 2}


def test_get_approval_summary_preserves_approved_when_github_reports_approved(
    monkeypatch,
):
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {"repository": {"pullRequest": {"reviewDecision": "APPROVED"}}}
        },
    )
    monkeypatch.setattr(
        api,
        "make_paginated_github_api_request",
        lambda path: [{"user": {"login": "alice"}, "state": "APPROVED"}],
    )
    monkeypatch.setattr(
        api,
        "get_required_approving_review_count",
        lambda owner, repo, branch: 2,
    )

    summary = api.get_approval_summary("org", "repo", 1, base_branch="main")

    assert summary == {"status": "approved", "current": 2, "required": 2}


def test_get_check_status_mixed_sources(monkeypatch):
    """Check runs pass but commit statuses fail — overall should be fail."""

    def fake_api(path):
        if "check-runs" in path:
            return {
                "check_runs": [
                    {"status": "completed", "conclusion": "success"},
                ]
            }
        return {"statuses": [{"context": "ci/jenkins/pr-merge", "state": "failure"}]}

    monkeypatch.setattr(api, "make_github_api_request", fake_api)
    assert api.get_check_status("org", "repo", "abc123") == "fail"


def test_make_github_graphql_request_retries_on_connection_error(monkeypatch):
    """TLS reset / connection reset by peer is retried and eventually succeeds."""
    attempts = []
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    monkeypatch.setattr(api.random, "uniform", lambda _a, _b: 0)

    class GoodResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"ok": True}}

    def fake_post(url, json, headers):
        attempts.append(1)
        if len(attempts) < 3:
            raise requests.exceptions.ConnectionError(
                "[Errno 54] Connection reset by peer"
            )
        return GoodResponse()

    monkeypatch.setattr(api.requests, "post", fake_post)

    result = api.make_github_graphql_request("{ viewer { login } }")

    assert result == {"data": {"ok": True}}
    assert len(attempts) == 3


def test_make_github_graphql_request_retries_on_dns_failure(monkeypatch):
    """DNS resolution failure (nodename nor servname provided) is retried."""
    attempts = []
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    monkeypatch.setattr(api.random, "uniform", lambda _a, _b: 0)

    class GoodResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"ok": True}}

    def fake_post(url, json, headers):
        attempts.append(1)
        if len(attempts) < 2:
            raise requests.exceptions.ConnectionError(
                "NameResolutionError: [Errno 8] nodename nor servname provided"
            )
        return GoodResponse()

    monkeypatch.setattr(api.requests, "post", fake_post)

    result = api.make_github_graphql_request("{ viewer { login } }")

    assert result == {"data": {"ok": True}}
    assert len(attempts) == 2


def test_make_github_graphql_request_raises_after_max_retries(monkeypatch):
    """Persistent connection errors exhaust retries and re-raise."""
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    monkeypatch.setattr(api.random, "uniform", lambda _a, _b: 0)

    def fake_post(url, json, headers):
        raise requests.exceptions.ConnectionError("[Errno 54] Connection reset by peer")

    monkeypatch.setattr(api.requests, "post", fake_post)

    with pytest.raises(requests.exceptions.ConnectionError):
        api.make_github_graphql_request("{ viewer { login } }")


def test_make_github_graphql_request_raises_on_persistent_timeout(monkeypatch):
    """Persistent timeout exhausts retries and re-raises."""
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    monkeypatch.setattr(api.random, "uniform", lambda _a, _b: 0)

    def fake_post(url, json, headers):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(api.requests, "post", fake_post)

    with pytest.raises(requests.exceptions.Timeout):
        api.make_github_graphql_request("{ viewer { login } }")


def test_make_github_graphql_request_retries_on_chunked_encoding_error(monkeypatch):
    """Premature chunked response is retried and eventually succeeds."""
    attempts = []
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    monkeypatch.setattr(api.random, "uniform", lambda _a, _b: 0)

    class GoodResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"ok": True}}

    def fake_post(url, json, headers):
        attempts.append(1)
        if len(attempts) < 3:
            raise requests.exceptions.ChunkedEncodingError("Response ended prematurely")
        return GoodResponse()

    monkeypatch.setattr(api.requests, "post", fake_post)

    result = api.make_github_graphql_request("{ viewer { login } }")

    assert result == {"data": {"ok": True}}
    assert len(attempts) == 3


def test_make_github_api_request_retries_on_chunked_encoding_error(monkeypatch):
    """Premature chunked REST response is retried and eventually succeeds."""
    attempts = []
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    class GoodResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def fake_get(url, headers):
        attempts.append(1)
        if len(attempts) < 2:
            raise requests.exceptions.ChunkedEncodingError("Response ended prematurely")
        return GoodResponse()

    monkeypatch.setattr(api.requests, "get", fake_get)

    result = api.make_github_api_request("/repos/org/repo")

    assert result == {"ok": True}
    assert len(attempts) == 2


def test_get_api_stats_tracks_rest_calls(monkeypatch):
    """REST calls increment the rest_calls counter."""
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    # Reset stats for this test
    with api._api_stats_lock:
        api._api_stats.update(
            {
                "rest_calls": 0,
                "graphql_calls": 0,
                "rest_rate_limit_remaining": None,
                "rest_rate_limit_reset": None,
            }
        )

    class OkResponse:
        status_code = 200
        headers = {"X-RateLimit-Remaining": "4999", "X-RateLimit-Reset": "1700000000"}

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(api.requests, "get", lambda url, headers: OkResponse())

    api.make_github_api_request("/repos/org/repo")
    api.make_github_api_request("/repos/org/repo")

    stats = api.get_api_stats()
    assert stats["rest_calls"] == 2
    assert stats["rest_rate_limit_remaining"] == 4999
    assert stats["rest_rate_limit_reset"] == 1700000000


def test_get_api_stats_tracks_graphql_calls(monkeypatch):
    """GraphQL calls increment the graphql_calls counter."""
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    monkeypatch.setattr(api.random, "uniform", lambda _a, _b: 0)
    with api._api_stats_lock:
        api._api_stats.update(
            {
                "rest_calls": 0,
                "graphql_calls": 0,
                "rest_rate_limit_remaining": None,
                "rest_rate_limit_reset": None,
            }
        )

    class GoodGraphqlResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"viewer": {"login": "alice"}}}

    monkeypatch.setattr(
        api.requests, "post", lambda url, json, headers: GoodGraphqlResponse()
    )

    api.make_github_graphql_request("{ viewer { login } }")
    api.make_github_graphql_request("{ viewer { login } }")

    stats = api.get_api_stats()
    assert stats["graphql_calls"] == 2


def test_get_graphql_rate_limit_returns_rate_limit_data(monkeypatch):
    """get_graphql_rate_limit returns the rateLimit node from the response."""
    rate_limit = {
        "cost": 1,
        "remaining": 4998,
        "resetAt": "2026-04-11T10:30:00Z",
        "used": 2,
    }
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables={}: {"data": {"rateLimit": rate_limit}},
    )

    result = api.get_graphql_rate_limit()
    assert result == rate_limit


def test_get_graphql_rate_limit_returns_none_on_error(monkeypatch):
    """get_graphql_rate_limit returns None if the request fails."""
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables={}: (_ for _ in ()).throw(
            requests.exceptions.ConnectionError("network error")
        ),
    )

    result = api.get_graphql_rate_limit()
    assert result is None


# ---------------------------------------------------------------------------
# _match_repo_filter
# ---------------------------------------------------------------------------


def test_match_repo_filter_empty_matches_all():
    assert api._match_repo_filter("any-repo", "") is True


def test_match_repo_filter_substring_backward_compat():
    """Plain strings use substring matching for backward compatibility."""
    assert api._match_repo_filter("platform-api", "platform") is True
    assert api._match_repo_filter("happyapp", "app") is True
    assert api._match_repo_filter("mapper", "app") is True


def test_match_repo_filter_substring_no_match():
    assert api._match_repo_filter("platform-api", "frontend") is False


def test_match_repo_filter_glob_star_prefix():
    """app-* matches repos starting with 'app-' only."""
    assert api._match_repo_filter("app-one", "app-*") is True
    assert api._match_repo_filter("app-two", "app-*") is True
    assert api._match_repo_filter("happyapp", "app-*") is False
    assert api._match_repo_filter("mapper", "app-*") is False


def test_match_repo_filter_glob_question_mark():
    """? matches exactly one character."""
    assert api._match_repo_filter("service-a", "service-?") is True
    assert api._match_repo_filter("service-ab", "service-?") is False


def test_match_repo_filter_glob_bracket():
    """[abc] matches a single character from the set."""
    assert api._match_repo_filter("service-a", "service-[abc]") is True
    assert api._match_repo_filter("service-z", "service-[abc]") is False


def test_match_repo_filter_glob_exact_match():
    """Glob without wildcards requires exact match."""
    # fnmatch treats a bare pattern with no wildcards as exact match
    assert api._match_repo_filter("app", "app") is True


def test_match_repo_filter_glob_no_partial_match():
    """Glob pattern without trailing * does not match mid-string."""
    assert api._match_repo_filter("app-one", "app") is True  # substring fallback
    # But if user adds glob chars, fnmatch is used (no partial match)
    assert api._match_repo_filter("app-one", "app?") is False  # 'app-one' != 'app?'


# ---------------------------------------------------------------------------
# Rate limit error tests
# ---------------------------------------------------------------------------


def _make_rate_limit_response(reset_ts="1712000000"):
    """Return a fake requests.Response that looks like a GitHub rate-limit 403."""

    class FakeResponse:
        status_code = 403
        headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": reset_ts,
        }

        def raise_for_status(self):
            raise requests.exceptions.HTTPError(response=self)

    return FakeResponse()


def test_make_github_api_request_raises_rate_limit_error(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(
        api.requests, "get", lambda *_a, **_kw: _make_rate_limit_response()
    )

    with pytest.raises(api.GitHubRateLimitError):
        api.make_github_api_request("/user")


def test_make_github_api_request_rate_limit_error_contains_reset_time(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(
        api.requests, "get", lambda *_a, **_kw: _make_rate_limit_response("1712000000")
    )

    with pytest.raises(api.GitHubRateLimitError) as exc_info:
        api.make_github_api_request("/user")

    assert exc_info.value.reset_time is not None
    assert "2024" in exc_info.value.reset_time  # timestamp 1712000000 is in 2024


def test_make_github_api_request_403_without_rate_limit_header_raises_http_error(
    monkeypatch,
):
    """A plain 403 (auth failure) should raise HTTPError, not GitHubRateLimitError."""

    class FakeForbidden:
        status_code = 403
        headers = {}  # no X-RateLimit-Remaining header

        def raise_for_status(self):
            raise requests.exceptions.HTTPError(response=self)

    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.requests, "get", lambda *_a, **_kw: FakeForbidden())

    with pytest.raises(requests.exceptions.HTTPError):
        api.make_github_api_request("/user")
