import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch

import requests
from click.testing import CliRunner

from breakfast import api, cli


def test_get_pr_age_days():
    pr_detail = {"created_at": "2026-01-10T00:00:00Z"}
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)

    assert cli.get_pr_age_days(pr_detail, now=now) == 5


def test_get_pr_age_days_invalid_or_missing():
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)

    assert cli.get_pr_age_days({}, now=now) == 0
    assert cli.get_pr_age_days({"created_at": "bad-date"}, now=now) == 0


def test_cli_exits_when_token_missing(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", None)
    runner = CliRunner()

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 1
    assert "GITHUB_TOKEN not set" in result.output


def test_cli_outputs_table(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "PR-1" in result.output
    assert "repo" in result.output


def test_cli_outputs_age_column_when_enabled(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)
    monkeypatch.setattr(cli, "get_pr_age_days", lambda _pr_detail: 7)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--age"])

    assert result.exit_code == 0
    assert "Age" in result.output
    assert "7" in result.output


def test_cli_outputs_json(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--json"])

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
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "get_github_prs", lambda _org, _repo: [])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output[result.output.index("[") :]) == []


def test_cli_continues_when_one_pr_fetch_fails(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    # Skip threading to make testing easier
    monkeypatch.setattr(
        ThreadPoolExecutor, "map", lambda self, func, *args: map(func, *args)
    )

    # skip sleep in api
    monkeypatch.setattr(api.time, "sleep", lambda _: None)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "Good PR" in result.output
    assert "Warning" in result.output
    assert "1 PR(s)" in result.output


def test_cli_mine_only_filters_to_authenticated_user(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)
    monkeypatch.setattr(cli, "get_authenticated_user_login", lambda: "alice")

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--mine-only"],
    )

    assert result.exit_code == 0
    assert "Alice PR" in result.output
    assert "Bob PR" not in result.output


def test_cli_outputs_checks_column(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    def fake_get_prs(_org, _repo_filter):
        return ["https://github.com/org/repo/pull/1"]

    def fake_api_request(path):
        if "check-runs" in path:
            return {
                "check_runs": [
                    {"status": "completed", "conclusion": "success"},
                ]
            }
        return {
            "base": {
                "repo": {
                    "name": "repo",
                    "owner": {"login": "org"},
                }
            },
            "head": {"sha": "abc123"},
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
            "id": 1001,
        }

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--checks"])

    assert result.exit_code == 0
    assert "Checks" in result.output
    assert "pass" in result.output


def test_cli_checks_no_collision_across_repos(monkeypatch):
    """PRs with the same number in different repos must keep separate check statuses."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    def fake_get_prs(_org, _repo_filter):
        return [
            "https://github.com/org/repo-a/pull/17",
            "https://github.com/org/repo-b/pull/17",
        ]

    pr_details = {
        "/repos/org/repo-a/pulls/17": {
            "base": {"repo": {"name": "repo-a", "owner": {"login": "org"}}},
            "head": {"sha": "sha-a"},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 1,
            "deletions": 0,
            "title": "PR A",
            "user": {"login": "alice"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "html_url": "https://github.com/org/repo-a/pull/17",
            "number": 17,
            "id": 2001,
        },
        "/repos/org/repo-b/pulls/17": {
            "base": {"repo": {"name": "repo-b", "owner": {"login": "org"}}},
            "head": {"sha": "sha-b"},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 2,
            "deletions": 1,
            "title": "PR B",
            "user": {"login": "bob"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "html_url": "https://github.com/org/repo-b/pull/17",
            "number": 17,
            "id": 2002,
        },
    }

    check_runs = {
        "/repos/org/repo-a/commits/sha-a/check-runs": {
            "check_runs": [{"status": "completed", "conclusion": "success"}]
        },
        "/repos/org/repo-b/commits/sha-b/check-runs": {
            "check_runs": [{"status": "completed", "conclusion": "failure"}]
        },
        "/repos/org/repo-a/commits/sha-a/status": {"statuses": []},
        "/repos/org/repo-b/commits/sha-b/status": {"statuses": []},
    }

    def fake_api_request(path):
        if path in check_runs:
            return check_runs[path]
        return pr_details[path]

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--checks"])

    assert result.exit_code == 0
    assert "pass" in result.output
    assert "fail" in result.output


def test_cli_checks_not_shown_by_default(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "Checks" not in result.output


def test_cli_json_includes_checks_when_enabled(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    def fake_get_prs(_org, _repo_filter):
        return ["https://github.com/org/repo/pull/1"]

    def fake_api_request(path):
        if "check-runs" in path:
            return {
                "check_runs": [
                    {"status": "completed", "conclusion": "failure"},
                ]
            }
        return {
            "base": {
                "repo": {
                    "name": "repo",
                    "owner": {"login": "org"},
                }
            },
            "head": {"sha": "abc123"},
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
            "id": 1001,
            "labels": [],
            "requested_reviewers": [],
        }

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--json", "--checks"]
    )

    assert result.exit_code == 0
    data = json.loads(result.output[result.output.index("[") :])
    assert data[0]["checks"] == "fail"


def test_cli_json_excludes_checks_by_default(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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
            "labels": [],
            "requested_reviewers": [],
        }

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output[result.output.index("[") :])
    assert "checks" not in data[0]


def test_no_update_check_flag_skips_update(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "get_github_prs", lambda _o, _r: [])
    check_called = []
    monkeypatch.setattr(
        cli,
        "check_for_update",
        lambda: check_called.append(1) or "update!",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--no-update-check"],
    )

    assert result.exit_code == 0
    assert len(check_called) == 0


def test_no_update_check_env_var(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "get_github_prs", lambda _o, _r: [])
    monkeypatch.setenv("BREAKFAST_NO_UPDATE_CHECK", "1")
    check_called = []
    monkeypatch.setattr(
        cli,
        "check_for_update",
        lambda: check_called.append(1) or "update!",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo"],
    )

    assert result.exit_code == 0
    assert len(check_called) == 0


def test_cli_truncates_title_when_max_title_length_set(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    long_title = "A" * 100

    def fake_get_prs(_org, _repo_filter):
        return ["https://github.com/org/repo/pull/1"]

    def fake_api_request(_path):
        return {
            "base": {"repo": {"name": "repo"}},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 1,
            "deletions": 0,
            "title": long_title,
            "user": {"login": "alice"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "html_url": "https://github.com/org/repo/pull/1",
            "number": 1,
        }

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--max-title-length", "20"]
    )

    assert result.exit_code == 0
    assert long_title not in result.output
    assert "A" * 19 + "…" in result.output


def test_cli_does_not_truncate_title_when_max_title_length_unset(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    long_title = "A" * 100

    def fake_get_prs(_org, _repo_filter):
        return ["https://github.com/org/repo/pull/1"]

    def fake_api_request(_path):
        return {
            "base": {"repo": {"name": "repo"}},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 1,
            "deletions": 0,
            "title": long_title,
            "user": {"login": "alice"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "html_url": "https://github.com/org/repo/pull/1",
            "number": 1,
        }

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert long_title in result.output


def test_cli_limit_caps_results(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    def fake_get_prs(_org, _repo_filter):
        return [f"https://github.com/org/repo/pull/{i}" for i in range(1, 6)]

    def fake_api_request(path):
        number = int(path.split("/")[-1])
        return {
            "base": {"repo": {"name": "repo"}},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 1,
            "deletions": 0,
            "title": f"PR number {number}",
            "user": {"login": "alice"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "html_url": f"https://github.com/org/repo/pull/{number}",
            "number": number,
        }

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--limit", "2"])

    assert result.exit_code == 0
    assert result.output.count("PR number") == 2


def _make_pr_fixture(title="Test PR", number=1):
    return {
        "base": {"repo": {"name": "repo"}},
        "mergeable": True,
        "mergeable_state": "clean",
        "additions": 1,
        "deletions": 0,
        "title": title,
        "user": {"login": "alice"},
        "state": "open",
        "changed_files": 1,
        "commits": 1,
        "review_comments": 0,
        "created_at": "2026-01-10T00:00:00Z",
        "html_url": f"https://github.com/org/repo/pull/{number}",
        "number": number,
    }


def test_auto_fit_truncates_title_to_terminal_width(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda _o, _r: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(
        api, "make_github_api_request", lambda _: _make_pr_fixture(title="A" * 200)
    )

    runner = CliRunner()
    term = type("T", (), {"columns": 150})()
    with patch("shutil.get_terminal_size", return_value=term):
        monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
        result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "A" * 200 not in result.output
    assert "…" in result.output


def test_auto_fit_skips_truncation_when_title_fits(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda _o, _r: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(
        api, "make_github_api_request", lambda _: _make_pr_fixture(title="Short title")
    )

    runner = CliRunner()
    term = type("T", (), {"columns": 220})()
    with patch("shutil.get_terminal_size", return_value=term):
        monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
        result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "Short title" in result.output


def test_auto_fit_truncates_repo_and_author_before_dropping(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda _o, _r: ["https://github.com/org/repo/pull/1"]
    )

    def fake_api(_path):
        r = _make_pr_fixture(title="Short")
        r["base"]["repo"]["name"] = "a-very-long-repository-name"
        r["user"]["login"] = "a-very-long-author-name"
        return r

    monkeypatch.setattr(api, "make_github_api_request", fake_api)

    runner = CliRunner()
    term = type("T", (), {"columns": 100})()
    with patch("shutil.get_terminal_size", return_value=term):
        monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
        result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    # Full long names should have been truncated
    assert "a-very-long-repository-name" not in result.output
    assert "a-very-long-author-name" not in result.output


def test_auto_fit_compresses_mergeable_before_dropping(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda _o, _r: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _make_pr_fixture())

    runner = CliRunner()
    term = type("T", (), {"columns": 100})()
    with patch("shutil.get_terminal_size", return_value=term):
        monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
        result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    # "(clean)" reason should be gone if compression kicked in
    assert "(clean)" not in result.output


def test_auto_fit_drops_columns_when_very_narrow(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda _o, _r: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _make_pr_fixture())

    runner = CliRunner()
    term = type("T", (), {"columns": 60})()
    with patch("shutil.get_terminal_size", return_value=term):
        monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
        result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    # At least one droppable column should be absent
    assert "State" not in result.output or "Commits" not in result.output


def test_auto_fit_noop_when_not_tty(monkeypatch):
    """When stdout is not a TTY (e.g. piped), auto-fit must not run."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda _o, _r: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(
        api, "make_github_api_request", lambda _: _make_pr_fixture(title="A" * 200)
    )

    # CliRunner uses a non-TTY stream by default — no patching of isatty
    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "A" * 200 in result.output


def test_explicit_max_title_length_overrides_auto_fit(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda _o, _r: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(
        api, "make_github_api_request", lambda _: _make_pr_fixture(title="A" * 100)
    )

    runner = CliRunner()
    term = type("T", (), {"columns": 220})()
    with patch("shutil.get_terminal_size", return_value=term):
        monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
        result = runner.invoke(
            cli.breakfast, ["-o", "org", "-r", "repo", "--max-title-length", "20"]
        )

    assert result.exit_code == 0
    assert "A" * 19 + "…" in result.output


def test_cli_init_config(monkeypatch):
    from breakfast import cli

    called = []

    def fake_generate():
        called.append(True)
        return True

    monkeypatch.setattr(cli, "generate_default_config", fake_generate)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--init-config"])

    assert result.exit_code == 0
    assert len(called) == 1
