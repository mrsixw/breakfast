import json
from datetime import datetime, timezone

import click
import pytest
import requests
from click.testing import CliRunner

import breakfast


@pytest.mark.parametrize(
    "num,expected_color",
    [
        (5, "green"),
        (15, "yellow"),
        (30, (255, 165, 0)),
        (60, "red"),
    ],
)
def test_click_colour_grade_number(num, expected_color):
    expected = click.style(str(num), fg=expected_color, bold=True)
    assert breakfast.click_colour_grade_number(num) == expected


def test_generate_terminal_url_anchor():
    url = "https://example.com/path"
    text = "Link"
    expected = f"\033]8;;{url}\033\\{text}\033]8;;\033\\"
    assert breakfast.generate_terminal_url_anchor(url, text) == expected


def test_get_pr_age_days():
    pr_detail = {"created_at": "2026-01-10T00:00:00Z"}
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)

    assert breakfast.get_pr_age_days(pr_detail, now=now) == 5


def test_get_pr_age_days_invalid_or_missing():
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)

    assert breakfast.get_pr_age_days({}, now=now) == 0
    assert breakfast.get_pr_age_days({"created_at": "bad-date"}, now=now) == 0


def test_make_github_api_request_retries_on_connection_error(monkeypatch):
    attempts = []
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast.time, "sleep", lambda _: None)

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

    monkeypatch.setattr(breakfast.requests, "get", fake_get)

    result = breakfast.make_github_api_request("/repos/org/repo")

    assert result == {"ok": True}
    assert len(attempts) == 3


def test_make_github_api_request_raises_after_max_retries_connection_error(monkeypatch):
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast.time, "sleep", lambda _: None)

    def fake_get(url, headers):
        raise requests.exceptions.ConnectionError("reset")

    monkeypatch.setattr(breakfast.requests, "get", fake_get)

    with pytest.raises(requests.exceptions.ConnectionError):
        breakfast.make_github_api_request("/repos/org/repo")


def test_make_github_api_request_retries_on_502(monkeypatch):
    attempts = []
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast.time, "sleep", lambda _: None)

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

    monkeypatch.setattr(breakfast.requests, "get", fake_get)

    result = breakfast.make_github_api_request("/repos/org/repo")

    assert result == {"ok": True}
    assert len(attempts) == 3


def test_make_github_api_request_raises_after_max_retries_502(monkeypatch):
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast.time, "sleep", lambda _: None)

    class BadGateway:
        status_code = 502

        def raise_for_status(self):
            raise requests.exceptions.HTTPError("502")

        def json(self):
            return {}

    monkeypatch.setattr(breakfast.requests, "get", lambda url, headers: BadGateway())

    with pytest.raises(requests.exceptions.HTTPError):
        breakfast.make_github_api_request("/repos/org/repo")


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

    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast.requests, "get", fake_get)

    result = breakfast.make_github_api_request("/repos/org/repo")

    assert result == {"ok": True}
    assert calls["url"] == f"{breakfast.GITHUB_API_URL}/repos/org/repo"
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

    monkeypatch.setattr(breakfast, "make_github_graphql_request", fake_graphql_request)
    monkeypatch.setattr(breakfast, "BREAKFAST_ITEMS", ["*"])

    prs = breakfast.get_github_prs("org", "app")

    assert prs == [
        "https://example.com/app-one/1",
        "https://example.com/app-two/3",
    ]


def test_filter_pr_details_ignores_authors():
    pr_details = [
        {"user": {"login": "dependabot[bot]"}},
        {"user": {"login": "alice"}},
        {"user": {"login": "bob"}},
    ]

    filtered = breakfast.filter_pr_details(
        pr_details,
        ignore_authors=["Dependabot[Bot]", "bob"],
    )

    assert filtered == [{"user": {"login": "alice"}}]


def test_filter_pr_details_mine_only():
    pr_details = [
        {"user": {"login": "alice"}},
        {"user": {"login": "bob"}},
    ]

    filtered = breakfast.filter_pr_details(
        pr_details,
        ignore_authors=[],
        mine_only=True,
        current_user_login="alice",
    )

    assert filtered == [{"user": {"login": "alice"}}]


def test_normalize_ignore_authors_multiple():
    ignore_authors = [" Dependabot[Bot] ", "", "ALICE", "alice", None, "bob"]

    result = breakfast.normalize_ignore_authors(ignore_authors)

    assert result == {"dependabot[bot]", "alice", "bob"}


def test_get_authenticated_user_login(monkeypatch):
    monkeypatch.setattr(
        breakfast,
        "make_github_api_request",
        lambda _path: {"login": "alice"},
    )

    assert breakfast.get_authenticated_user_login() == "alice"


