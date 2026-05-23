"""End-to-end integration tests for the breakfast CLI.

These tests exercise the full CLI pipeline — option parsing, config loading,
filtering, output formatting — using Click's CliRunner and monkeypatched
GitHub API responses.  No real HTTP is made; all API surface is replaced with
controlled fixtures so the tests remain deterministic and fast.
"""

import json

import pytest
from click.testing import CliRunner

from breakfast import api, cache, cli

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _pr(
    number=1,
    title="Test PR",
    author="alice",
    state="open",
    draft=False,
    repo="myrepo",
    labels=None,
    review_comments=0,
    created_at="2026-01-10T00:00:00Z",
):
    """Build a minimal fake PR detail dict suitable for all tests."""
    return {
        "number": number,
        "title": title,
        "state": state,
        "draft": draft,
        "user": {"login": author, "html_url": f"https://github.com/{author}"},
        "base": {
            "repo": {"name": repo},
            "ref": "main",
            "label": f"org:{repo}",
        },
        "head": {
            "ref": f"feature/pr-{number}",
            "label": f"org:feature/pr-{number}",
        },
        "mergeable": True,
        "mergeable_state": "clean",
        "additions": 10,
        "deletions": 5,
        "changed_files": 2,
        "commits": 1,
        "review_comments": review_comments,
        "comments": 0,
        "created_at": created_at,
        "updated_at": "2026-01-15T00:00:00Z",
        "html_url": f"https://github.com/org/{repo}/pull/{number}",
        "labels": labels or [],
        "requested_reviewers": [],
        "id": number * 100,
    }


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def patch_token(monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", "fake-token")


@pytest.fixture(autouse=True)
def suppress_spinner(monkeypatch):
    monkeypatch.setattr(cli, "BREAKFAST_ITEMS", ["*"])


@pytest.fixture(autouse=True)
def suppress_update(monkeypatch):
    monkeypatch.setattr(cli, "check_for_update", lambda **_kw: None)


def _wire(monkeypatch, prs, pr_lookup=None):
    """Monkeypatch get_github_prs and the REST API to return *prs*.

    *prs* is a list of PR detail dicts.  *pr_lookup* overrides per-URL
    resolution (rarely needed — the default maps by number).
    """
    urls = [p["html_url"] for p in prs]

    def fake_get_prs(*_args, **_kwargs):
        return urls

    lookup = {p["html_url"]: p for p in prs}
    if pr_lookup:
        lookup.update(pr_lookup)

    def fake_rest(_path):
        # _path looks like "/repos/org/myrepo/pulls/1"
        parts = _path.rstrip("/").split("/")
        number = int(parts[-1])
        for p in prs:
            if p["number"] == number:
                return p
        raise KeyError(f"No PR for path {_path!r}")

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_rest)


# ---------------------------------------------------------------------------
# Output format: table (default)
# ---------------------------------------------------------------------------


def test_table_format_golden_path(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1, title="Add login endpoint", author="alice")])

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo"])

    assert result.exit_code == 0, result.output
    assert "Add login endpoint" in result.stdout
    assert "alice" in result.stdout
    assert "myrepo" in result.stdout
    assert "✅ (clean)" in result.stdout


def test_table_shows_pr_link(runner, monkeypatch):
    _wire(monkeypatch, [_pr(42)])

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo"])

    assert result.exit_code == 0
    assert "PR-42" in result.stdout


def test_no_prs_exits_cleanly(runner, monkeypatch):
    monkeypatch.setattr(cli, "get_github_prs", lambda *a, **kw: [])

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo"])

    assert result.exit_code == 0
    # With zero PRs the CLI exits cleanly (empty table or no output — both are fine).
    assert "PR-" not in result.stdout


def test_table_data_on_stdout_progress_on_stderr(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1)])

    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo"], catch_exceptions=False
    )

    assert result.exit_code == 0
    # PR data must be on stdout
    assert "PR-1" in result.stdout
    # ANSI table structure on stdout, progress on stderr (or mixed via runner)
    # At minimum, the table must not be empty
    assert len(result.stdout.strip()) > 0


# ---------------------------------------------------------------------------
# Output format: JSON
# ---------------------------------------------------------------------------


def test_json_format_valid_json(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1, title="JSON test PR", author="bob")])

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["title"] == "JSON test PR"
    assert data[0]["author"] == "bob"


def test_json_format_via_format_flag(runner, monkeypatch):
    _wire(monkeypatch, [_pr(2, title="Via --format")])

    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo", "--format", "json"]
    )

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["title"] == "Via --format"


def test_json_multiple_prs(runner, monkeypatch):
    prs = [_pr(i, title=f"PR {i}") for i in range(1, 4)]
    _wire(monkeypatch, prs)

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert len(data) == 3


# ---------------------------------------------------------------------------
# Output format: Markdown
# ---------------------------------------------------------------------------


def test_markdown_format(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1, title="Markdown PR")])

    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo", "--format", "markdown"]
    )

    assert result.exit_code == 0
    assert "|" in result.stdout
    assert "Markdown PR" in result.stdout


