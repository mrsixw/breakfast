import datetime
import json
import re

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


_SEARCH_PAGE = 100
_SEARCH_CAP = 1000
_CREATED_RANGE = re.compile(r"created:(\S+)\.\.(\S+)")


def _parse_search_timestamp(value):
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


class FakeSearch:
    """Stand-in for GitHub's search endpoint.

    Honours ``created:A..B`` ranges (inclusive, like GitHub), the 1,000-result
    cap, 100-node pages with opaque cursors, and the optional owner lookup.
    """

    def __init__(self, prs, owner_exists=True):
        self.prs = sorted(prs, key=lambda pr: pr["created"])
        self.owner_exists = owner_exists
        self.calls = []

    def __call__(self, _query, variables):
        self.calls.append(dict(variables))
        matched = self.prs
        created = _CREATED_RANGE.search(variables["searchQuery"])
        if created:
            low, high = (_parse_search_timestamp(v) for v in created.groups())
            matched = [pr for pr in matched if low <= pr["created"] <= high]
        visible = matched[:_SEARCH_CAP]
        offset = int(variables["cursor"] or 0)
        end = offset + _SEARCH_PAGE
        data = {
            "search": {
                "issueCount": len(matched),
                "nodes": [
                    {"url": pr["url"], "repository": {"name": pr["repo"]}}
                    for pr in visible[offset:end]
                ],
                "pageInfo": {"endCursor": str(end), "hasNextPage": end < len(visible)},
            }
        }
        if variables["checkOwner"]:
            data["owner"] = {"login": "acme"} if self.owner_exists else None
        return {"data": data}


def _fake_prs(count, repo="app", start=None, step=datetime.timedelta(hours=1)):
    start = start or datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    return [
        {
            "url": f"https://github.com/acme/{repo}/pull/{n}",
            "repo": repo,
            "created": start + step * n,
        }
        for n in range(count)
    ]


def _install_search(monkeypatch, fake):
    monkeypatch.setattr(api, "make_github_graphql_request", fake)
    monkeypatch.setattr(api, "BREAKFAST_ITEMS", ["*"])
    return fake


def test_get_github_prs_pages_through_search_results(monkeypatch):
    prs = _fake_prs(250)
    fake = _install_search(monkeypatch, FakeSearch(prs))

    result = api.get_github_prs("acme", [])

    assert result == [pr["url"] for pr in prs]
    assert [call["cursor"] for call in fake.calls] == [None, "100", "200"]


def test_get_github_prs_cost_scales_with_prs_not_repos(monkeypatch):
    # Three PRs spread over three repos: one request, however many repos exist.
    prs = _fake_prs(1, "a") + _fake_prs(1, "b") + _fake_prs(1, "c")
    fake = _install_search(monkeypatch, FakeSearch(prs))

    api.get_github_prs("acme", [])

    assert len(fake.calls) == 1


def test_get_github_prs_checks_owner_on_first_request_only(monkeypatch):
    fake = _install_search(monkeypatch, FakeSearch(_fake_prs(150)))

    api.get_github_prs("acme", [])

    assert [call["checkOwner"] for call in fake.calls] == [True, False]
    assert all(call["owner"] == "acme" for call in fake.calls)


def test_get_github_prs_raises_owner_not_found_when_null(monkeypatch):
    _install_search(monkeypatch, FakeSearch([], owner_exists=False))

    with pytest.raises(api.OwnerNotFoundError) as exc_info:
        api.get_github_prs("ghost-login", [])

    assert "ghost-login" in str(exc_info.value)


def test_get_github_prs_filters_on_repository_name(monkeypatch):
    prs = _fake_prs(1, "app-one") + _fake_prs(1, "other") + _fake_prs(1, "app-two")
    _install_search(monkeypatch, FakeSearch(prs))

    result = api.get_github_prs("acme", ["app"])

    assert result == [
        "https://github.com/acme/app-one/pull/0",
        "https://github.com/acme/app-two/pull/0",
    ]


