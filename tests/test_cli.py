import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import requests
from click.testing import CliRunner
from tabulate import tabulate

from breakfast import api, cache, cli


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
    assert "not valid regex" in result.output


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
    assert "✅ (clean)" in result.output


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
    assert "✅ pass" in result.output


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


def test_cli_show_config_includes_status_style_from_config(tmp_path):
    cfg_path = tmp_path / "breakfast.toml"
    cfg_path.write_text(
        'organization = "org"\n'
        'repo-filter = "repo"\n'
        "checks = true\n"
        'status-style = "ascii"\n'
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--config", str(cfg_path), "--show-config"])

    assert result.exit_code == 0
    assert "status-style: ascii" in result.output


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
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    pr_detail = _make_pr_detail()

    def fake_get_prs(_org, _repo_filter):
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
    assert "Approved" in result.output
    assert "✅ approved" in result.output


def test_cli_renders_review_required_for_incomplete_reviews(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    pr_detail = _make_pr_detail()

    monkeypatch.setattr(
        cli,
        "get_github_prs",
        lambda _org, _repo_filter: ["https://github.com/org/repo/pull/1"],
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
    assert "⏳ pending" in result.output


def test_cli_renders_approval_counts_for_multi_review_branch(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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
        lambda _org, _repo_filter: ["https://github.com/org/repo/pull/1"],
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
    assert "✅ 1/2 approvals" in result.output


def test_cli_approvals_not_shown_by_default(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    pr_detail = _make_pr_detail()

    monkeypatch.setattr(
        cli, "get_github_prs", lambda _o, _r: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _path: pr_detail)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "Approved" not in result.output


def test_cli_json_includes_approval_when_enabled(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    pr_detail = _make_pr_detail()

    def fake_api_request(path):
        if "/reviews" in path:
            return [{"user": {"login": "bob"}, "state": "CHANGES_REQUESTED"}]
        return pr_detail

    monkeypatch.setattr(
        cli, "get_github_prs", lambda _o, _r: ["https://github.com/org/repo/pull/1"]
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
    data = json.loads(result.output[result.output.index("[") :])
    assert data[0]["approval"] == "changes"


def test_cli_json_includes_approval_counts_when_available(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    pr_detail = _make_pr_detail()

    def fake_api_request(path):
        if "/reviews" in path:
            return [{"user": {"login": "bob"}, "state": "APPROVED"}]
        if path.endswith("/branches/main/protection/required_pull_request_reviews"):
            return {"required_approving_review_count": 2}
        return pr_detail

    monkeypatch.setattr(
        cli, "get_github_prs", lambda _o, _r: ["https://github.com/org/repo/pull/1"]
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
    data = json.loads(result.output[result.output.index("[") :])
    assert data[0]["approval"] == "pending"
    assert data[0]["approval_current"] == 1
    assert data[0]["approval_required"] == 2


def test_cli_json_excludes_approval_by_default(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    pr_detail = _make_pr_detail()

    monkeypatch.setattr(
        cli, "get_github_prs", lambda _o, _r: ["https://github.com/org/repo/pull/1"]
    )
    monkeypatch.setattr(api, "make_github_api_request", lambda _path: pr_detail)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output[result.output.index("[") :])
    assert "approval" not in data[0]


def test_cli_approvals_config_file(tmp_path):
    cfg_path = tmp_path / "breakfast.toml"
    cfg_path.write_text(
        'organization = "org"\nrepo-filter = "repo"\napprovals = true\n'
    )

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--config", str(cfg_path), "--show-config"])

    assert result.exit_code == 0
    assert "approvals: True" in result.output


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


def test_auto_fit_measures_later_rows_when_fitting_table():
    rows = [
        {
            "Repo": "short",
            "PR Title": "short",
            "Author": "alice",
            "State": "open",
            "Files": "1",
            "Commits": "1",
            "+/-": "+1/-0",
            "Comments": "0",
            "Mergeable?": "yes (clean)",
            "Link": "PR-1",
        },
        {
            "Repo": "a-very-long-repository-name-that-should-be-truncated",
            "PR Title": "short",
            "Author": "alice",
            "State": "open",
            "Files": "1",
            "Commits": "1",
            "+/-": "+1/-0",
            "Comments": "0",
            "Mergeable?": "yes (clean)",
            "Link": "PR-2",
        },
    ]

    terminal_width = cli._table_width(rows[:1])
    fitted_rows = cli._auto_fit(rows, terminal_width, explicit_max_title_length=None)
    rendered_width = len(
        tabulate(
            fitted_rows, headers="keys", showindex="always", tablefmt="outline"
        ).splitlines()[0]
    )

    assert rendered_width <= terminal_width
    assert fitted_rows[1]["Repo"].endswith("…")


def test_cli_status_columns_use_ascii_to_keep_rows_aligned(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

    def fake_get_prs(_org, _repo_filter):
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
    assert "yes (clean)" in result.output
    assert "no (dirty)" in result.output
    assert "pending" in result.output
    assert "✅" not in result.output
    assert "❌" not in result.output
    assert "⚠️" not in result.output
    assert "➖" not in result.output

    table_lines = [
        cli._strip_ansi(line)
        for line in result.output.splitlines()
        if line.startswith(("+", "|"))
    ]
    widths = {len(line) for line in table_lines}

    assert len(widths) == 1


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


def test_auto_fit_renames_mergeable_to_mrg(monkeypatch):
    rows = [{"Mergeable?": "✅", "PR Title": "x", "Repo": "r", "Author": "a"}]
    # Set terminal width just narrow enough to trigger step 4b but not step 5+
    width = cli._table_width(rows) - 1
    result = cli._auto_fit(rows, width, explicit_max_title_length=None)
    keys = list(result[0].keys())
    assert "Mrg" in keys
    assert "Mergeable?" not in keys


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


# ---------------------------------------------------------------------------
# Cache integration tests
# ---------------------------------------------------------------------------


def _make_pr_detail(number=1):
    return {
        "base": {
            "repo": {"name": "repo", "owner": {"login": "org"}},
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
        "html_url": f"https://github.com/org/repo/pull/{number}",
        "number": number,
        "id": 1000 + number,
    }


def test_cache_hit_skips_get_github_prs(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
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
    assert "PR number 1" in result.output


def test_no_cache_flag_always_fetches(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli, "read_pr_cache", cache.read_pr_cache)
    monkeypatch.setattr(cli, "write_pr_cache", cache.write_pr_cache)

    # Pre-populate cache
    cache.write_pr_cache("org", "repo", [_make_pr_detail(99)])

    api_called = []

    def fake_get_prs(_org, _repo):
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
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
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
    assert "invalid" in result.output.lower() or "cache-ttl" in result.output.lower()


def test_config_cache_ttl_respected(monkeypatch, tmp_path):
    """cache-ttl = "5m" in config is honoured when no CLI flag given."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
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
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
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
    assert "PR number 1" in result.output


def test_pr_results_grouped_by_repo(monkeypatch, tmp_path):
    """PRs from multiple repos should appear grouped by repo name in the output."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
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
    alpha_pos = result.output.index("alpha-service")
    zebra_pos = result.output.index("zebra-service")
    assert alpha_pos < zebra_pos, "repos should appear in alphabetical order"


def test_refresh_without_cache_exits_with_error(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--refresh"])

    assert result.exit_code == 1
    assert "requires the cache to be enabled" in result.output
    assert "--cache" in result.output


def test_refresh_prs_without_cache_exits_with_error(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "repo", "--refresh-prs"])

    assert result.exit_code == 1
    assert "requires the cache to be enabled" in result.output
    assert "--cache" in result.output


def test_refresh_ignores_cache_and_writes_fresh(monkeypatch, tmp_path):
    """--refresh bypasses the cache read but still writes fresh data back."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
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
    assert "PR number 1" in result.output
    # Cache should now contain fresh data
    cached = cache.read_pr_cache("org", "repo", 300)
    assert cached is not None
    assert cached["prs"][0]["number"] == 1


def test_refresh_does_not_use_cached_data(monkeypatch, tmp_path):
    """--refresh must not serve stale data even when cache is warm."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
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
    assert "PR number 99" not in result.output, "stale cached PR should not appear"
    assert "PR number 1" in result.output


def test_refresh_prs_uses_graphql_cache_skips_pr_cache(monkeypatch, tmp_path):
    """--refresh-prs uses the cached URL list but re-fetches PR details."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
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
    assert "PR number 99" not in result.output, "stale PR cache should be bypassed"
    assert "PR number 1" in result.output


def test_refresh_prs_writes_fresh_pr_cache(monkeypatch, tmp_path):
    """--refresh-prs writes fresh PR details back to cache."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)
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
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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
    assert "⚔️" in result.output, "legendary PR should have sword emoji in State"


def test_cli_legendary_off_by_default(monkeypatch):
    """Without --legendary, no sword emoji appears even for qualifying PRs."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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
    assert "⚔️" not in result.output


def test_cli_legendary_only_filters_non_legendary(monkeypatch):
    """--legendary-only shows only PRs that qualify as legendary."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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
    assert "Fresh PR" not in result.output


def test_cli_legendary_only_implies_legendary_marking(monkeypatch):
    """--legendary-only implies --legendary so the ⚔️ marker is applied."""
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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
    assert "⚔️" in result.output


# ---------------------------------------------------------------------------
# Colour grading / ANSI preservation tests (from #122)
# ---------------------------------------------------------------------------


def test_compress_styled_preserves_ansi_colour():
    import click

    styled = click.style("✅ pass", fg="green", bold=True)
    compressed = cli._compress_styled(styled)
    # Should keep the emoji but drop " pass"
    assert "✅" in cli._strip_ansi(compressed)
    assert "pass" not in cli._strip_ansi(compressed)
    # ANSI colour codes should be preserved
    assert "\x1b[" in compressed


def test_compress_styled_noop_for_single_word():
    import click

    styled = click.style("✅", fg="green", bold=True)
    assert cli._compress_styled(styled) == styled


def test_compress_styled_plain_text():
    assert cli._compress_styled("hello world") == "hello"
    assert cli._compress_styled("single") == "single"


def test_compress_styled_preserves_approval_fraction():
    styled = cli.format_approval_status(
        "pending",
        current_reviews=1,
        required_reviews=2,
    )

    compressed = cli._compress_styled(styled)

    assert cli._strip_ansi(compressed) == "✅ 1/2"


def test_auto_fit_preserves_checks_colour(monkeypatch):
    import click

    styled_checks = click.style("✅ pass", fg="green", bold=True)
    rows = [
        {
            "Repo": "myrepo",
            "PR Title": "Some title",
            "Author": "alice",
            "State": "open",
            "Files": "1",
            "Commits": "1",
            "+/-": "+1/-0",
            "Comments": "0",
            "Checks": styled_checks,
            "Mergeable?": click.style("✅ (clean)", fg="green", bold=True),
            "Link": "PR-1",
        }
    ]
    # Very narrow width to force all compression steps
    result = cli._auto_fit(rows, 80, explicit_max_title_length=None)
    checks_key = "Checks" if "Checks" in result[0] else None
    if checks_key:
        # Colour should be preserved even after compression
        assert "\x1b[" in result[0][checks_key]


def test_no_drafts_and_drafts_only_are_mutually_exclusive(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["-o", "org", "--no-drafts", "--drafts-only"])

    assert result.exit_code == 1
    assert "mutually exclusive" in result.output.lower()


def test_styled_hyperlink_puts_colour_outside_osc8():
    import click

    styled = click.style("pending", fg="yellow", bold=True)
    result = cli._styled_hyperlink("https://example.com/checks", styled)
    # Find the link text between the OSC 8 open and close tags
    osc_open_end = result.index("\x1b\\") + 2
    osc_close_start = result.index("\x1b]8;;\x1b\\", osc_open_end)
    link_text = result[osc_open_end:osc_close_start]
    assert link_text == "pending"  # plain text inside the OSC 8, no escape sequences
    assert "\x1b[" in result  # colour codes still present outside the OSC 8


def test_cli_repo_and_author_are_hyperlinks(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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
    assert "\x1b]8;;https://github.com/myorg/myrepo\x1b\\" in result.output
    assert "\x1b]8;;https://github.com/alice\x1b\\" in result.output


def test_cli_checks_column_links_to_checks_tab(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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
    assert "\x1b]8;;https://github.com/org/repo/pull/7/checks\x1b\\" in result.output


def test_progress_emoji_emitted_after_check_status_fetch(monkeypatch):
    """Emoji must appear only after the full bundle (detail + checks) is fetched.

    Regression for #142: the old code emitted the emoji as soon as PR detail
    completed, before check/approval statuses were fetched, causing a silent
    delay after the progress line showed ...Done.
    """
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])
    monkeypatch.setattr(cli, "check_for_update", lambda: None)

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