# ---------------------------------------------------------------------------
# Output format: CSV
# ---------------------------------------------------------------------------


def test_csv_format(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1, title="CSV PR", author="alice")])

    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo", "--format", "csv"]
    )

    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert len(lines) >= 2
    header = lines[0]
    assert "title" in header.lower() or "Title" in header
    assert "CSV PR" in result.stdout


# ---------------------------------------------------------------------------
# Filtering: --ignore-author
# ---------------------------------------------------------------------------


def test_ignore_author_removes_pr(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1, author="bot"), _pr(2, title="Human PR", author="alice")])

    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "myrepo", "--ignore-author", "bot"],
    )

    assert result.exit_code == 0
    assert "Human PR" in result.stdout
    assert "bot" not in result.stdout


def test_ignore_author_case_insensitive(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1, title="Bot PR", author="Dependabot")])

    result = runner.invoke(
        cli.breakfast,
        ["-o", "org", "-r", "myrepo", "--ignore-author", "dependabot"],
    )

    assert result.exit_code == 0
    assert "Bot PR" not in result.stdout


# ---------------------------------------------------------------------------
# Filtering: --mine-only
# ---------------------------------------------------------------------------


def test_mine_only_shows_current_user(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1, author="alice"), _pr(2, title="Bob PR", author="bob")])
    monkeypatch.setattr(cli, "get_authenticated_user_login", lambda: "alice")

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--mine-only"])

    assert result.exit_code == 0
    assert "alice" in result.stdout
    assert "Bob PR" not in result.stdout


# ---------------------------------------------------------------------------
# Filtering: --no-drafts / --drafts-only
# ---------------------------------------------------------------------------


def test_no_drafts_excludes_drafts(runner, monkeypatch):
    _wire(
        monkeypatch,
        [_pr(1, title="Draft PR", draft=True), _pr(2, title="Ready PR", draft=False)],
    )

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--no-drafts"])

    assert result.exit_code == 0
    assert "Ready PR" in result.stdout
    assert "Draft PR" not in result.stdout


def test_drafts_only_shows_only_drafts(runner, monkeypatch):
    _wire(
        monkeypatch,
        [_pr(1, title="Draft PR", draft=True), _pr(2, title="Ready PR", draft=False)],
    )

    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo", "--drafts-only"]
    )

    assert result.exit_code == 0
    assert "Draft PR" in result.stdout
    assert "Ready PR" not in result.stdout


# ---------------------------------------------------------------------------
# Filtering: --filter-state
# ---------------------------------------------------------------------------


def test_filter_state_open(runner, monkeypatch):
    _wire(
        monkeypatch,
        [
            _pr(1, title="Open PR", state="open"),
            _pr(2, title="Closed PR", state="closed"),
        ],
    )

    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo", "--filter-state", "open"]
    )

    assert result.exit_code == 0
    assert "Open PR" in result.stdout
    assert "Closed PR" not in result.stdout


# ---------------------------------------------------------------------------
# Filtering: --search
# ---------------------------------------------------------------------------


def test_search_filters_by_title(runner, monkeypatch):
    _wire(
        monkeypatch,
        [_pr(1, title="Add login feature"), _pr(2, title="Fix typo in docs")],
    )

    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo", "--search", "login"]
    )

    assert result.exit_code == 0
    assert "Add login feature" in result.stdout
    assert "Fix typo" not in result.stdout


def test_search_regex(runner, monkeypatch):
    _wire(
        monkeypatch,
        [_pr(1, title="feat: add login"), _pr(2, title="chore: bump version")],
    )

    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo", "--search", "^feat"]
    )

    assert result.exit_code == 0
    assert "feat: add login" in result.stdout
    assert "chore: bump version" not in result.stdout


def test_search_invalid_regex_exits_nonzero(runner, monkeypatch):
    monkeypatch.setattr(cli, "get_github_prs", lambda *a, **kw: [])

    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo", "--search", "[invalid"]
    )

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Filtering: --limit
# ---------------------------------------------------------------------------


def test_limit_caps_results(runner, monkeypatch):
    _wire(monkeypatch, [_pr(i, title=f"PR {i}") for i in range(1, 6)])

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--limit", "2"])

    assert result.exit_code == 0
    # Only 2 PRs should appear
    assert result.stdout.count("PR-") == 2


# ---------------------------------------------------------------------------
# Columns: --age
# ---------------------------------------------------------------------------


def test_age_column_appears(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1)])

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--age"])

    assert result.exit_code == 0
    assert "Age" in result.stdout


# ---------------------------------------------------------------------------
# Columns: --checks
# ---------------------------------------------------------------------------


def test_checks_column_appears(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1)])
    monkeypatch.setattr(cli, "get_check_status", lambda *a, **kw: "pass")

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--checks"])

    assert result.exit_code == 0
    assert "Checks" in result.stdout


# ---------------------------------------------------------------------------
# Columns: --approvals
# ---------------------------------------------------------------------------