def test_get_github_prs_skips_null_nodes(monkeypatch):
    def fake(_query, variables):
        return {
            "data": {
                "owner": {"login": "acme"},
                "search": {
                    "issueCount": 3,
                    "nodes": [
                        None,
                        {"url": "https://github.com/acme/x/pull/1", "repository": None},
                        {
                            "url": "https://github.com/acme/app/pull/2",
                            "repository": {"name": "app"},
                        },
                    ],
                    "pageInfo": {"endCursor": None, "hasNextPage": False},
                },
            }
        }

    _install_search(monkeypatch, fake)

    assert api.get_github_prs("acme", []) == ["https://github.com/acme/app/pull/2"]


def _search_string_for(monkeypatch, fetch_state="open", include_archived=False):
    fake = _install_search(monkeypatch, FakeSearch([]))
    api.get_github_prs("acme", [], fetch_state, include_archived)
    return fake.calls[0]["searchQuery"].split()


def test_get_github_prs_search_scopes_to_owner_prs(monkeypatch):
    terms = _search_string_for(monkeypatch)

    assert "org:acme" in terms
    assert "is:pr" in terms
    # Oldest first, so PRs opened mid-run append rather than shift pages.
    assert "sort:created-asc" in terms


def test_get_github_prs_skips_archived_repos_by_default(monkeypatch):
    assert "archived:false" in _search_string_for(monkeypatch)


def test_get_github_prs_include_archived_drops_the_qualifier(monkeypatch):
    terms = _search_string_for(monkeypatch, include_archived=True)

    assert not any(term.startswith("archived:") for term in terms)


@pytest.mark.parametrize(
    "fetch_state, expected, forbidden",
    [
        ("open", {"is:open"}, {"is:closed", "is:merged", "is:unmerged"}),
        ("OPEN", {"is:open"}, {"is:closed", "is:merged", "is:unmerged"}),
        ("closed", {"is:closed", "is:unmerged"}, {"is:open", "is:merged"}),
        ("merged", {"is:merged"}, {"is:open", "is:closed", "is:unmerged"}),
        ("all", set(), {"is:open", "is:closed", "is:merged", "is:unmerged"}),
    ],
)
def test_get_github_prs_maps_fetch_state_to_qualifiers(
    monkeypatch, fetch_state, expected, forbidden
):
    terms = set(_search_string_for(monkeypatch, fetch_state))

    assert expected <= terms
    assert not terms & forbidden


def test_get_github_prs_splits_over_the_search_cap(monkeypatch):
    prs = _fake_prs(2500)
    fake = _install_search(monkeypatch, FakeSearch(prs))

    result = api.get_github_prs("acme", [])

    assert sorted(result) == sorted(pr["url"] for pr in prs)
    assert len(result) == len(set(result))
    # No slice that is still over the cap gets paged: those pages are wasted.
    for call in fake.calls:
        if call["cursor"] is not None:
            query = call["searchQuery"]
            created = _CREATED_RANGE.search(query)
            assert created, f"paged an unsliced over-cap query: {query}"
            low, high = (_parse_search_timestamp(v) for v in created.groups())
            in_slice = [pr for pr in prs if low <= pr["created"] <= high]
            assert len(in_slice) <= _SEARCH_CAP


def test_get_github_prs_slices_results_under_the_cap_for_parallel_paging(
    monkeypatch,
):
    # 600 results fit under the cap, but paging them one cursor at a time is
    # slow; slicing lets every page be fetched in parallel.
    prs = _fake_prs(600)
    fake = _install_search(monkeypatch, FakeSearch(prs))

    result = api.get_github_prs("acme", [])

    assert sorted(result) == sorted(pr["url"] for pr in prs)
    unsliced_pages = [
        call
        for call in fake.calls
        if call["cursor"] and not _CREATED_RANGE.search(call["searchQuery"])
    ]
    assert unsliced_pages == []


def test_get_github_prs_dedupes_prs_on_a_slice_boundary(monkeypatch):
    # Many PRs sharing each second makes boundary PRs land in both halves of an
    # inclusive split, exactly as they would on GitHub.
    prs = _fake_prs(1500, step=datetime.timedelta(0))
    prs += _fake_prs(1500, repo="svc", step=datetime.timedelta(seconds=1))
    _install_search(monkeypatch, FakeSearch(prs))

    result = api.get_github_prs("acme", [])

    assert len(result) == len(set(result))


