import csv
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import requests
from click.testing import CliRunner

from breakfast import api, cache, cli, renderers


@pytest.fixture(autouse=True)
def stub_review_decision(monkeypatch):
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {
                "repository": {"pullRequest": {"reviewDecision": "REVIEW_REQUIRED"}}
            }
        },
    )


@pytest.fixture(autouse=True)
def isolate_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))


def test_get_pr_age_days():
    pr_detail = {"created_at": "2026-01-10T00:00:00Z"}
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)

    assert cli.get_pr_age_days(pr_detail, now=now) == 5


def test_get_pr_age_days_invalid_or_missing():
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)

    assert cli.get_pr_age_days({}, now=now) == 0
    assert cli.get_pr_age_days({"created_at": "bad-date"}, now=now) == 0


def test_cli_search_invalid_regex():
    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "--search", "[invalid"])
    assert result.exit_code == 1
    assert "not valid regex" in result.stderr


def test_cli_exits_when_token_missing(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", None)
    runner = CliRunner()

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 1
    assert "GITHUB_TOKEN not set" in result.stderr


def test_cli_outputs_table(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    assert "PR-1" in result.stdout
    assert "repo" in result.stdout
    assert "✅ (clean)" in result.stdout


def test_cli_outputs_age_column_when_enabled(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    monkeypatch.setattr(renderers, "get_pr_age_days", lambda _pr_detail, **_kw: 7)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--age"])

    assert result.exit_code == 0
    assert "Age" in result.stdout
    assert "7" in result.stdout


def _fake_pr_detail_with_branches():
    return {
        "base": {
            "ref": "main",
            "repo": {"name": "repo", "owner": {"login": "org"}},
        },
        "head": {"ref": "feature/my-branch", "sha": "abc123"},
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


def test_cli_outputs_head_branch_column_when_enabled(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _org, _repo_filter, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(
        api,
        "make_github_api_request",
        lambda _path: _fake_pr_detail_with_branches(),
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--head-branch"])

    assert result.exit_code == 0
    assert "Head Branch" in result.stdout
    assert "feature/my-branch" in result.stdout


def test_cli_outputs_base_branch_column_when_enabled(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _org, _repo_filter, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(
        api,
        "make_github_api_request",
        lambda _path: _fake_pr_detail_with_branches(),
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--base-branch"])

    assert result.exit_code == 0
    assert "Base Branch" in result.stdout
    assert "main" in result.stdout


def test_cli_head_and_base_branch_hidden_by_default(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _org, _repo_filter, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(
        api,
        "make_github_api_request",
        lambda _path: _fake_pr_detail_with_branches(),
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "Head Branch" not in result.stdout
    assert "Base Branch" not in result.stdout


def test_cli_outputs_json(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    data = json.loads(result.stdout[result.stdout.index("[") :])
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
    monkeypatch.setattr(cli, "get_github_prs", lambda _org, _repo, _state="open": [])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout[result.stdout.index("[") :]) == []


def test_cli_continues_when_one_pr_fetch_fails(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    assert "Good PR" in result.stdout
    assert "Warning" in result.stderr
    assert "Warning" not in result.stdout
    assert "1 PR(s)" in result.stderr


def test_cli_mine_only_filters_to_authenticated_user(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    assert "Alice PR" in result.stdout
    assert "Bob PR" not in result.stdout


def test_cli_mine_only_exits_cleanly_on_rate_limit(monkeypatch):
    from breakfast.api import GitHubRateLimitError

    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_authenticated_user_login",
        lambda: (_ for _ in ()).throw(GitHubRateLimitError("2026-04-10 16:04:48")),
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--mine-only"])

    assert result.exit_code == 1
    assert "rate limit" in result.stderr.lower()
    assert "2026-04-10 16:04:48" in result.stderr


def test_cli_needs_my_review_filters_to_requested_reviewer(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
        return [
            "https://github.com/org/repo/pull/1",
            "https://github.com/org/repo/pull/2",
        ]

    def fake_api_request(path):
        number = 1 if path.endswith("/1") else 2
        title = "Needs Alice Review" if number == 1 else "No Alice Review"
        reviewers = [{"login": "alice"}] if number == 1 else []
        return {
            "base": {"repo": {"name": "repo"}},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 5,
            "deletions": 2,
            "title": title,
            "user": {"login": "bob"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "requested_reviewers": reviewers,
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
        ["-o", "org", "-r", "repo", "--needs-my-review"],
    )

    assert result.exit_code == 0
    assert "Needs Alice Review" in result.stdout
    assert "No Alice Review" not in result.stdout


def test_cli_needs_my_review_login_fetched_once_with_mine_only(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    call_count = {"n": 0}

    def counting_login():
        call_count["n"] += 1
        return "alice"

    def fake_get_prs(_org, _repo_filter, _state="open"):
        return []

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(cli, "get_authenticated_user_login", counting_login)

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--needs-my-review", "--mine-only"],
    )

    assert result.exit_code == 0
    assert call_count["n"] == 1


def test_cli_outputs_checks_column(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    assert "Checks" in result.stdout
    assert "✅ pass" in result.stdout


def test_cli_checks_no_collision_across_repos(monkeypatch):
    """PRs with the same number in different repos must keep separate check statuses."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    assert "pass" in result.stdout
    assert "fail" in result.stdout


def test_cli_checks_not_shown_by_default(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    assert "Checks" not in result.stdout


def test_cli_show_config_includes_status_style_from_config(tmp_path):
    cfg_path = tmp_path / "breakfast.toml"
    cfg_path.write_text(
        'owner = "org"\n'
        'repo-filter = "repo"\n'
        "checks = true\n"
        'status-style = "ascii"\n'
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--config", str(cfg_path), "--show-config"])

    assert result.exit_code == 0
    assert "status-style: ascii" in result.stdout


def test_cli_json_includes_checks_when_enabled(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    data = json.loads(result.stdout[result.stdout.index("[") :])
    assert data[0]["checks"] == "fail"


def test_cli_json_excludes_checks_by_default(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    data = json.loads(result.stdout[result.stdout.index("[") :])
    assert "checks" not in data[0]


def _make_pr_detail(number=1, owner="org", repo="repo", pr_id=1001):
    return {
        "base": {
            "repo": {
                "name": repo,
                "owner": {"login": owner},
            },
            "ref": "main",
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
        "updated_at": "2026-01-11T00:00:00Z",
        "html_url": f"https://github.com/{owner}/{repo}/pull/{number}",
        "number": number,
        "id": pr_id,
        "labels": [],
        "requested_reviewers": [],
        "draft": False,
    }


def test_cli_outputs_approvals_column(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    pr_detail = _make_pr_detail()

    def fake_get_prs(_org, _repo_filter, _state="open"):
        return ["https://github.com/org/repo/pull/1"]

    def fake_api_request(path):
        if "/reviews" in path:
            return [{"user": {"login": "bob"}, "state": "APPROVED"}]
        return pr_detail

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {"repository": {"pullRequest": {"reviewDecision": "APPROVED"}}}
        },
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--approvals"])

    assert result.exit_code == 0
    assert "Approved" in result.stdout
    assert "✅ approved" in result.stdout


def test_cli_renders_review_required_for_incomplete_reviews(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    pr_detail = _make_pr_detail()

    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _org, _repo_filter, _s="open": ["https://github.com/org/repo/pull/1"],
    )

    def fake_api_request(path):
        if "/reviews" in path:
            return []
        return pr_detail

    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {
                "repository": {"pullRequest": {"reviewDecision": "REVIEW_REQUIRED"}}
            }
        },
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--approvals"])

    assert result.exit_code == 0
    assert "⏳ pending" in result.stdout


def test_cli_renders_approval_counts_for_multi_review_branch(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    pr_detail = _make_pr_detail()

    def fake_api_request(path):
        if "/reviews" in path:
            return [{"user": {"login": "bob"}, "state": "APPROVED"}]
        if path.endswith("/branches/main/protection/required_pull_request_reviews"):
            return {"required_approving_review_count": 2}
        return pr_detail

    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _org, _repo_filter, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {
                "repository": {"pullRequest": {"reviewDecision": "REVIEW_REQUIRED"}}
            }
        },
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--approvals"])

    assert result.exit_code == 0
    assert "✅ 1/2 approvals" in result.stdout


def test_cli_approvals_not_shown_by_default(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    pr_detail = _make_pr_detail()

    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _o, _r, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _path: pr_detail)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "Approved" not in result.stdout


def test_cli_json_includes_approval_when_enabled(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    pr_detail = _make_pr_detail()

    def fake_api_request(path):
        if "/reviews" in path:
            return [{"user": {"login": "bob"}, "state": "CHANGES_REQUESTED"}]
        return pr_detail

    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _o, _r, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {
                "repository": {"pullRequest": {"reviewDecision": "CHANGES_REQUESTED"}}
            }
        },
    )

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--json", "--approvals"]
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout[result.stdout.index("[") :])
    assert data[0]["approval"] == "changes"


def test_cli_json_includes_approval_counts_when_available(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    pr_detail = _make_pr_detail()

    def fake_api_request(path):
        if "/reviews" in path:
            return [{"user": {"login": "bob"}, "state": "APPROVED"}]
        if path.endswith("/branches/main/protection/required_pull_request_reviews"):
            return {"required_approving_review_count": 2}
        return pr_detail

    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _o, _r, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)
    monkeypatch.setattr(
        api,
        "make_github_graphql_request",
        lambda query, variables: {
            "data": {
                "repository": {"pullRequest": {"reviewDecision": "REVIEW_REQUIRED"}}
            }
        },
    )

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--json", "--approvals"]
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout[result.stdout.index("[") :])
    assert data[0]["approval"] == "pending"
    assert data[0]["approval_current"] == 1
    assert data[0]["approval_required"] == 2


def test_cli_json_excludes_approval_by_default(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    pr_detail = _make_pr_detail()

    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _o, _r, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _path: pr_detail)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout[result.stdout.index("[") :])
    assert "approval" not in data[0]


def test_cli_approvals_config_file(tmp_path):
    cfg_path = tmp_path / "breakfast.toml"
    cfg_path.write_text('owner = "org"\nrepo-filter = "repo"\napprovals = true\n')

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--config", str(cfg_path), "--show-config"])

    assert result.exit_code == 0
    assert "approvals: True" in result.stdout


def test_no_update_check_flag_skips_update(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "get_github_prs", lambda _o, _r, _s="open": [])
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
    monkeypatch.setattr(cli, "get_github_prs", lambda _o, _r, _s="open": [])
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


def test_cli_exclude_repo_filtering(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    mock_urls = [
        "https://github.com/org/repo-one/pull/1",
        "https://github.com/org/exclude-me/pull/2",
        "https://github.com/malformed-url-no-repo",
    ]
    monkeypatch.setattr(cli, "get_github_prs", lambda _o, _r, _s="open": mock_urls)

    fetched_urls = []

    def fake_fetch_pr_detail(url):
        fetched_urls.append(url)
        return {
            "id": hash(url),
            "base": {"repo": {"name": "repo"}},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 1,
            "deletions": 0,
            "title": "Some PR",
            "user": {"login": "alice"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "html_url": url,
            "number": 1,
        }

    monkeypatch.setattr(cli, "_fetch_pr_detail", fake_fetch_pr_detail)
    monkeypatch.setattr(cli, "render_pr_summary", lambda *a, **k: "PR SUMMARY")

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "--exclude-repo", "exclude-me"],
    )

    assert result.exit_code == 0
    assert "https://github.com/org/repo-one/pull/1" in fetched_urls
    assert "https://github.com/org/exclude-me/pull/2" not in fetched_urls
    assert "https://github.com/malformed-url-no-repo" in fetched_urls


def test_cli_truncates_title_when_max_title_length_set(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    long_title = "A" * 100

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    assert long_title not in result.stdout
    assert "A" * 19 + "…" in result.stdout


def test_cli_does_not_truncate_title_when_max_title_length_unset(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    long_title = "A" * 100

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    assert long_title in result.stdout


def test_cli_limit_caps_results(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    assert result.stdout.count("PR number") == 2


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


def test_cli_status_columns_use_ascii_to_keep_rows_aligned(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
        return [
            "https://github.com/org/repo/pull/1",
            "https://github.com/org/repo/pull/2",
            "https://github.com/org/repo/pull/3",
            "https://github.com/org/repo/pull/4",
        ]

    pr_details = {
        "/repos/org/repo/pulls/1": _make_pr_fixture(number=1),
        "/repos/org/repo/pulls/2": _make_pr_fixture(number=2),
        "/repos/org/repo/pulls/3": _make_pr_fixture(number=3),
        "/repos/org/repo/pulls/4": _make_pr_fixture(number=4),
    }
    for idx, pr_detail in enumerate(pr_details.values(), start=1):
        pr_detail["base"]["repo"]["owner"] = {"login": "org"}
        pr_detail["head"] = {"sha": f"sha-{idx}"}
        pr_detail["id"] = 1000 + idx

    pr_details["/repos/org/repo/pulls/3"]["mergeable"] = False
    pr_details["/repos/org/repo/pulls/3"]["mergeable_state"] = "dirty"
    pr_details["/repos/org/repo/pulls/4"]["mergeable_state"] = "blocked"

    check_runs = {
        "/repos/org/repo/commits/sha-1/check-runs": {
            "check_runs": [{"status": "completed", "conclusion": "success"}]
        },
        "/repos/org/repo/commits/sha-1/status": {"statuses": []},
    }

    check_runs["/repos/org/repo/commits/sha-2/check-runs"] = {
        "check_runs": [{"status": "in_progress", "conclusion": None}]
    }
    check_runs["/repos/org/repo/commits/sha-2/status"] = {"statuses": []}
    check_runs["/repos/org/repo/commits/sha-3/check-runs"] = {
        "check_runs": [{"status": "completed", "conclusion": "failure"}]
    }
    check_runs["/repos/org/repo/commits/sha-3/status"] = {"statuses": []}
    check_runs["/repos/org/repo/commits/sha-4/check-runs"] = {"check_runs": []}
    check_runs["/repos/org/repo/commits/sha-4/status"] = {"statuses": []}

    def fake_api_request(path):
        if path in check_runs:
            return check_runs[path]
        return pr_details[path]

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--checks", "--status-style", "ascii"],
    )

    assert result.exit_code == 0
    assert "yes (clean)" in result.stdout
    assert "no (dirty)" in result.stdout
    assert "pending" in result.stdout
    assert "✅" not in result.stdout
    assert "❌" not in result.stdout
    assert "⚠️" not in result.stdout
    assert "➖" not in result.stdout

    table_lines = [
        renderers._strip_ansi(line)
        for line in result.stdout.splitlines()
        if line.startswith(("+", "|"))
    ]
    widths = {len(line) for line in table_lines}

    assert len(widths) == 1


def test_auto_fit_truncates_title_to_terminal_width(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _o, _r, _s="open": ["https://github.com/org/repo/pull/1"],
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
    assert "A" * 200 not in result.stdout
    assert "…" in result.stdout


def test_auto_fit_skips_truncation_when_title_fits(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _o, _r, _s="open": ["https://github.com/org/repo/pull/1"],
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
    assert "Short title" in result.stdout


def test_auto_fit_truncates_repo_and_author_before_dropping(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _o, _r, _s="open": ["https://github.com/org/repo/pull/1"],
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
    visible_output = renderers._strip_ansi(result.stdout)
    # Full long names should have been truncated
    assert "a-very-long-repository-name" not in visible_output
    assert "a-very-long-author-name" not in visible_output
    assert "a-very-…" in visible_output


def test_auto_fit_compresses_mergeable_before_dropping(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _o, _r, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _make_pr_fixture())

    runner = CliRunner()
    term = type("T", (), {"columns": 100})()
    with patch("shutil.get_terminal_size", return_value=term):
        monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
        result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    # "(clean)" reason should be gone if compression kicked in
    assert "(clean)" not in result.stdout


def test_auto_fit_drops_columns_when_very_narrow(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _o, _r, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _make_pr_fixture())

    runner = CliRunner()
    term = type("T", (), {"columns": 60})()
    with patch("shutil.get_terminal_size", return_value=term):
        monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
        result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    # At least one droppable column should be absent
    assert "State" not in result.stdout or "Commits" not in result.stdout


def test_auto_fit_noop_when_not_tty(monkeypatch):
    """When stdout is not a TTY (e.g. piped), auto-fit must not run."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _o, _r, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(
        api, "make_github_api_request", lambda _: _make_pr_fixture(title="A" * 200)
    )

    # CliRunner uses a non-TTY stream by default — no patching of isatty
    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "A" * 200 in result.stdout


def test_explicit_max_title_length_overrides_auto_fit(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _o, _r, _s="open": ["https://github.com/org/repo/pull/1"],
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
    assert "A" * 19 + "…" in result.stdout


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


# ---------------------------------------------------------------------------
# Cache integration tests
# ---------------------------------------------------------------------------


def _make_pr_detail(number=1, repo="repo"):
    return {
        "base": {
            "repo": {"name": repo, "owner": {"login": "org"}},
            "ref": "main",
        },
        "head": {"sha": "abc123"},
        "mergeable": True,
        "mergeable_state": "clean",
        "additions": 5,
        "deletions": 2,
        "title": f"PR number {number}",
        "user": {"login": "alice"},
        "state": "open",
        "changed_files": 1,
        "commits": 1,
        "review_comments": 0,
        "created_at": "2026-01-10T00:00:00Z",
        "html_url": f"https://github.com/org/{repo}/pull/{number}",
        "number": number,
        "id": 1000 + number,
    }


def test_cache_hit_skips_get_github_prs(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    # Pre-populate cache
    cache.write_pr_cache("org", "repo", [_make_pr_detail(1)])

    api_called = []
    monkeypatch.setattr(cli, "get_github_prs", lambda *a: api_called.append(1) or [])

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--cache"])

    assert result.exit_code == 0
    assert len(api_called) == 0, "get_github_prs should not be called on a cache hit"
    assert "PR number 1" in result.stdout


def test_no_cache_flag_always_fetches(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    # Pre-populate cache
    cache.write_pr_cache("org", "repo", [_make_pr_detail(99)])

    api_called = []

    def fake_get_prs(_org, _repo, _s="open"):
        api_called.append(1)
        return ["https://github.com/org/repo/pull/1"]

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _make_pr_detail(1))

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--no-cache"])

    assert result.exit_code == 0
    assert len(api_called) == 1, "get_github_prs must be called when --no-cache is set"


def test_no_cache_flag_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    monkeypatch.setattr(cli, "get_github_prs", lambda *a: [])

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--no-cache"])

    assert result.exit_code == 0
    assert list(tmp_path.glob("prs_*.json")) == []


def test_invalid_cache_ttl_exits_with_code_1(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--cache-ttl", "0"]
    )

    assert result.exit_code == 1
    assert "invalid" in result.stderr.lower() or "cache-ttl" in result.stderr.lower()


def test_config_cache_ttl_respected(monkeypatch, tmp_path):
    """cache-ttl = "5m" in config is honoured when no CLI flag given."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    # Simulate config returning cache = true and cache-ttl = "5m"
    monkeypatch.setattr(
        cli, "load_config", lambda _: {"cache": True, "cache-ttl": "5m"}
    )

    cache.write_pr_cache("org", "repo", [_make_pr_detail(7)])

    api_called = []
    monkeypatch.setattr(cli, "get_github_prs", lambda *a: api_called.append(1) or [])

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert len(api_called) == 0, "cache-ttl from config should be honoured"


def test_corrupt_cache_falls_back_to_live_fetch(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    # Write corrupt cache file
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = cache.cache_path("org", "repo")
    path.write_text("}{bad json")

    api_called = []

    def fake_get_prs(*a):
        api_called.append(1)
        return ["https://github.com/org/repo/pull/1"]

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _make_pr_detail(1))

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert len(api_called) == 1, "corrupt cache should fall back to live fetch"
    assert "PR number 1" in result.stdout


def test_pr_results_grouped_by_repo(monkeypatch, tmp_path):
    """PRs from multiple repos should appear grouped by repo name in the output."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    def make_pr(number, repo):
        pr = _make_pr_detail(number)
        pr["base"]["repo"]["name"] = repo
        pr["html_url"] = f"https://github.com/org/{repo}/pull/{number}"
        return pr

    # Store PRs in reverse-alphabetical order; sorting should fix this
    prs = [
        make_pr(3, "zebra-service"),
        make_pr(1, "alpha-service"),
        make_pr(2, "alpha-service"),
    ]
    cache.write_pr_cache("org", "svc", prs)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "svc", "--cache"])

    assert result.exit_code == 0
    alpha_pos = result.stdout.index("alpha-service")
    zebra_pos = result.stdout.index("zebra-service")
    assert alpha_pos < zebra_pos, "repos should appear in alphabetical order"


def test_refresh_without_cache_exits_with_error(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--refresh"])

    assert result.exit_code == 1
    assert "requires the cache to be enabled" in result.stderr
    assert "--cache" in result.stderr


def test_refresh_prs_without_cache_exits_with_error(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--refresh-prs"])

    assert result.exit_code == 1
    assert "requires the cache to be enabled" in result.stderr
    assert "--cache" in result.stderr


def test_refresh_ignores_cache_and_writes_fresh(monkeypatch, tmp_path):
    """--refresh bypasses the cache read but still writes fresh data back."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    # Pre-populate cache with stale data
    cache.write_pr_cache("org", "repo", [_make_pr_detail(99)])

    api_called = []

    def fake_get_prs(*a):
        api_called.append(1)
        return ["https://github.com/org/repo/pull/1"]

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _make_pr_detail(1))

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--cache", "--refresh"]
    )

    assert result.exit_code == 0
    assert len(api_called) == 1, "--refresh should always fetch fresh"
    assert "PR number 1" in result.stdout
    # Cache should now contain fresh data
    cached = cache.read_pr_cache("org", "repo", 300)
    assert cached is not None
    assert cached["prs"][0]["number"] == 1


def test_refresh_does_not_use_cached_data(monkeypatch, tmp_path):
    """--refresh must not serve stale data even when cache is warm."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    cache.write_pr_cache("org", "repo", [_make_pr_detail(99)])

    monkeypatch.setattr(
        cli, "get_github_prs", lambda *a: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _make_pr_detail(1))

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--cache", "--refresh"]
    )

    assert result.exit_code == 0
    assert "PR number 99" not in result.stdout, "stale cached PR should not appear"
    assert "PR number 1" in result.stdout


def test_refresh_prs_uses_graphql_cache_skips_pr_cache(monkeypatch, tmp_path):
    """--refresh-prs uses the cached URL list but re-fetches PR details."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)
    monkeypatch.setattr(cli, "read_graphql_cache", cache.read_graphql_cache)
    monkeypatch.setattr(cli, "write_graphql_cache", cache.write_graphql_cache)

    # Warm PR detail cache (stale) and GraphQL cache
    cache.write_pr_cache("org", "repo", [_make_pr_detail(99)])
    cache.write_graphql_cache(
        "org", "repo", ["https://api.github.com/repos/org/repo/pulls/1"]
    )

    graphql_called = []
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *a: graphql_called.append(1) or []
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _make_pr_detail(1))

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--cache", "--refresh-prs"]
    )

    assert result.exit_code == 0
    assert len(graphql_called) == 0, "--refresh-prs should use cached GraphQL result"
    assert "PR number 99" not in result.stdout, "stale PR cache should be bypassed"
    assert "PR number 1" in result.stdout


def test_refresh_prs_writes_fresh_pr_cache(monkeypatch, tmp_path):
    """--refresh-prs writes fresh PR details back to cache."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)
    monkeypatch.setattr(cli, "read_graphql_cache", cache.read_graphql_cache)
    monkeypatch.setattr(cli, "write_graphql_cache", cache.write_graphql_cache)

    cache.write_graphql_cache(
        "org", "repo", ["https://api.github.com/repos/org/repo/pulls/1"]
    )
    monkeypatch.setattr(cli, "get_github_prs", lambda *a: [])
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _make_pr_detail(1))

    runner = CliRunner()
    runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--cache", "--refresh-prs"]
    )

    cached = cache.read_pr_cache("org", "repo", 300)
    assert cached is not None, "--refresh-prs should write fresh data to PR cache"


# ---------------------------------------------------------------------------
# Per-repo PR cache tests
# ---------------------------------------------------------------------------


def test_per_repo_cache_hit_skips_fetch(monkeypatch, tmp_path):
    """When per-repo cache has a fresh entry, that repo's PRs are not fetched."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_repo_pr_cache", cache.read_repo_pr_cache)
    monkeypatch.setattr(cli, "write_repo_pr_cache", cache.write_repo_pr_cache)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)
    monkeypatch.setattr(cli, "read_graphql_cache", cache.read_graphql_cache)
    monkeypatch.setattr(cli, "write_graphql_cache", cache.write_graphql_cache)

    # Pre-populate the GraphQL URL cache and per-repo PR cache
    cache.write_graphql_cache("org", "repo", ["https://github.com/org/repo/pull/42"])
    cache.write_repo_pr_cache("org", "repo", [_make_pr_detail(42, repo="repo")])

    fetch_called = []
    monkeypatch.setattr(cli, "get_github_prs", lambda *a: fetch_called.append(1) or [])

    def _should_not_be_called(_url):
        raise AssertionError("REST API should not be called on per-repo cache hit")

    monkeypatch.setattr(api, "make_github_api_request", _should_not_be_called)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--cache"])

    assert result.exit_code == 0, result.output
    assert "PR number 42" in result.stdout
    assert len(fetch_called) == 0


def test_per_repo_cache_partial_hit(monkeypatch, tmp_path):
    """When one repo is cached and another is not, only the uncached repo is fetched."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_repo_pr_cache", cache.read_repo_pr_cache)
    monkeypatch.setattr(cli, "write_repo_pr_cache", cache.write_repo_pr_cache)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)
    monkeypatch.setattr(cli, "read_graphql_cache", cache.read_graphql_cache)
    monkeypatch.setattr(cli, "write_graphql_cache", cache.write_graphql_cache)

    # repo-a is cached, repo-b is not
    cache.write_graphql_cache(
        "org",
        "",
        [
            "https://github.com/org/repo-a/pull/1",
            "https://github.com/org/repo-b/pull/2",
        ],
    )
    cache.write_repo_pr_cache("org", "repo-a", [_make_pr_detail(1, repo="repo-a")])

    fetched_urls = []

    def fake_rest(url):
        # _fetch_pr_detail converts https://github.com/org/repo-b/pull/2 →
        # /repos/org/repo-b/pulls/2
        fetched_urls.append(url)
        if "repo-b" in url and "2" in url:
            return _make_pr_detail(2, repo="repo-b")
        raise AssertionError(f"unexpected REST URL: {url}")

    monkeypatch.setattr(cli, "get_github_prs", lambda *a: [])
    monkeypatch.setattr(api, "make_github_api_request", fake_rest)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "", "--cache"])

    assert result.exit_code == 0, result.output
    assert "PR number 1" in result.stdout
    assert "PR number 2" in result.stdout
    # Only repo-b's PR should have been fetched via REST
    assert any("repo-b" in u for u in fetched_urls)
    assert not any("repo-a" in u for u in fetched_urls)


def test_per_repo_cache_writes_after_fetch(monkeypatch, tmp_path):
    """After fetching fresh PRs, a per-repo cache file is written for each repo."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_repo_pr_cache", cache.read_repo_pr_cache)
    monkeypatch.setattr(cli, "write_repo_pr_cache", cache.write_repo_pr_cache)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda *a: ["https://github.com/org/myrepo/pull/7"],
    )
    monkeypatch.setattr(
        api,
        "make_github_api_request",
        lambda _: _make_pr_detail(7, repo="myrepo"),
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--cache"])

    assert result.exit_code == 0, result.output
    cached = cache.read_repo_pr_cache("org", "myrepo", 300)
    assert cached is not None, "per-repo cache should be written after fetch"
    assert len(cached["prs"]) == 1
    assert cached["prs"][0]["number"] == 7


def test_per_repo_cache_expired_triggers_refetch(monkeypatch, tmp_path):
    """An expired per-repo cache entry causes a fresh fetch for that repo."""
    import json as _json
    from datetime import timedelta

    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_repo_pr_cache", cache.read_repo_pr_cache)
    monkeypatch.setattr(cli, "write_repo_pr_cache", cache.write_repo_pr_cache)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)
    monkeypatch.setattr(cli, "read_graphql_cache", cache.read_graphql_cache)
    monkeypatch.setattr(cli, "write_graphql_cache", cache.write_graphql_cache)

    # Write per-repo cache, then backdate it to expire
    cache.write_graphql_cache("org", "repo", ["https://github.com/org/repo/pull/5"])
    cache.write_repo_pr_cache("org", "repo", [_make_pr_detail(99, repo="repo")])
    path = cache.repo_pr_cache_path("org", "repo")
    data = _json.loads(path.read_text())
    from datetime import datetime, timezone

    old_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(_json.dumps(data))

    fetch_calls = []
    monkeypatch.setattr(cli, "get_github_prs", lambda *a: [])
    monkeypatch.setattr(
        api,
        "make_github_api_request",
        lambda _: fetch_calls.append(1) or _make_pr_detail(5, repo="repo"),
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--cache"])

    assert result.exit_code == 0, result.output
    assert len(fetch_calls) >= 1, "expired per-repo cache should trigger a fresh fetch"
    assert "PR number 5" in result.stdout


# ---------------------------------------------------------------------------
# Legendary PR tests
# ---------------------------------------------------------------------------


def test_is_legendary_meets_both_conditions():
    """A PR with 100+ comments AND open 30+ days is legendary."""
    from datetime import datetime, timezone

    now = datetime(2026, 2, 15, tzinfo=timezone.utc)
    pr = {
        "comments": 80,
        "review_comments": 20,
        "created_at": "2026-01-01T00:00:00Z",  # 45 days old
    }
    assert cli.is_legendary(pr, now=now)


def test_is_not_legendary_high_comments_but_fresh():
    """100+ comments alone is not enough — must also be 30+ days old."""
    from datetime import datetime, timezone

    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    pr = {
        "comments": 80,
        "review_comments": 20,
        "created_at": "2026-01-14T00:00:00Z",  # only 1 day old
    }
    assert not cli.is_legendary(pr, now=now)


def test_is_not_legendary_old_but_few_comments():
    """30+ days open alone is not enough — must also have 100+ comments."""
    from datetime import datetime, timezone

    now = datetime(2026, 2, 15, tzinfo=timezone.utc)
    pr = {
        "comments": 0,
        "review_comments": 0,
        "created_at": "2026-01-01T00:00:00Z",  # 45 days old
    }
    assert not cli.is_legendary(pr, now=now)


def test_is_not_legendary_fresh_few_comments():
    """A recent PR with few comments is not legendary."""
    from datetime import datetime, timezone

    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    pr = {
        "comments": 5,
        "review_comments": 3,
        "created_at": "2026-01-10T00:00:00Z",  # 5 days old
    }
    assert not cli.is_legendary(pr, now=now)


def test_is_legendary_exactly_at_both_thresholds():
    """Exactly 100 comments AND exactly 30 days old triggers legendary."""
    from datetime import datetime, timezone

    now = datetime(2026, 2, 9, tzinfo=timezone.utc)
    pr = {
        "comments": 60,
        "review_comments": 40,
        "created_at": "2026-01-10T00:00:00Z",  # exactly 30 days
    }
    assert cli.is_legendary(pr, now=now)


def test_cli_legendary_flag_annotates_state(monkeypatch):
    """--legendary appends ⚔️ to the State of qualifying PRs."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    # A PR that qualifies as legendary (very old AND many comments)
    legendary_pr = {
        **_make_pr_detail(1),
        "title": "Ancient PR",
        "comments": 60,
        "review_comments": 40,
        "created_at": "2025-01-01T00:00:00Z",
    }

    monkeypatch.setattr(
        cli, "get_github_prs", lambda *a: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: legendary_pr)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--legendary"])

    assert result.exit_code == 0
    assert "⚔️" in result.stdout, "legendary PR should have sword emoji in State"


def test_cli_legendary_off_by_default(monkeypatch):
    """Without --legendary, no sword emoji appears even for qualifying PRs."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    old_pr = {
        **_make_pr_detail(1),
        "comments": 0,
        "review_comments": 0,
        "created_at": "2020-01-01T00:00:00Z",
    }

    monkeypatch.setattr(
        cli, "get_github_prs", lambda *a: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: old_pr)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "⚔️" not in result.stdout


def test_cli_legendary_only_filters_non_legendary(monkeypatch):
    """--legendary-only shows only PRs that qualify as legendary."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    # A fresh PR — should be filtered out
    fresh_pr = {
        **_make_pr_detail(1),
        "title": "Fresh PR",
        "comments": 0,
        "review_comments": 0,
        "created_at": "2026-03-22T00:00:00Z",
    }

    monkeypatch.setattr(
        cli, "get_github_prs", lambda *a: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: fresh_pr)

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--legendary-only"]
    )

    assert result.exit_code == 0
    assert "Fresh PR" not in result.stdout


def test_cli_legendary_only_implies_legendary_marking(monkeypatch):
    """--legendary-only implies --legendary so the ⚔️ marker is applied."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    legendary_pr = {
        **_make_pr_detail(1),
        "title": "Ancient PR",
        "comments": 60,
        "review_comments": 40,
        "created_at": "2025-01-01T00:00:00Z",
    }

    monkeypatch.setattr(
        cli, "get_github_prs", lambda *a: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: legendary_pr)

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--legendary-only"]
    )

    assert result.exit_code == 0
    assert "⚔️" in result.stdout


# ---------------------------------------------------------------------------
# Colour grading / ANSI preservation tests (from #122)
# ---------------------------------------------------------------------------


def test_no_drafts_and_drafts_only_are_mutually_exclusive(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "--no-drafts", "--drafts-only"])

    assert result.exit_code == 1
    assert "mutually exclusive" in result.stderr.lower()


def test_cli_repo_and_author_are_hyperlinks(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    pr = _make_pr_fixture(number=1)
    pr["base"]["repo"]["html_url"] = "https://github.com/myorg/myrepo"
    pr["user"]["html_url"] = "https://github.com/alice"

    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/myorg/myrepo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _path: pr)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "myorg", "-r", "myrepo"])

    assert result.exit_code == 0
    assert "\x1b]8;;https://github.com/myorg/myrepo\x1b\\" in result.stdout
    assert "\x1b]8;;https://github.com/alice\x1b\\" in result.stdout


def test_cli_checks_column_links_to_checks_tab(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    pr = _make_pr_fixture(number=7)
    pr["base"]["repo"]["owner"] = {"login": "org"}
    pr["head"] = {"sha": "abc123"}
    pr["id"] = 9007

    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/7"]
    )

    def fake_api(path):
        if "check-runs" in path:
            return {"check_runs": [{"status": "completed", "conclusion": "success"}]}
        if "status" in path:
            return {"statuses": []}
        return pr

    monkeypatch.setattr(api, "make_github_api_request", fake_api)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--checks"])

    assert result.exit_code == 0
    assert "\x1b]8;;https://github.com/org/repo/pull/7/checks\x1b\\" in result.stdout


def test_progress_emoji_emitted_after_check_status_fetch(monkeypatch):
    """Emoji must appear only after the full bundle (detail + checks) is fetched.

    Regression for #142: the old code emitted the emoji as soon as PR detail
    completed, before check/approval statuses were fetched, causing a silent
    delay after the progress line showed ...Done.
    """
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    pr = _make_pr_fixture(number=1)
    pr["base"]["repo"]["owner"] = {"login": "org"}
    pr["head"] = {"sha": "sha-abc"}
    pr["id"] = 5001

    call_log = []

    original_bundle = cli._fetch_pr_bundle

    def tracked_bundle(url, fetch_checks, fetch_approvals):
        result = original_bundle(url, fetch_checks, fetch_approvals)
        call_log.append("bundle_complete")
        return result

    monkeypatch.setattr(cli, "_fetch_pr_bundle", tracked_bundle)

    original_echo = cli.click.echo

    def tracked_echo(msg=None, **kwargs):
        if msg == "*":
            call_log.append("emoji")
        original_echo(msg, **kwargs)

    monkeypatch.setattr(cli.click, "echo", tracked_echo)

    def fake_api(path):
        if "check-runs" in path:
            call_log.append("check_status_fetched")
            return {"check_runs": [{"status": "completed", "conclusion": "success"}]}
        if "status" in path:
            return {"statuses": []}
        return pr

    monkeypatch.setattr(api, "make_github_api_request", fake_api)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--checks"])

    assert result.exit_code == 0

    # check_status_fetched must come before emoji in the log
    assert "check_status_fetched" in call_log, "get_check_status was never called"
    assert "emoji" in call_log, "progress emoji was never emitted"
    check_idx = call_log.index("check_status_fetched")
    emoji_idx = call_log.index("emoji")
    assert check_idx < emoji_idx, (
        f"Expected check status fetch (pos {check_idx}) before emoji "
        f"(pos {emoji_idx}); got call_log={call_log}"
    )

    # bundle_complete appears exactly once — no second bulk-fetch phase
    assert call_log.count("bundle_complete") == 1
    assert call_log.count("check_status_fetched") == 1


def test_debug_flag_prints_summary_to_stderr(monkeypatch):
    """--debug emits a summary block to stderr without disrupting stdout output."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_api_stats",
        lambda: {
            "rest_calls": 10,
            "graphql_calls": 2,
            "rest_rate_limit_remaining": 4990,
            "rest_rate_limit_reset": 1700000000,
        },
    )
    monkeypatch.setattr(
        cli,
        "get_graphql_rate_limit",
        lambda: {
            "remaining": 4998,
            "resetAt": "2026-04-11T10:30:00Z",
        },
    )

    def fake_get_prs(_org, _repo_filter, _state="open"):
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
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--api-stats"])

    assert result.exit_code == 0
    assert "Debug summary" in result.stderr
    assert "12 (10 REST + 2 GraphQL)" in result.stderr
    assert "4990 requests remaining" in result.stderr
    assert "4998 points remaining" in result.stderr
    # Normal table output is still present on stdout
    assert "PR-1" in result.stdout


def _plain_pr():
    return {
        "base": {"repo": {"name": "repo", "html_url": "https://github.com/org/repo"}},
        "mergeable": True,
        "mergeable_state": "clean",
        "additions": 5,
        "deletions": 2,
        "title": "Test PR",
        "user": {"login": "alice", "html_url": "https://github.com/alice"},
        "state": "open",
        "draft": False,
        "changed_files": 1,
        "commits": 1,
        "review_comments": 0,
        "created_at": "2026-01-10T00:00:00Z",
        "html_url": "https://github.com/org/repo/pull/1",
        "number": 1,
        "id": 1,
    }


def test_no_colour_strips_ansi_from_table(monkeypatch):
    """--no-colour produces output with no ANSI escape sequences."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _plain_pr())

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--no-colour"])

    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout
    assert "PR-1" in result.stdout


def test_no_color_alias_works(monkeypatch):
    """--no-color (US spelling) is accepted and strips ANSI."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _plain_pr())

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--no-color"])

    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout


# ---------------------------------------------------------------------------
# Colour diagnostics (#189)
# ---------------------------------------------------------------------------


def test_colour_diagnostics_flag_exits_zero_and_outputs_swatches():
    """--colour-diagnostics prints swatch output and exits 0 without needing a token."""
    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--colour-diagnostics"])
    assert result.exit_code == 0
    assert "Seasonal colours" in result.stdout
    assert "Check status" in result.stdout
    assert "Number gradient" in result.stdout


def test_color_diagnostics_alias_works():
    """--color-diagnostics (US spelling) is accepted."""
    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--color-diagnostics"])
    assert result.exit_code == 0
    assert "Seasonal colours" in result.stdout


# ---------------------------------------------------------------------------
# Seasonal colours (#168)
# ---------------------------------------------------------------------------


def test_seasonal_colours_no_colour_suppresses_them(monkeypatch):
    """--no-colour must suppress seasonal ANSI colour codes on title and author."""

    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _plain_pr())

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--no-colour"])

    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout


def test_seasonal_colours_disabled_by_config(monkeypatch, tmp_path):
    """seasonal-colours = false in config disables the seasonal ANSI codes."""

    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _: _plain_pr())

    cfg_file = tmp_path / "test.toml"
    cfg_file.write_text("seasonal-colours = false\n")

    runner = CliRunner()
    # In non-TTY output, colour is suppressed anyway; test the config path by
    # verifying the command runs without error and title text is unmodified.
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--config", str(cfg_file)],
    )

    assert result.exit_code == 0
    assert "Test PR" in result.stdout


# ---------------------------------------------------------------------------
# PR summary views (#177)
# ---------------------------------------------------------------------------


def _two_author_prs():
    """Return a pair of PR detail URLs for two different authors."""
    return [
        "https://github.com/org/repo/pull/1",
        "https://github.com/org/repo/pull/2",
    ]


def _fake_pr_for_summary(path):
    pr_number = int(path.split("/pulls/")[1])
    authors = {1: "alice", 2: "bob"}
    repos = {1: "repo-a", 2: "repo-b"}
    return {
        "base": {
            "repo": {
                "name": repos[pr_number],
                "html_url": f"https://github.com/org/{repos[pr_number]}",
                "owner": {"login": "org"},
            }
        },
        "head": {"ref": "feature", "sha": "abc123"},
        "mergeable": True,
        "mergeable_state": "clean",
        "additions": 5,
        "deletions": 2,
        "title": f"PR by {authors[pr_number]}",
        "user": {
            "login": authors[pr_number],
            "html_url": f"https://github.com/{authors[pr_number]}",
        },
        "state": "open",
        "draft": False,
        "changed_files": 1,
        "commits": 1,
        "review_comments": 0,
        "created_at": "2026-01-10T00:00:00Z",
        "html_url": f"https://github.com/org/{repos[pr_number]}/pull/{pr_number}",
        "number": pr_number,
        "id": pr_number,
    }


def test_summarise_user_prs_shows_author_summary(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cli, "get_github_prs", lambda *_: _two_author_prs())
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_for_summary)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "--summarise-user-prs"])

    assert result.exit_code == 0
    assert "PR Summary by Author" in result.stdout
    assert "alice" in result.stdout
    assert "bob" in result.stdout
    # Table columns must NOT appear
    assert "PR Title" not in result.stdout


def test_summarise_repo_prs_shows_repo_summary(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cli, "get_github_prs", lambda *_: _two_author_prs())
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_for_summary)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "--summarise-repo-prs"])

    assert result.exit_code == 0
    assert "PR Summary by Repo" in result.stdout
    assert "repo-a" in result.stdout
    assert "repo-b" in result.stdout
    assert "PR Title" not in result.stdout


