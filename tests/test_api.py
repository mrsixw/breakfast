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