def test_get_github_prs_keeps_the_cap_when_a_slice_cannot_split(monkeypatch, caplog):
    # 1,200 PRs created in the same second: no finer slice exists.
    _install_search(
        monkeypatch, FakeSearch(_fake_prs(1200, step=datetime.timedelta(0)))
    )

    with caplog.at_level("WARNING", logger="breakfast"):
        result = api.get_github_prs("acme", [])

    assert len(result) == _SEARCH_CAP
    assert "search_slice_over_cap" in caplog.text


def test_get_github_prs_warns_on_stderr_when_a_slice_is_truncated(monkeypatch, capsys):
    _install_search(
        monkeypatch, FakeSearch(_fake_prs(1200, step=datetime.timedelta(0)))
    )

    api.get_github_prs("acme", [])

    captured = capsys.readouterr()
    assert "only 1000 of 1200" in captured.err
    assert captured.out == ""


def test_get_github_prs_propagates_errors_from_parallel_slices(monkeypatch):
    fake = FakeSearch(_fake_prs(900))

    def failing_slices(query, variables):
        if _CREATED_RANGE.search(variables["searchQuery"]):
            raise api.GitHubRateLimitError()
        return fake(query, variables)

    _install_search(monkeypatch, failing_slices)

    with pytest.raises(api.GitHubRateLimitError):
        api.get_github_prs("acme", [])


def test_get_github_prs_propagates_graphql_errors(monkeypatch):
    def fake(_query, _variables):
        raise api.GitHubGraphQLError([{"type": "FORBIDDEN", "message": "Nope."}])

    _install_search(monkeypatch, fake)

    with pytest.raises(api.GitHubGraphQLError):
        api.get_github_prs("acme", [])


def test_match_exclude_repos_exact():
    assert api.match_exclude_repos("old-service", ["old-service"]) is True
    assert api.match_exclude_repos("app", ["old-service"]) is False


def test_match_exclude_repos_glob():
    assert api.match_exclude_repos("old-api", ["old-*"]) is True
    assert api.match_exclude_repos("old-web", ["old-*"]) is True
    assert api.match_exclude_repos("app", ["old-*"]) is False


def test_match_exclude_repos_multiple_patterns():
    assert api.match_exclude_repos("infra-prod", ["old-*", "infra-*"]) is True
    assert api.match_exclude_repos("app", ["old-*", "infra-*"]) is False


def test_match_exclude_repos_empty():
    assert api.match_exclude_repos("anything", []) is False
    assert api.match_exclude_repos("anything", None) is False


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


def test_get_approval_status_makes_only_one_graphql_call_on_fallback(monkeypatch):
    """When reviewDecision is null, the REST-fallback path must not re-query GraphQL."""
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    graphql_calls = []

    def fake_graphql(query, variables):
        graphql_calls.append(variables)
        return {"data": {"repository": {"pullRequest": {"reviewDecision": None}}}}

    monkeypatch.setattr(api, "make_github_graphql_request", fake_graphql)
    monkeypatch.setattr(
        api,
        "make_paginated_github_api_request",
        lambda path: [{"user": {"login": "alice"}, "state": "APPROVED"}],
    )

    assert api.get_approval_status("org", "repo", 1) == "approved"
    assert len(graphql_calls) == 1


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
    """When GitHub reports APPROVED but the latest review tally is below the
    required count, the displayed count must reflect the actual review tally,
    not be silently inflated to required."""
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

    assert summary == {"status": "approved", "current": 1, "required": 2}


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