def test_get_authenticated_user_login_missing_login(monkeypatch):
    monkeypatch.setattr(breakfast, "make_github_api_request", lambda _path: {})

    with pytest.raises(
        ValueError,
        match="Unable to determine authenticated GitHub user",
    ):
        breakfast.get_authenticated_user_login()


def test_cli_exits_when_token_missing(monkeypatch):
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", None)
    runner = CliRunner()

    result = runner.invoke(breakfast.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 1
    assert "GITHUB_TOKEN not set" in result.output


def test_cli_outputs_table(monkeypatch):
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast, "BREAKFAST_ITEMS", ["*"])

    def fake_get_prs(_org, _repo_filter):
        return ["https://github.com/org/repo/pull/1"]

    def fake_api_request(_path):
        return {
            "base": {"repo": {"name": "repo"}},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 5,
            "deletions": 2,
            "title": "Test PR",
            "user": {"login": "alice"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "html_url": "https://github.com/org/repo/pull/1",
            "number": 1,
        }

    monkeypatch.setattr(breakfast, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(breakfast, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(breakfast.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "PR-1" in result.output
    assert "repo" in result.output


def test_cli_outputs_age_column_when_enabled(monkeypatch):
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast, "BREAKFAST_ITEMS", ["*"])

    def fake_get_prs(_org, _repo_filter):
        return ["https://github.com/org/repo/pull/1"]

    def fake_api_request(_path):
        return {
            "base": {"repo": {"name": "repo"}},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 5,
            "deletions": 2,
            "title": "Test PR",
            "user": {"login": "alice"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "html_url": "https://github.com/org/repo/pull/1",
            "number": 1,
        }

    monkeypatch.setattr(breakfast, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(breakfast, "make_github_api_request", fake_api_request)
    monkeypatch.setattr(breakfast, "get_pr_age_days", lambda _pr_detail: 7)

    runner = CliRunner()
    result = runner.invoke(breakfast.breakfast, ["-o", "org", "-r", "repo", "--age"])

    assert result.exit_code == 0
    assert "Age" in result.output
    assert "7" in result.output


def test_cli_outputs_json(monkeypatch):
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast, "BREAKFAST_ITEMS", ["*"])

    def fake_get_prs(_org, _repo_filter):
        return ["https://github.com/org/repo/pull/1"]

    def fake_api_request(_path):
        return {
            "base": {"repo": {"name": "repo"}},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 5,
            "deletions": 2,
            "title": "Test PR",
            "user": {"login": "alice"},
            "state": "open",
            "draft": False,
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "updated_at": "2026-01-11T00:00:00Z",
            "html_url": "https://github.com/org/repo/pull/1",
            "number": 1,
            "labels": [{"name": "bug"}],
            "requested_reviewers": [{"login": "bob"}],
        }

    monkeypatch.setattr(breakfast, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(breakfast, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(breakfast.breakfast, ["-o", "org", "-r", "repo", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output[result.output.index("[") :])
    assert len(data) == 1
    pr = data[0]
    assert pr["repo"] == "repo"
    assert pr["pr_number"] == 1
    assert pr["title"] == "Test PR"
    assert pr["author"] == "alice"
    assert pr["url"] == "https://github.com/org/repo/pull/1"
    assert pr["state"] == "open"
    assert pr["draft"] is False
    assert pr["created_at"] == "2026-01-10T00:00:00Z"
    assert pr["updated_at"] == "2026-01-11T00:00:00Z"
    assert pr["labels"] == ["bug"]
    assert pr["requested_reviewers"] == ["bob"]


def test_cli_json_output_is_valid_json_when_empty(monkeypatch):
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(breakfast, "get_github_prs", lambda _org, _repo: [])

    runner = CliRunner()
    result = runner.invoke(breakfast.breakfast, ["-o", "org", "-r", "repo", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output[result.output.index("[") :]) == []


def test_cli_continues_when_one_pr_fetch_fails(monkeypatch):
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast, "BREAKFAST_ITEMS", ["*"])

    def fake_get_prs(_org, _repo_filter):
        return [
            "https://github.com/org/repo/pull/1",
            "https://github.com/org/repo/pull/2",
        ]

    def fake_api_request(path):
        if path.endswith("/2"):
            raise requests.exceptions.ConnectionError("reset")
        return {
            "base": {"repo": {"name": "repo"}},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 5,
            "deletions": 2,
            "title": "Good PR",
            "user": {"login": "alice"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "html_url": "https://github.com/org/repo/pull/1",
            "number": 1,
        }

    monkeypatch.setattr(breakfast, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(breakfast, "make_github_api_request", fake_api_request)
    monkeypatch.setattr(breakfast.time, "sleep", lambda _: None)

    runner = CliRunner()
    result = runner.invoke(breakfast.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "Good PR" in result.output
    assert "Warning" in result.output
    assert "1 PR(s)" in result.output


def test_cli_mine_only_filters_to_authenticated_user(monkeypatch):
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast, "BREAKFAST_ITEMS", ["*"])

    def fake_get_prs(_org, _repo_filter):
        return [
            "https://github.com/org/repo/pull/1",
            "https://github.com/org/repo/pull/2",
        ]

    def fake_api_request(path):
        number = 1 if path.endswith("/1") else 2
        author = "alice" if number == 1 else "bob"
        title = "Alice PR" if number == 1 else "Bob PR"
        return {
            "base": {"repo": {"name": "repo"}},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 5,
            "deletions": 2,
            "title": title,
            "user": {"login": author},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "html_url": f"https://github.com/org/repo/pull/{number}",
            "number": number,
        }

    monkeypatch.setattr(breakfast, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(breakfast, "make_github_api_request", fake_api_request)
    monkeypatch.setattr(breakfast, "get_authenticated_user_login", lambda: "alice")

    runner = CliRunner()
    result = runner.invoke(
        breakfast.breakfast,
        ["-o", "org", "-r", "repo", "--mine-only"],
    )

    assert result.exit_code == 0
    assert "Alice PR" in result.output
    assert "Bob PR" not in result.output


def test_parse_version_tuple():
    assert breakfast._parse_version_tuple("1.2.3") == (1, 2, 3)
    assert breakfast._parse_version_tuple("0.10.0") == (0, 10, 0)
    assert breakfast._parse_version_tuple("bad") == ()
    assert breakfast._parse_version_tuple(None) == ()


def test_check_for_update_newer_available(monkeypatch):
    monkeypatch.setattr(breakfast, "pkg_version", lambda _name: "0.9.0")
    monkeypatch.setattr(breakfast, "get_latest_version", lambda: "0.10.0")

    result = breakfast.check_for_update()

    assert result is not None
    assert "v0.9.0" in result
    assert "v0.10.0" in result
    assert "fresh breakfast" in result


def test_check_for_update_up_to_date(monkeypatch):
    monkeypatch.setattr(breakfast, "pkg_version", lambda _name: "0.10.0")
    monkeypatch.setattr(breakfast, "get_latest_version", lambda: "0.10.0")

    assert breakfast.check_for_update() is None


def test_check_for_update_no_latest(monkeypatch):
    monkeypatch.setattr(breakfast, "pkg_version", lambda _name: "0.10.0")
    monkeypatch.setattr(breakfast, "get_latest_version", lambda: None)

    assert breakfast.check_for_update() is None


def test_check_for_update_handles_errors(monkeypatch):
    def boom(_name):
        raise Exception("boom")

    monkeypatch.setattr(breakfast, "pkg_version", boom)
    monkeypatch.setattr(breakfast, "get_latest_version", lambda: "1.0.0")

    assert breakfast.check_for_update() is None


def test_get_latest_version_from_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(breakfast, "_CACHE_DIR", tmp_path)
    cache_file = tmp_path / "latest_version.json"
    cache_file.write_text(
        json.dumps(
            {
                "latest_version": "1.2.3",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )

    assert breakfast.get_latest_version() == "1.2.3"


def test_get_latest_version_expired_cache_fetches(monkeypatch, tmp_path):
    monkeypatch.setattr(breakfast, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    cache_file = tmp_path / "latest_version.json"
    old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
    cache_file.write_text(
        json.dumps(
            {
                "latest_version": "0.1.0",
                "checked_at": old_time.isoformat(),
            }
        )
    )

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"tag_name": "v2.0.0"}

    monkeypatch.setattr(
        breakfast.requests,
        "get",
        lambda *args, **kwargs: FakeResp(),
    )

    assert breakfast.get_latest_version() == "2.0.0"


def test_get_latest_version_api_failure_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(breakfast, "_CACHE_DIR", tmp_path)

    def fail(*args, **kwargs):
        raise requests.exceptions.ConnectionError("nope")

    monkeypatch.setattr(breakfast.requests, "get", fail)

    assert breakfast.get_latest_version() is None


def test_write_and_read_version_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(breakfast, "_CACHE_DIR", tmp_path)

    breakfast._write_version_cache("3.0.0")
    assert breakfast._read_version_cache() == "3.0.0"