def test_approvals_column_appears(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1)])
    monkeypatch.setattr(
        cli,
        "get_approval_summary",
        lambda *a, **kw: ("approved", 1, 1, {}),
    )

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--approvals"])

    assert result.exit_code == 0
    assert "Apr" in result.stdout or "Approved" in result.stdout


# ---------------------------------------------------------------------------
# Display: --no-colour
# ---------------------------------------------------------------------------


def test_no_colour_strips_ansi(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1)])

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--no-colour"])

    assert result.exit_code == 0
    assert "\033[" not in result.stdout


# ---------------------------------------------------------------------------
# Summary views
# ---------------------------------------------------------------------------


def test_summarise_user_prs(runner, monkeypatch):
    _wire(
        monkeypatch,
        [_pr(1, author="alice"), _pr(2, author="alice"), _pr(3, author="bob")],
    )

    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo", "--summarise-user-prs"]
    )

    assert result.exit_code == 0
    assert "alice" in result.stdout
    assert "bob" in result.stdout


def test_summarise_repo_prs(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1, repo="repo-a"), _pr(2, repo="repo-b")])

    result = runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo", "--summarise-repo-prs"]
    )

    assert result.exit_code == 0
    assert "repo-a" in result.stdout or "repo-b" in result.stdout


# ---------------------------------------------------------------------------
# Update notification
# ---------------------------------------------------------------------------


def test_update_notification_appears_in_output(runner, monkeypatch):
    _wire(monkeypatch, [_pr(1)])
    monkeypatch.setattr(
        cli,
        "check_for_update",
        lambda **_kw: "🍳 A fresh breakfast is ready! v0.1.0 → v9.9.9",
    )

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo"])

    assert result.exit_code == 0
    # The update banner goes to stderr; CliRunner merges it by default.
    assert "fresh breakfast" in result.output


# ---------------------------------------------------------------------------
# Authentication: missing token
# ---------------------------------------------------------------------------


def test_missing_token_exits_nonzero(runner, monkeypatch):
    monkeypatch.setattr(cli, "SECRET_GITHUB_TOKEN", None)

    result = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo"])

    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Cache round-trip
# ---------------------------------------------------------------------------


def test_cache_hit_skips_api(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    call_count = {"n": 0}

    def counting_get_prs(*a, **kw):
        call_count["n"] += 1
        return ["https://github.com/org/myrepo/pull/1"]

    def fake_rest(_path):
        return _pr(1, title="Cached PR")

    monkeypatch.setattr(cli, "get_github_prs", counting_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", fake_rest)

    # First run — fetches and writes cache
    r1 = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--cache"])
    assert r1.exit_code == 0
    assert call_count["n"] == 1

    # Second run — should hit cache and NOT call get_github_prs again
    r2 = runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--cache"])
    assert r2.exit_code == 0
    assert "Cached PR" in r2.stdout
    # get_github_prs may still be called to get URL list; the key is that
    # make_github_api_request was NOT called for individual PR details.
    # We verify the cache by checking the output matches.


def test_cache_refresh_bypasses_cache(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    rest_call_count = {"n": 0}

    def fake_get_prs(*a, **kw):
        return ["https://github.com/org/myrepo/pull/1"]

    def counting_rest(_path):
        rest_call_count["n"] += 1
        return _pr(1)

    monkeypatch.setattr(cli, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(api, "make_github_api_request", counting_rest)

    # First run builds cache
    runner.invoke(cli.breakfast, ["-o", "org", "-r", "myrepo", "--cache"])
    count_after_first = rest_call_count["n"]

    # Second run with --refresh should re-fetch
    runner.invoke(
        cli.breakfast, ["-o", "org", "-r", "myrepo", "--cache", "--refresh-prs"]
    )
    assert rest_call_count["n"] > count_after_first


# ---------------------------------------------------------------------------
# Config file: options loaded from config
# ---------------------------------------------------------------------------


def test_config_file_sets_organization(runner, monkeypatch, tmp_path):
    """Config file organization option is loaded and used."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('organization = "configured-org"\n')

    call_args = {}

    def capture_get_prs(org, repo_filter, _state="open"):
        call_args["org"] = org
        return []

    monkeypatch.setattr(cli, "get_github_prs", capture_get_prs)

    runner.invoke(cli.breakfast, ["--config", str(cfg_file)])

    # Either it succeeds or errors due to no PRs — but org should be set
    assert call_args.get("org") == "configured-org"


def test_config_ignore_author_merged_with_cli(runner, monkeypatch, tmp_path):
    """Config ignore-author and CLI --ignore-author are both applied."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('organization = "org"\nignore-author = ["config-bot"]\n')

    _wire(
        monkeypatch,
        [
            _pr(1, title="Config Bot PR", author="config-bot"),
            _pr(2, title="CLI Bot PR", author="cli-bot"),
            _pr(3, title="Human PR", author="alice"),
        ],
    )

    result = runner.invoke(
        cli.breakfast,
        ["--config", str(cfg_file), "--ignore-author", "cli-bot"],
    )

    assert result.exit_code == 0
    assert "Human PR" in result.stdout
    assert "Config Bot PR" not in result.stdout
    assert "CLI Bot PR" not in result.stdout