def test_make_github_graphql_request_bounds_repeated_resource_errors(
    monkeypatch, requests_mock, caplog
):
    errors = [
        {
            "type": "RESOURCE_LIMITS_EXCEEDED",
            "path": ["repositoryOwner", "repositories", "nodes", index, "url"],
            "message": "Resource limits for this query exceeded.",
        }
        for index in range(500)
    ]
    requests_mock.post(
        api.GITHUB_GRAPHQL_URL,
        json={"data": {"repositoryOwner": {"repositories": None}}, "errors": errors},
    )
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    caplog.set_level("WARNING")

    with pytest.raises(api.GitHubGraphQLResourceLimitError) as exc_info:
        api.make_github_graphql_request("{ viewer { login } }")

    exc = exc_info.value
    assert exc.error_count == 500
    assert len(exc.errors) == 10
    assert "RESOURCE_LIMITS_EXCEEDED=500" in str(exc)
    assert "repositories', 'nodes'" not in str(exc)
    assert len(str(exc)) < 250
    assert "error_count=500" in caplog.text
    assert caplog.text.count("RESOURCE_LIMITS_EXCEEDED") == 1
    assert len(caplog.text) < 500


def test_make_github_graphql_request_does_not_mask_mixed_errors(
    monkeypatch, requests_mock
):
    errors = [
        {"type": "FORBIDDEN", "message": "Access denied."},
        {
            "type": "RESOURCE_LIMITS_EXCEEDED",
            "message": "Resource limits for this query exceeded.",
        },
    ]
    requests_mock.post(api.GITHUB_GRAPHQL_URL, json={"data": {}, "errors": errors})
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")

    with pytest.raises(api.GitHubGraphQLError) as exc_info:
        api.make_github_graphql_request("{ viewer { login } }")

    assert type(exc_info.value) is api.GitHubGraphQLError
    assert "FORBIDDEN=1" in exc_info.value.summary
    assert "RESOURCE_LIMITS_EXCEEDED=1" in exc_info.value.summary


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
    assert api._match_repo_filter("any-repo", []) is True


def test_match_repo_filter_substring_backward_compat():
    """Plain strings use substring matching for backward compatibility."""
    assert api._match_repo_filter("platform-api", ["platform"]) is True
    assert api._match_repo_filter("happyapp", ["app"]) is True
    assert api._match_repo_filter("mapper", ["app"]) is True


def test_match_repo_filter_substring_no_match():
    assert api._match_repo_filter("platform-api", ["frontend"]) is False


def test_match_repo_filter_glob_star_prefix():
    """app-* matches repos starting with 'app-' only."""
    assert api._match_repo_filter("app-one", ["app-*"]) is True
    assert api._match_repo_filter("app-two", ["app-*"]) is True
    assert api._match_repo_filter("happyapp", ["app-*"]) is False
    assert api._match_repo_filter("mapper", ["app-*"]) is False


def test_match_repo_filter_glob_question_mark():
    """? matches exactly one character."""
    assert api._match_repo_filter("service-a", ["service-?"]) is True
    assert api._match_repo_filter("service-ab", ["service-?"]) is False


def test_match_repo_filter_glob_bracket():
    """[abc] matches a single character from the set."""
    assert api._match_repo_filter("service-a", ["service-[abc]"]) is True
    assert api._match_repo_filter("service-z", ["service-[abc]"]) is False


def test_match_repo_filter_glob_exact_match():
    """Glob without wildcards requires exact match."""
    # fnmatch treats a bare pattern with no wildcards as exact match
    assert api._match_repo_filter("app", ["app"]) is True


def test_match_repo_filter_multiple_or_logic():
    """Multiple filters: repo matches if it satisfies any one filter."""
    assert api._match_repo_filter("api-gateway", ["api", "platform"]) is True
    assert api._match_repo_filter("platform-web", ["api", "platform"]) is True
    assert api._match_repo_filter("auth-service", ["api", "platform"]) is False


def test_match_repo_filter_multiple_with_glob():
    """Multiple filters support mixing substring and glob patterns."""
    assert api._match_repo_filter("service-a", ["api", "service-?"]) is True
    assert api._match_repo_filter("service-ab", ["api", "service-?"]) is False
    assert api._match_repo_filter("api-gw", ["api", "service-?"]) is True


def test_match_repo_filter_glob_no_partial_match():
    """Glob pattern without trailing * does not match mid-string."""
    assert api._match_repo_filter("app-one", ["app"]) is True  # substring fallback
    # But if user adds glob chars, fnmatch is used (no partial match)
    assert api._match_repo_filter("app-one", ["app?"]) is False  # 'app-one' != 'app?'


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