def test_summarise_user_and_repo_mutually_exclusive(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "--summarise-user-prs", "--summarise-repo-prs"],
    )

    assert result.exit_code == 1
    assert "mutually exclusive" in result.stderr


def test_summarise_user_prs_empty_shows_no_prs_message(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cli, "get_github_prs", lambda *_: [])

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "--summarise-user-prs"])

    assert result.exit_code == 0
    assert "no PRs" in result.stdout


def test_summarise_repo_prs_no_colour(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cli, "get_github_prs", lambda *_: _two_author_prs())
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_for_summary)

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast, ["-o", "org", "--summarise-repo-prs", "--no-colour"]
    )

    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout


# ---------------------------------------------------------------------------
# stdout / stderr separation
# ---------------------------------------------------------------------------


def _fake_pr_detail(_path):
    return {
        "base": {
            "repo": {
                "name": "repo",
                "html_url": "https://github.com/org/repo",
                "owner": {"login": "org"},
            }
        },
        "mergeable": True,
        "mergeable_state": "clean",
        "additions": 5,
        "deletions": 2,
        "title": "My PR",
        "user": {"login": "alice", "html_url": "https://github.com/alice"},
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
        "id": 1001,
        "head": {"sha": "abc123", "ref": "feature/x"},
    }


def test_table_output_goes_to_stdout_not_stderr(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "PR-1" in result.stdout
    assert "PR-1" not in result.stderr


def test_progress_messages_go_to_stderr_in_table_mode(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "Processing" in result.stderr
    assert "Processing" not in result.stdout


def test_progress_messages_go_to_stderr_in_json_mode(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--json"])

    assert result.exit_code == 0
    assert "Processing" in result.stderr
    assert json.loads(result.stdout)  # stdout is valid JSON


def test_json_stdout_is_clean_json(monkeypatch):
    """stdout must contain only parseable JSON — no progress noise."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["repo"] == "repo"


def test_no_match_message_goes_to_stderr(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--search", "no-match-xyz"]
    )

    assert result.exit_code == 0
    assert "No PRs matched" in result.stderr
    assert "No PRs matched" not in result.stdout


def test_no_match_with_json_stdout_stays_clean(monkeypatch):
    """--json --search with no matches: stdout must be parseable empty JSON."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--json", "--search", "no-match-xyz"]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_error_messages_go_to_stderr(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", None)

    result = CliRunner().invoke(cli.breakfast, ["-o", "org"])

    assert result.exit_code == 1
    assert "GITHUB_TOKEN" in result.stderr
    assert "GITHUB_TOKEN" not in result.stdout


# ---------------------------------------------------------------------------
# format config key validation
# ---------------------------------------------------------------------------


def test_config_format_json_enables_json_output(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('format = "json"\nowner = "org"\n')
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(cli.breakfast, ["--config", str(cfg_file)])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["repo"] == "repo"


def test_config_format_table_produces_table_output(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('format = "table"\nowner = "org"\n')
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(cli.breakfast, ["--config", str(cfg_file)])

    assert result.exit_code == 0
    assert "PR-1" in result.stdout


def test_config_format_invalid_warns_and_falls_back_to_table(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('format = "tofu"\nowner = "org"\n')
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(cli.breakfast, ["--config", str(cfg_file)])

    assert result.exit_code == 0
    assert "tofu" in result.stderr
    assert "Falling back" in result.stderr
    assert "PR-1" in result.stdout


def test_cli_no_json_flag_overrides_config_format_json(monkeypatch, tmp_path):
    """--no-json on CLI overrides format = "json" in config."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('format = "json"\nowner = "org"\n')
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(cli.breakfast, ["--config", str(cfg_file), "--no-json"])

    assert result.exit_code == 0
    assert "PR-1" in result.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


# ---------------------------------------------------------------------------
# --format markdown
# ---------------------------------------------------------------------------


def test_format_markdown_produces_gfm_table(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--format", "markdown"]
    )

    assert result.exit_code == 0
    assert "| Repo" in result.stdout
    assert "|---" in result.stdout
    assert "[repo](https://github.com/org/repo)" in result.stdout
    assert "[PR-1](https://github.com/org/repo/pull/1)" in result.stdout


def test_format_markdown_strips_ansi_codes(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--format", "markdown"]
    )

    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout
    assert "\x1b]8;;" not in result.stdout


def test_format_markdown_output_goes_to_stdout(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--format", "markdown"]
    )

    assert result.exit_code == 0
    assert "Processing" in result.stderr
    assert "Processing" not in result.stdout
    assert "[repo]" in result.stdout


def test_config_format_markdown_produces_markdown_output(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('format = "markdown"\nowner = "org"\n')
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(cli.breakfast, ["--config", str(cfg_file)])

    assert result.exit_code == 0
    assert "| Repo" in result.stdout
    assert "[PR-1]" in result.stdout


def test_format_markdown_includes_optional_columns(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_api_request(path):
        if "check-runs" in path:
            return {"check_runs": [{"status": "completed", "conclusion": "success"}]}
        return _fake_pr_detail(path)

    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    result = CliRunner().invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--format", "markdown", "--checks", "--age"],
    )

    assert result.exit_code == 0
    assert "| Checks" in result.stdout
    assert "| Age" in result.stdout


def test_format_flag_overrides_json_flag(monkeypatch):
    """--format markdown takes precedence over --json."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--json", "--format", "markdown"],
    )

    assert result.exit_code == 0
    assert "| Repo" in result.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


# ---------------------------------------------------------------------------
# CSV format (#182)
# ---------------------------------------------------------------------------


def test_format_csv_produces_header_row(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--format", "csv"]
    )

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[0].startswith("repo,pr_number,title,author,url")


def test_format_csv_contains_pr_data(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--format", "csv"]
    )

    assert result.exit_code == 0
    assert "repo" in result.stdout
    assert "https://github.com/org/repo/pull/1" in result.stdout


def test_format_csv_strips_ansi_codes(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--format", "csv"]
    )

    assert result.exit_code == 0
    assert "\x1b[" not in result.stdout
    assert "\x1b]8;;" not in result.stdout


def test_format_csv_output_goes_to_stdout(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--format", "csv"]
    )

    assert result.exit_code == 0
    assert "Processing" in result.stderr
    assert "Processing" not in result.stdout
    assert "repo,pr_number" in result.stdout


def test_format_csv_is_valid_csv(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--format", "csv"]
    )

    assert result.exit_code == 0
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    assert len(rows) == 1
    assert rows[0]["repo"] == "repo"
    assert rows[0]["pr_number"] == "1"


def test_format_csv_includes_optional_age_column(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--format", "csv", "--age"]
    )

    assert result.exit_code == 0
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    assert "age_days" in rows[0]


def test_config_format_csv_produces_csv_output(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('format = "csv"\nowner = "org"\n')
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(cli.breakfast, ["--config", str(cfg_file)])

    assert result.exit_code == 0
    assert result.stdout.startswith("repo,pr_number")


def _make_summary_pr(login, repo, comments=0, review_comments=0, draft=False):
    return {
        "user": {"login": login, "html_url": f"https://github.com/{login}"},
        "base": {
            "repo": {
                "name": repo,
                "html_url": f"https://github.com/org/{repo}",
            }
        },
        "html_url": f"https://github.com/org/{repo}/pull/1",
        "draft": draft,
        "comments": comments,
        "review_comments": review_comments,
        "created_at": "2026-05-13T00:00:00Z",
    }


def test_group_prs_by_sums_both_comment_fields():
    pr_details = [
        _make_summary_pr("alice", "api", comments=7, review_comments=3),
        _make_summary_pr("alice", "web", comments=1, review_comments=4),
    ]

    groups = cli._group_prs_by(pr_details, "user")

    assert len(groups) == 1
    name, _url, count, _drafts, _age, total_comments = groups[0]
    assert name == "alice"
    assert count == 2
    assert total_comments == 7 + 3 + 1 + 4


# ---------------------------------------------------------------------------
# --sort / --reverse tests
# ---------------------------------------------------------------------------


def _make_sort_pr(number, repo, author, created_at, updated_at, comments=0):
    return {
        "base": {
            "repo": {"name": repo, "owner": {"login": "org"}},
            "ref": "main",
        },
        "head": {"sha": "abc123"},
        "mergeable": True,
        "mergeable_state": "clean",
        "additions": 1,
        "deletions": 0,
        "title": f"PR {number}",
        "user": {"login": author},
        "state": "open",
        "draft": False,
        "changed_files": 1,
        "commits": 1,
        "comments": comments,
        "review_comments": comments,
        "created_at": created_at,
        "updated_at": updated_at,
        "html_url": f"https://github.com/org/{repo}/pull/{number}",
        "number": number,
        "id": 2000 + number,
        "labels": [],
        "requested_reviewers": [],
    }


def _sort_invoke(monkeypatch, prs, *extra_args):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    pr_by_url = {pr["html_url"]: pr for pr in prs}

    def _fake_api(path):
        # path looks like /repos/org/repo/pulls/N — map back to the PR
        for pr in prs:
            parts = pr["html_url"].split("/")
            owner, repo_name, num = parts[-4], parts[-3], parts[-1]
            if path == f"/repos/{owner}/{repo_name}/pulls/{num}":
                return pr
        raise KeyError(path)

    monkeypatch.setattr(cli, "get_github_prs", lambda *_: list(pr_by_url))
    monkeypatch.setattr(api, "make_github_api_request", _fake_api)
    runner = CliRunner()
    return runner.invoke(cli.breakfast, ["-o", "org", *extra_args])


_TS_A = "2025-01-01T00:00:00Z"
_TS_B = "2025-06-01T00:00:00Z"
_TS_OLD = "2024-01-01T00:00:00Z"


def test_sort_default_by_repo(monkeypatch):
    prs = [
        _make_sort_pr(1, "zebra", "alice", _TS_A, _TS_B),
        _make_sort_pr(2, "alpha", "bob", _TS_A, _TS_A),
    ]
    result = _sort_invoke(monkeypatch, prs)
    assert result.exit_code == 0
    assert result.stdout.index("alpha") < result.stdout.index("zebra")


def test_sort_by_age(monkeypatch):
    prs = [
        _make_sort_pr(1, "repo", "alice", _TS_B, _TS_B),
        _make_sort_pr(2, "repo", "bob", _TS_OLD, _TS_OLD),
    ]
    result = _sort_invoke(monkeypatch, prs, "--sort", "age", "--age")
    assert result.exit_code == 0
    # ascending age: newest PR (smallest age in days) first
    assert result.stdout.index("PR 1") < result.stdout.index("PR 2")


def test_sort_by_age_reverse(monkeypatch):
    prs = [
        _make_sort_pr(1, "repo", "alice", _TS_B, _TS_B),
        _make_sort_pr(2, "repo", "bob", _TS_OLD, _TS_OLD),
    ]
    result = _sort_invoke(monkeypatch, prs, "--sort", "age", "--reverse", "--age")
    assert result.exit_code == 0
    # reversed: oldest PR (most days) first
    assert result.stdout.index("PR 2") < result.stdout.index("PR 1")


def test_sort_by_author(monkeypatch):
    prs = [
        _make_sort_pr(1, "repo", "zara", _TS_A, _TS_A),
        _make_sort_pr(2, "repo", "alice", _TS_A, _TS_A),
    ]
    result = _sort_invoke(monkeypatch, prs, "--sort", "author")
    assert result.exit_code == 0
    assert result.stdout.index("alice") < result.stdout.index("zara")


def test_sort_reverse(monkeypatch):
    prs = [
        _make_sort_pr(1, "alpha", "alice", _TS_A, _TS_A),
        _make_sort_pr(2, "zebra", "bob", _TS_A, _TS_A),
    ]
    result = _sort_invoke(monkeypatch, prs, "--sort", "repo", "--reverse")
    assert result.exit_code == 0
    assert result.stdout.index("zebra") < result.stdout.index("alpha")


def test_sort_by_size(monkeypatch):
    prs = [
        _make_sort_pr(1, "repo", "alice", _TS_A, _TS_A),
        _make_sort_pr(2, "repo", "bob", _TS_A, _TS_A),
    ]
    prs[0]["additions"] = 200
    prs[0]["deletions"] = 50
    prs[1]["additions"] = 10
    prs[1]["deletions"] = 5
    result = _sort_invoke(monkeypatch, prs, "--sort", "size")
    assert result.exit_code == 0
    # ascending: smallest diff (PR 2, total 15) before largest (PR 1, total 250)
    assert result.stdout.index("PR 2") < result.stdout.index("PR 1")


def test_sort_by_size_reverse(monkeypatch):
    prs = [
        _make_sort_pr(1, "repo", "alice", _TS_A, _TS_A),
        _make_sort_pr(2, "repo", "bob", _TS_A, _TS_A),
    ]
    prs[0]["additions"] = 200
    prs[0]["deletions"] = 50
    prs[1]["additions"] = 10
    prs[1]["deletions"] = 5
    result = _sort_invoke(monkeypatch, prs, "--sort", "size", "--reverse")
    assert result.exit_code == 0
    # reversed: largest diff (PR 1) first
    assert result.stdout.index("PR 1") < result.stdout.index("PR 2")


def test_sort_by_size_missing_fields(monkeypatch):
    prs = [
        _make_sort_pr(1, "repo", "alice", _TS_A, _TS_A),
        _make_sort_pr(2, "repo", "bob", _TS_A, _TS_A),
    ]
    del prs[0]["additions"]
    del prs[0]["deletions"]
    result = _sort_invoke(monkeypatch, prs, "--sort", "size")
    assert result.exit_code == 0
    # PR 1 missing fields → treated as 0; PR 2 has additions=1, deletions=0 → 1
    assert result.stdout.index("PR 1") < result.stdout.index("PR 2")


def test_sort_by_files(monkeypatch):
    prs = [
        _make_sort_pr(1, "repo", "alice", _TS_A, _TS_A),
        _make_sort_pr(2, "repo", "bob", _TS_A, _TS_A),
    ]
    prs[0]["changed_files"] = 30
    prs[1]["changed_files"] = 3
    result = _sort_invoke(monkeypatch, prs, "--sort", "files")
    assert result.exit_code == 0
    # ascending: fewest files (PR 2) before most (PR 1)
    assert result.stdout.index("PR 2") < result.stdout.index("PR 1")


# ---------------------------------------------------------------------------
# --format template (#183)
# ---------------------------------------------------------------------------


def test_format_template_basic(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast,
        ["-o", "org", "--format", "template", "--template", "{repo}:{title}"],
    )

    assert result.exit_code == 0
    assert "repo:My PR" in result.stdout


def test_format_template_output_to_stdout(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast,
        ["-o", "org", "--format", "template", "--template", "{url}"],
    )

    assert result.exit_code == 0
    assert "https://github.com/org/repo/pull/1" in result.stdout
    assert "https://github.com/org/repo/pull/1" not in result.stderr


def test_format_template_missing_template_string_exits(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast,
        ["-o", "org", "--format", "template"],
    )

    assert result.exit_code == 1
    assert "--template" in result.stderr


def test_format_template_unknown_field_exits(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast,
        ["-o", "org", "--format", "template", "--template", "{nonexistent_field}"],
    )

    assert result.exit_code == 1
    assert "nonexistent_field" in result.stderr


# ---------------------------------------------------------------------------
# Multiple organizations (#62)
# ---------------------------------------------------------------------------


def test_multiple_orgs_aggregates_prs(monkeypatch):
    """PRs from both orgs are included in the output."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(org, _repo, _state="open"):
        if org == "org-a":
            return ["https://github.com/org-a/repo/pull/1"]
        if org == "org-b":
            return ["https://github.com/org-b/repo/pull/2"]
        return []

    def fake_api(path):
        if "org-a" in path:
            pr = _make_pr_detail(1)
            pr["title"] = "PR from org-a"
            pr["base"]["repo"]["name"] = "repo"
            pr["html_url"] = "https://github.com/org-a/repo/pull/1"
            return pr
        pr = _make_pr_detail(2)
        pr["title"] = "PR from org-b"
        pr["base"]["repo"]["name"] = "repo"
        pr["html_url"] = "https://github.com/org-b/repo/pull/2"
        return pr

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org-a", "-o", "org-b"])

    assert result.exit_code == 0
    assert "PR from org-a" in result.stdout
    assert "PR from org-b" in result.stdout


def test_multiple_orgs_deduplicates_shared_prs(monkeypatch):
    """A URL returned by two orgs appears only once."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    shared_url = "https://github.com/shared-org/repo/pull/1"
    call_count = []

    def fake_get_prs(_org, _repo, _state="open"):
        return [shared_url]

    def fake_api(_path):
        call_count.append(1)
        pr = _make_pr_detail(1)
        pr["title"] = "Shared PR"
        pr["base"]["repo"]["name"] = "repo"
        pr["html_url"] = shared_url
        return pr

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org-a", "-o", "org-b"])

    assert result.exit_code == 0
    assert result.stdout.count("Shared PR") == 1
    assert len(call_count) == 1


def test_missing_organization_exits_with_error(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, [])

    assert result.exit_code == 1
    assert "Owner must be provided" in result.stderr


# ---------------------------------------------------------------------------
# Owner flag / deprecation (#295, #325, #327)
# ---------------------------------------------------------------------------


def test_deprecated_org_flag_warns_and_works(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cli, "get_github_prs", lambda *_: [])

    result = CliRunner().invoke(cli.breakfast, ["--org", "my-org"])

    assert "deprecated" in result.stderr
    assert "--owner" in result.stderr


def test_deprecated_organization_flag_warns_and_works(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cli, "get_github_prs", lambda *_: [])

    result = CliRunner().invoke(cli.breakfast, ["--organization", "my-org"])

    assert "deprecated" in result.stderr
    assert "--owner" in result.stderr


def test_deprecated_organization_config_key_warns(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cli, "get_github_prs", lambda *_: [])

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('organization = "my-org"\n')

    result = CliRunner().invoke(cli.breakfast, ["--config", str(cfg_file)])

    assert "deprecated" in result.stderr
    assert "'organization'" in result.stderr
    assert "'owner'" in result.stderr


def test_owner_not_found_exits_cleanly(monkeypatch, tmp_path):
    from breakfast.api import OwnerNotFoundError

    def _raise(*_):
        raise OwnerNotFoundError("ghost")

    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cli, "get_github_prs", _raise)

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('owner = "ghost"\n')

    result = CliRunner().invoke(cli.breakfast, ["--config", str(cfg_file)])

    assert result.exit_code == 1
    assert "ghost" in result.stderr
    assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# Multiple repo filters (#290)
# ---------------------------------------------------------------------------


def test_multiple_repo_filters_includes_matching_prs(monkeypatch):
    """PRs from repos matching any filter are included (OR logic)."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, repo_filters, _state="open"):
        assert set(repo_filters) == {"api", "platform"}
        return [
            "https://github.com/org/api-gateway/pull/1",
            "https://github.com/org/platform-web/pull/2",
        ]

    def fake_api(path):
        if "api-gateway" in path:
            pr = _make_pr_detail(1)
            pr["title"] = "API PR"
            pr["base"]["repo"]["name"] = "api-gateway"
            pr["html_url"] = "https://github.com/org/api-gateway/pull/1"
            return pr
        pr = _make_pr_detail(2)
        pr["title"] = "Platform PR"
        pr["base"]["repo"]["name"] = "platform-web"
        pr["html_url"] = "https://github.com/org/platform-web/pull/2"
        return pr

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "api", "-r", "platform"])

    assert result.exit_code == 0
    assert "API PR" in result.stdout
    assert "Platform PR" in result.stdout


def test_multiple_repo_filters_config_list(monkeypatch, tmp_path):
    """Config file list for repo-filter is loaded and applied."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    config_file = tmp_path / "breakfast.toml"
    config_file.write_text('owner = "org"\nrepo-filter = ["api", "platform"]\n')

    captured = []

    def fake_get_prs(_org, repo_filters, _state="open"):
        captured.extend(repo_filters)
        return []

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--config", str(config_file)])

    assert result.exit_code == 0
    assert set(captured) == {"api", "platform"}


# ---------------------------------------------------------------------------
# Per-org scoped repo filter — org:filter syntax (#292)
# ---------------------------------------------------------------------------


def test_parse_org_spec_no_colon():
    assert cli._parse_org_spec("my-org") == ("my-org", None)


def test_parse_org_spec_with_filter():
    assert cli._parse_org_spec("my-org:api") == ("my-org", ["api"])


def test_parse_org_spec_empty_filter():
    assert cli._parse_org_spec("my-org:") == ("my-org", [])


def test_parse_org_spec_degenerate_multiple_colons():
    # partition stops at first colon; extra colons go into the filter text
    assert cli._parse_org_spec("my-org:a:b") == ("my-org", ["a:b"])


def test_scoped_filter_overrides_global_repo_filter(monkeypatch):
    """When org has a scoped filter, it wins over the global -r flag."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    captured = {}

    def fake_get_prs(org, repo_filters, _state="open"):
        captured[org] = list(repo_filters)
        return []

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)

    runner = CliRunner()
    runner.invoke(cli.breakfast, ["-o", "my-org:api", "-r", "platform"])

    assert captured["my-org"] == ["api"]


def test_empty_scoped_filter_matches_all_ignoring_global(monkeypatch):
    """org: (empty scoped) passes an empty filter list, matching all repos."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    captured = {}

    def fake_get_prs(org, repo_filters, _state="open"):
        captured[org] = list(repo_filters)
        return []

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)

    runner = CliRunner()
    runner.invoke(cli.breakfast, ["-o", "my-org:", "-r", "platform"])

    assert captured["my-org"] == []


def test_mixed_scoped_and_global_filters(monkeypatch):
    """Scoped org uses its own filter; unscoped org defers to global -r."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    captured = {}

    def fake_get_prs(org, repo_filters, _state="open"):
        captured[org] = list(repo_filters)
        return []

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)

    runner = CliRunner()
    runner.invoke(cli.breakfast, ["-o", "org-a:api", "-o", "org-b", "-r", "platform"])

    assert captured["org-a"] == ["api"]
    assert captured["org-b"] == ["platform"]


def test_scoped_filter_from_config(monkeypatch, tmp_path):
    """Config file org:filter syntax routes per-org filters correctly."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    config_file = tmp_path / "breakfast.toml"
    config_file.write_text(
        'owner = ["my-org:api", "other-org"]\nrepo-filter = "platform"\n'
    )

    captured = {}

    def fake_get_prs(org, repo_filters, _state="open"):
        captured[org] = list(repo_filters)
        return []

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)

    runner = CliRunner()
    runner.invoke(cli.breakfast, ["--config", str(config_file)])

    assert captured["my-org"] == ["api"]
    assert captured["other-org"] == ["platform"]


def test_consolidate_org_specs():
    """Unit test for the consolidate_org_specs helper function."""
    # Case 1: Simple combination
    specs = [("org-a", ["filter-one"]), ("org-a", ["filter-two"])]
    res = cli.consolidate_org_specs(specs, [])
    assert res == [("org-a", ["filter-one", "filter-two"])]

    # Case 2: Case insensitivity and preserving first casing
    specs = [("ORG-A", ["filter-one"]), ("org-a", ["filter-two"])]
    res = cli.consolidate_org_specs(specs, [])
    assert res == [("ORG-A", ["filter-one", "filter-two"])]

    # Case 3: Defer to global filters
    specs = [("org-a", None), ("org-a", None)]
    res = cli.consolidate_org_specs(specs, ["platform"])
    assert res == [("org-a", None)]

    # Case 4: Mixture of scoped and global where one has no scoped filter
    specs = [("org-a", ["filter-one"]), ("org-a", None)]
    res = cli.consolidate_org_specs(specs, ["platform"])
    assert res == [("org-a", ["filter-one", "platform"])]

    # Case 5: Mixture of scoped and global (empty global) resolves to []
    specs = [("org-a", ["filter-one"]), ("org-a", None)]
    res = cli.consolidate_org_specs(specs, [])
    assert res == [("org-a", [])]

    # Case 6: Explicitly empty scoped filter (colon with nothing) resolves to []
    specs = [("org-a", ["filter-one"]), ("org-a", [])]
    res = cli.consolidate_org_specs(specs, ["platform"])
    assert res == [("org-a", [])]

    # Case 7: Order of unique organizations is preserved
    specs = [("org-b", None), ("org-a", ["f1"]), ("org-b", ["f2"])]
    res = cli.consolidate_org_specs(specs, ["platform"])
    assert res == [("org-b", ["platform", "f2"]), ("org-a", ["f1"])]


def test_org_spec_cache_segment_multi_filter():
    """Verify _org_spec_cache_segment behavior with multiple filters."""
    seg_first = cli._org_spec_cache_segment("org", ["filter-b", "filter-a"])
    seg_second = cli._org_spec_cache_segment("org", ["filter-a", "filter-b"])
    seg_one = cli._org_spec_cache_segment("org", ["filter-a"])
    assert seg_first == seg_second  # order-independent
    assert seg_first != seg_one  # different filter sets differ


def test_cli_duplicate_org_fetches_prevented(monkeypatch):
    """CLI groups duplicate org definitions and calls get_github_prs once."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    calls = []

    def fake_get_prs(org, repo_filters, _state="open"):
        filters = list(repo_filters) if repo_filters is not None else None
        calls.append((org, filters))
        return []

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        [
            "-o",
            "org-a:filter-one",
            "-o",
            "ORG-A:filter-two",
            "-o",
            "org-b",
            "-o",
            "org-b:filter-three",
            "-r",
            "global-f",
        ],
    )

    assert result.exit_code == 0
    # org-a was specified twice, first as org-a:filter-one and ORG-A:filter-two.
    # Its casing should be preserved as "org-a",
    # and filters combined as ["filter-one", "filter-two"].
    # org-b was specified as org-b (global-f) and org-b:filter-three.
    # Its casing "org-b" preserved, filters combined as ["global-f", "filter-three"].
    assert len(calls) == 2
    assert calls[0] == ("org-a", ["filter-one", "filter-two"])
    assert calls[1] == ("org-b", ["global-f", "filter-three"])


def test_template_auto_implies_format(monkeypatch):
    """Test that passing --template implies --format template."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast,
        ["-o", "org", "--template", "{repo}:{title}"],
    )

    assert result.exit_code == 0
    assert "repo:My PR" in result.stdout


def test_template_auto_implies_format_overridden_by_explicit_format(monkeypatch):
    """Test that passing --template with explicit format takes precedence."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    result = CliRunner().invoke(
        cli.breakfast,
        ["-o", "org", "--template", "{repo}:{title}", "--format", "json"],
    )

    assert result.exit_code == 0
    # Should output as JSON, not plain template
    assert "repo" in result.stdout
    assert "My PR" in result.stdout
    assert "My PR" in json.loads(result.stdout)[0]["title"]


def test_template_config_implies_format(monkeypatch, tmp_path):
    """Test that a template in config implies --format template

    when no format is configured.
    """
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "tok")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli, "get_github_prs", lambda *_: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", _fake_pr_detail)

    config_content = """
owner = "org"
template = "{repo} -> {title}"
"""
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_content)

    result = CliRunner().invoke(
        cli.breakfast,
        ["--config", str(config_file)],
    )

    assert result.exit_code == 0
    assert "repo -> My PR" in result.stdout


_COLOUR_INDEX_PR = {
    "base": {"repo": {"name": "repo", "owner": {"login": "org"}}},
    "mergeable": True,
    "mergeable_state": "clean",
    "additions": 5,
    "deletions": 2,
    "title": "Test PR",
    "user": {"login": "alice"},
    "number": 1,
    "html_url": "https://github.com/org/repo/pull/1",
    "state": "open",
    "id": 123,
    "review_comments": 0,
    "commits": 1,
    "changed_files": 1,
    "created_at": "2026-06-01T12:00:00Z",
    "updated_at": "2026-06-01T12:00:00Z",
}


def _setup_colour_index_mocks(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _org, _repo_filter, _s="open": ["https://github.com/org/repo/pull/1"],
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _path: _COLOUR_INDEX_PR)
    monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)


def test_index_column_plain_by_default(monkeypatch):
    _setup_colour_index_mocks(monkeypatch)
    result = CliRunner().invoke(cli.breakfast, ["-o", "org", "-r", "repo"])
    assert result.exit_code == 0
    assert re.search(r"\| 0 +\|", result.stdout)


def test_index_column_coloured_when_enabled_by_config(monkeypatch, tmp_path):
    _setup_colour_index_mocks(monkeypatch)
    cfg_file = tmp_path / "test.toml"
    cfg_file.write_text("colour-index = true\n")
    result = CliRunner().invoke(
        cli.breakfast, ["-o", "org", "-r", "repo", "--config", str(cfg_file)]
    )
    assert result.exit_code == 0
    # ANSI escape codes should wrap the index digit
    assert not re.search(r"\| 0 +\|", result.stdout)


# ---------------------------------------------------------------------------
# Column config (Option A inline table format)
# ---------------------------------------------------------------------------

_COLUMN_CONFIG_PR = {
    "base": {
        "repo": {
            "name": "my-repo",
            "html_url": "https://github.com/org/my-repo",
            "owner": {"login": "org"},
        }
    },
    "mergeable": True,
    "mergeable_state": "clean",
    "additions": 5,
    "deletions": 2,
    "title": "Fix the thing",
    "user": {"login": "alice", "html_url": "https://github.com/alice"},
    "state": "open",
    "draft": False,
    "changed_files": 1,
    "commits": 1,
    "review_comments": 0,
    "labels": [],
    "requested_reviewers": [],
    "created_at": "2026-01-10T00:00:00Z",
    "html_url": "https://github.com/org/my-repo/pull/42",
    "number": 42,
    "id": 42,
}


def _setup_column_config_mocks(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _org, _rf, _s="open": ["https://github.com/org/my-repo/pull/42"],
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _p: _COLUMN_CONFIG_PR)


def test_columns_config_reorders_columns(monkeypatch, tmp_path):
    _setup_column_config_mocks(monkeypatch)
    cfg_file = tmp_path / "test.toml"
    cfg_file.write_text(
        'columns = [{name = "title"}, {name = "repo"}, {name = "link"}]\n'
    )
    result = CliRunner().invoke(cli.breakfast, ["-o", "org", "--config", str(cfg_file)])
    assert result.exit_code == 0
    # Title column should appear before Repo
    title_pos = result.stdout.find("PR Title")
    repo_pos = result.stdout.find("Repo")
    assert title_pos < repo_pos
    # Columns not in spec should be absent
    assert "Author" not in result.stdout
    assert "State" not in result.stdout


def test_columns_config_custom_header(monkeypatch, tmp_path):
    _setup_column_config_mocks(monkeypatch)
    cfg_file = tmp_path / "test.toml"
    cfg_file.write_text(
        "columns = ["
        '{name = "repo"}, '
        '{name = "title", header = "Pull Request"}, '
        '{name = "link"}]\n'
    )
    result = CliRunner().invoke(cli.breakfast, ["-o", "org", "--config", str(cfg_file)])
    assert result.exit_code == 0
    assert "Pull Request" in result.stdout
    assert "PR Title" not in result.stdout


def test_columns_config_autoenables_age(monkeypatch, tmp_path):
    _setup_column_config_mocks(monkeypatch)
    cfg_file = tmp_path / "test.toml"
    cfg_file.write_text(
        "columns = ["
        '{name = "repo"}, '
        '{name = "title"}, '
        '{name = "age"}, '
        '{name = "link"}]\n'
    )
    result = CliRunner().invoke(cli.breakfast, ["-o", "org", "--config", str(cfg_file)])
    assert result.exit_code == 0
    assert "Age" in result.stdout


def test_columns_config_plain_string_list(monkeypatch, tmp_path):
    _setup_column_config_mocks(monkeypatch)
    cfg_file = tmp_path / "test.toml"
    cfg_file.write_text('columns = ["repo", "title", "link"]\n')
    result = CliRunner().invoke(cli.breakfast, ["-o", "org", "--config", str(cfg_file)])
    assert result.exit_code == 0
    assert "Repo" in result.stdout
    assert "PR Title" in result.stdout
    assert "Link" in result.stdout
    assert "Author" not in result.stdout


def test_cli_offline_flag_loads_from_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    # Pre-populate expired cache
    pr_details = [_make_pr_detail(1)]
    cache.write_pr_cache("org", "repo", pr_details)

    # Manually backdate cache fetched_at to 3 hours ago
    path = cache.cache_path("org", "repo")
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))

    api_called = []
    monkeypatch.setattr(cli, "get_github_prs", lambda *a: api_called.append(1) or [])

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--offline"])

    assert result.exit_code == 0
    assert len(api_called) == 0, "No network calls should be made in offline mode"
    assert "PR number 1" in result.stdout
    assert "🔌 Offline Mode: Displaying cached data from 3 hours ago." in result.stderr


def test_cli_offline_flag_no_cache_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--offline"])

    assert result.exit_code == 1
    assert "Error: Offline mode enabled, but no cached data was found." in result.stderr


def test_cli_network_failure_falls_back_to_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    # Pre-populate expired cache
    pr_details = [_make_pr_detail(1)]
    cache.write_pr_cache("org", "repo", pr_details)

    # Manually backdate cache fetched_at to 2 hours ago
    path = cache.cache_path("org", "repo")
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))

    # Mock get_github_prs to simulate network connection error
    def mock_get_prs(*args, **kwargs):
        raise requests.exceptions.ConnectionError("Could not resolve host")

    monkeypatch.setattr(cli, "get_github_prs", mock_get_prs)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "PR number 1" in result.stdout
    assert "🔌 Offline Mode: Displaying cached data from 2 hours ago." in result.stderr


def test_cli_offline_mode_does_not_write_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    # Pre-populate cache
    pr_details = [_make_pr_detail(1)]
    cache.write_pr_cache("org", "repo", pr_details)
    path = cache.cache_path("org", "repo")

    # Change file contents and get timestamp
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))

    # Track writes
    write_called = []
    original_write = cache.write_pr_cache

    def tracked_write(*args, **kwargs):
        write_called.append(1)
        return original_write(*args, **kwargs)

    monkeypatch.setattr(cache, "write_pr_cache", tracked_write)
    monkeypatch.setattr(cli, "write_pr_cache", tracked_write)

    # Run CLI in offline mode
    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--offline"])

    assert result.exit_code == 0
    assert len(write_called) == 0, "Should not write to cache in offline mode"

    # Confirm cache file hasn't been updated/overwritten
    data_after = json.loads(path.read_text())
    assert data_after["fetched_at"] == old_time


def test_cli_offline_mode_mine_only_no_cached_login_warns(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)
    monkeypatch.setattr(cli, "read_cached_user_login", cache.read_cached_user_login)

    # Pre-populate expired cache (no user.json — simulates first-time offline run)
    pr_details = [_make_pr_detail(1)]
    cache.write_pr_cache("org", "repo", pr_details)
    path = cache.cache_path("org", "repo")
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--offline", "--mine-only"],
    )

    assert result.exit_code == 0
    assert "PR number 1" in result.stdout
    assert "no cached login found" in result.stderr
    assert "--mine-only / --needs-my-review skipped" in result.stderr


def test_cli_mine_only_online_persists_login(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "write_cached_user_login", cache.write_cached_user_login)
    monkeypatch.setattr(cli, "get_authenticated_user_login", lambda: "alice")

    def fake_get_prs(_org, _repo_filter, _state="open"):
        return ["https://github.com/org/repo/pull/1"]

    def fake_api_request(path):
        return {
            "base": {"repo": {"name": "repo", "owner": {"login": "org"}}},
            "head": {"sha": "abc123"},
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 1,
            "deletions": 0,
            "title": "Alice PR",
            "user": {"login": "alice"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "created_at": "2026-01-10T00:00:00Z",
            "html_url": "https://github.com/org/repo/pull/1",
            "number": 1,
            "id": 1001,
            "labels": [],
            "requested_reviewers": [],
            "draft": False,
        }

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--mine-only"])

    assert result.exit_code == 0
    assert cache.read_cached_user_login() == "alice"


def test_cli_offline_mine_only_with_cached_login_filters(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)
    monkeypatch.setattr(cli, "read_cached_user_login", cache.read_cached_user_login)

    cache.write_cached_user_login("alice")

    alice_pr = _make_pr_detail(1)  # default author is alice
    bob_pr = {**_make_pr_detail(2), "user": {"login": "bob"}}
    cache.write_pr_cache("org", "repo", [alice_pr, bob_pr])

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--offline", "--mine-only"],
    )

    assert result.exit_code == 0
    assert "PR number 1" in result.stdout
    assert "PR number 2" not in result.stdout
    assert "no cached login found" not in result.stderr


def test_cli_offline_respects_no_age_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    pr_details = [_make_pr_detail(1)]
    cache.write_pr_cache("org", "repo", pr_details)

    path = cache.cache_path("org", "repo")
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--offline"],
    )

    assert result.exit_code == 0
    assert "PR number 1" in result.stdout
    assert "Age" not in result.stdout


def test_cli_offline_respects_age_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    pr_details = [_make_pr_detail(1)]
    cache.write_pr_cache("org", "repo", pr_details)

    path = cache.cache_path("org", "repo")
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--offline", "--age"],
    )

    assert result.exit_code == 0
    assert "PR number 1" in result.stdout
    assert "Age" in result.stdout


# ---------------------------------------------------------------------------
# Shell completion (#350)
# ---------------------------------------------------------------------------


def test_completion_zsh_exits_zero_and_outputs_script():
    """--completion zsh prints a zsh script and exits 0 without needing a token."""
    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--completion", "zsh"])
    assert result.exit_code == 0
    assert "_BREAKFAST_COMPLETE" in result.output
    assert "breakfast" in result.output


def test_completion_bash_exits_zero_and_outputs_script():
    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--completion", "bash"])
    assert result.exit_code == 0
    assert "_BREAKFAST_COMPLETE" in result.output
    assert "breakfast" in result.output


def test_completion_fish_exits_zero_and_outputs_script():
    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--completion", "fish"])
    assert result.exit_code == 0
    assert "_BREAKFAST_COMPLETE" in result.output
    assert "breakfast" in result.output


def test_completion_requires_no_github_token(monkeypatch):
    """--completion must work even with no GITHUB_TOKEN set."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "")
    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--completion", "zsh"])
    assert result.exit_code == 0


def test_completion_rejects_unknown_shell():
    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--completion", "powershell"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# --filter-mergeable (#343)
# ---------------------------------------------------------------------------


def test_cli_filter_mergeable_conflict(monkeypatch):
    """--filter-mergeable conflict shows only PRs with mergeable=False."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)

    def fake_get_prs(_org, _repo_filter, _state="open"):
        return [
            "https://github.com/org/repo/pull/1",
            "https://github.com/org/repo/pull/2",
        ]

    def fake_api_request(path):
        number = 1 if path.endswith("/1") else 2
        return {
            "base": {"repo": {"name": "repo", "owner": {"login": "org"}}},
            "mergeable": False if number == 1 else True,
            "mergeable_state": "dirty" if number == 1 else "clean",
            "additions": 1,
            "deletions": 0,
            "title": f"PR {number} {'conflict' if number == 1 else 'clean'}",
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
    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "repo", "--filter-mergeable", "conflict"],
    )

    assert result.exit_code == 0
    assert "PR 1 conflict" in result.stdout
    assert "PR 2 clean" not in result.stdout