def _make_auth_error_response():
    """Return a fake requests.Response that looks like an HTTP 401 Unauthorized."""

    class FakeUnauthorized:
        status_code = 401
        headers = {}

        def raise_for_status(self):
            raise requests.exceptions.HTTPError(response=self)

    return FakeUnauthorized()


def test_make_github_api_request_raises_auth_error_on_401(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "expired-token")
    calls = []

    def fake_get(*_a, **_kw):
        calls.append(1)
        return _make_auth_error_response()

    monkeypatch.setattr(api.requests, "get", fake_get)

    with pytest.raises(api.GitHubAuthenticationError) as exc_info:
        api.make_github_api_request("/user")

    assert isinstance(exc_info.value, requests.exceptions.HTTPError)
    assert "GitHub authentication failed" in str(exc_info.value)
    assert "HTTP 401" in str(exc_info.value)
    assert len(calls) == 1  # 401 is not retried


def test_make_github_graphql_request_raises_auth_error_on_401(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "expired-token")
    calls = []

    def fake_post(*_a, **_kw):
        calls.append(1)
        return _make_auth_error_response()

    monkeypatch.setattr(api.requests, "post", fake_post)

    with pytest.raises(api.GitHubAuthenticationError) as exc_info:
        api.make_github_graphql_request("query { viewer { login } }")

    assert isinstance(exc_info.value, requests.exceptions.HTTPError)
    assert "GitHub authentication failed" in str(exc_info.value)
    assert "HTTP 401" in str(exc_info.value)
    assert len(calls) == 1  # 401 is not retried


def test_get_authenticated_user_login_raises_auth_error_on_401(monkeypatch):
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "expired-token")
    monkeypatch.setattr(
        api.requests, "get", lambda *_a, **_kw: _make_auth_error_response()
    )

    with pytest.raises(api.GitHubAuthenticationError):
        api.get_authenticated_user_login()


def test_make_github_api_request_401_names_active_token_variable(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "cli-token")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "cli-token")
    monkeypatch.setattr(
        api.requests, "get", lambda *_a, **_kw: _make_auth_error_response()
    )

    with pytest.raises(api.GitHubAuthenticationError) as exc_info_gh:
        api.make_github_api_request("/user")
    assert "GH_TOKEN was rejected" in str(exc_info_gh.value)

    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "env-token")

    with pytest.raises(api.GitHubAuthenticationError) as exc_info_github:
        api.make_github_api_request("/user")
    assert "GITHUB_TOKEN was rejected" in str(exc_info_github.value)


def test_github_auth_error_message_identifies_token_variable():
    err = api.GitHubAuthenticationError(token_var="GH_TOKEN")
    assert "GH_TOKEN was rejected" in str(err)

    err2 = api.GitHubAuthenticationError(token_var="GITHUB_TOKEN")
    assert "GITHUB_TOKEN was rejected" in str(err2)


# ---------------------------------------------------------------------------
# fetch_pr_detail URL parsing (#241)
# ---------------------------------------------------------------------------


def test_fetch_pr_detail_standard_url(monkeypatch):
    """Standard GitHub PR URL is parsed correctly."""
    calls = []

    def fake_request(path):
        calls.append(path)
        return {"number": 42}

    monkeypatch.setattr(api, "make_github_api_request", fake_request)
    api.fetch_pr_detail("https://github.com/myorg/myrepo/pull/42")
    assert calls == ["/repos/myorg/myrepo/pulls/42"]


def test_fetch_pr_detail_trailing_slash(monkeypatch):
    """Trailing slash in URL does not break parsing."""
    calls = []
    monkeypatch.setattr(api, "make_github_api_request", lambda p: calls.append(p) or {})
    api.fetch_pr_detail("https://github.com/org/repo/pull/7/")
    assert calls == ["/repos/org/repo/pulls/7"]


def test_fetch_pr_detail_invalid_url_raises():
    """A URL with too few path segments raises ValueError."""
    import pytest

    with pytest.raises(ValueError, match="Unexpected PR URL format"):
        api.fetch_pr_detail("https://github.com/short")


def test_get_check_status_none_conclusion_not_counted_as_pass(monkeypatch):
    """In-progress check runs have conclusion=None; they must not be included in the
    conclusions set so that a mix of in-progress + passing runs does not falsely pass.
    """

    def fake_api(path):
        if "check-runs" in path:
            return {
                "check_runs": [
                    # completed and passing
                    {"status": "completed", "conclusion": "success"},
                    # queued/in-progress checks have conclusion=None
                    {"status": "queued", "conclusion": None},
                ]
            }
        return {"statuses": []}

    monkeypatch.setattr(api, "make_github_api_request", fake_api)
    assert api.get_check_status("org", "repo", "abc123") == "pending"


def test_get_check_status_all_completed_with_none_filtered(monkeypatch):
    """conclusion=None must be excluded from the conclusions set; only non-None values
    should be used to determine pass/fail."""

    def fake_api(path):
        if "check-runs" in path:
            return {
                "check_runs": [
                    {"status": "completed", "conclusion": "success"},
                    {"status": "completed", "conclusion": None},
                ]
            }
        return {"statuses": []}

    monkeypatch.setattr(api, "make_github_api_request", fake_api)
    assert api.get_check_status("org", "repo", "abc123") == "pass"


def test_make_github_api_request_asserts_timeout(monkeypatch):
    """Verifies that make_github_api_request passes the correct timeout kwarg."""
    timeout_passed = []

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def fake_get(url, headers, timeout=None):
        timeout_passed.append(timeout)
        return DummyResponse()

    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.requests, "get", fake_get)

    result = api.make_github_api_request("/repos/org/repo")
    assert result == {"ok": True}
    assert timeout_passed == [(5, 30)]


def test_make_github_graphql_request_asserts_timeout(monkeypatch):
    """Verifies that make_github_graphql_request passes the correct timeout kwarg."""
    timeout_passed = []

    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"ok": True}}

    def fake_post(url, json, headers, timeout=None):
        timeout_passed.append(timeout)
        return DummyResponse()

    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.requests, "post", fake_post)

    result = api.make_github_graphql_request("{ viewer { login } }")
    assert result == {"data": {"ok": True}}
    assert timeout_passed == [(5, 30)]


def test_make_github_api_request_retries_on_timeout_and_propagates(monkeypatch):
    """Verifies that a Timeout is retried MAX_RETRIES times and then raises."""
    attempts = []
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    def fake_get(url, headers, timeout=None):
        attempts.append(1)
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(api.requests, "get", fake_get)

    with pytest.raises(requests.exceptions.Timeout):
        api.make_github_api_request("/repos/org/repo")

    # 1 initial attempt + 3 retries = 4 attempts total
    assert len(attempts) == 4


def test_resolve_github_token_uses_gh_token_when_only_it_is_set(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", "gh-cli-token-value")

    assert api._resolve_github_token() == "gh-cli-token-value"


def test_resolve_github_token_falls_back_to_github_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token-value")
    monkeypatch.delenv("GH_TOKEN", raising=False)

    assert api._resolve_github_token() == "gh-token-value"


def test_resolve_github_token_prefers_gh_token_over_github_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token-value")
    monkeypatch.setenv("GH_TOKEN", "gh-cli-token-value")

    assert api._resolve_github_token() == "gh-cli-token-value"


def test_resolve_github_token_none_when_neither_set(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    assert api._resolve_github_token() is None


def test_resolve_github_token_info(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "cli-tok")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-tok")
    assert api._resolve_github_token_info() == ("cli-tok", "GH_TOKEN")

    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-tok")
    assert api._resolve_github_token_info() == ("gh-tok", "GITHUB_TOKEN")

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert api._resolve_github_token_info() == (None, None)


# ---------------------------------------------------------------------------
# GraphQL 403/429 handling
# ---------------------------------------------------------------------------

_SECONDARY_LIMIT_BODY = {
    "message": "You have exceeded a secondary rate limit. Please wait a few "
    "minutes before you try again."
}


def _graphql_http_response(status, body, headers=None):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    response.headers.update(headers or {})
    response.url = api.GITHUB_GRAPHQL_URL
    return response


def _script_graphql_posts(monkeypatch, responses):
    """Serve scripted responses to GraphQL POSTs and record every sleep."""
    monkeypatch.setattr(api, "SECRET_GITHUB_TOKEN", "token-123")
    queue = iter(responses)
    posts, sleeps = [], []

    def fake_post(*_a, **_kw):
        posts.append(1)
        return next(queue)

    monkeypatch.setattr(api.requests, "post", fake_post)
    monkeypatch.setattr(api.time, "sleep", sleeps.append)
    return posts, sleeps


def test_make_github_graphql_request_waits_out_secondary_limit_retry_after(
    monkeypatch, capsys
):
    _, sleeps = _script_graphql_posts(
        monkeypatch,
        [
            _graphql_http_response(403, _SECONDARY_LIMIT_BODY, {"Retry-After": "7"}),
            _graphql_http_response(200, {"data": {"ok": True}}),
        ],
    )

    result = api.make_github_graphql_request("{ viewer { login } }")

    assert result == {"data": {"ok": True}}
    assert sleeps == [7]
    captured = capsys.readouterr()
    assert "7s" in captured.err
    assert captured.out == ""


def test_make_github_graphql_request_treats_429_as_secondary_limit(monkeypatch):
    _, sleeps = _script_graphql_posts(
        monkeypatch,
        [
            _graphql_http_response(429, _SECONDARY_LIMIT_BODY, {"Retry-After": "3"}),
            _graphql_http_response(200, {"data": {"ok": True}}),
        ],
    )

    assert api.make_github_graphql_request("{ viewer { login } }") == {
        "data": {"ok": True}
    }
    assert sleeps == [3]


def test_make_github_graphql_request_waits_a_minute_without_retry_after(
    monkeypatch,
):
    # GitHub's guidance: with no retry-after header, wait at least one minute.
    _, sleeps = _script_graphql_posts(
        monkeypatch,
        [
            _graphql_http_response(403, _SECONDARY_LIMIT_BODY),
            _graphql_http_response(200, {"data": {"ok": True}}),
        ],
    )

    api.make_github_graphql_request("{ viewer { login } }")

    assert sleeps == [60]


def test_make_github_graphql_request_gives_up_on_a_persistent_secondary_limit(
    monkeypatch,
):
    limited = _graphql_http_response(403, _SECONDARY_LIMIT_BODY, {"Retry-After": "1"})
    posts, _ = _script_graphql_posts(monkeypatch, [limited] * (api.MAX_RETRIES + 1))

    with pytest.raises(api.GitHubRateLimitError) as exc_info:
        api.make_github_graphql_request("{ viewer { login } }")

    assert "secondary rate limit" in str(exc_info.value)
    assert len(posts) == api.MAX_RETRIES + 1


def test_make_github_graphql_request_raises_rate_limit_when_primary_exhausted(
    monkeypatch,
):
    posts, sleeps = _script_graphql_posts(
        monkeypatch,
        [
            _graphql_http_response(
                403,
                {"message": "API rate limit exceeded"},
                {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1790000000"},
            )
        ],
    )

    with pytest.raises(api.GitHubRateLimitError) as exc_info:
        api.make_github_graphql_request("{ viewer { login } }")

    assert exc_info.value.reset_time is not None
    assert len(posts) == 1, "an exhausted primary limit is not retried"
    assert sleeps == []


def test_make_github_graphql_request_surfaces_githubs_message_on_other_403(
    monkeypatch,
):
    message = "Resource protected by organization SAML enforcement."
    posts, _ = _script_graphql_posts(
        monkeypatch, [_graphql_http_response(403, {"message": message})]
    )

    with pytest.raises(api.GitHubForbiddenError) as exc_info:
        api.make_github_graphql_request("{ viewer { login } }")

    assert isinstance(exc_info.value, requests.exceptions.HTTPError)
    assert message in str(exc_info.value)
    assert "403" in str(exc_info.value)
    assert len(posts) == 1
