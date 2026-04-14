from breakfast import config


def test_filter_pr_details_ignores_authors():
    pr_details = [
        {"user": {"login": "dependabot[bot]"}},
        {"user": {"login": "alice"}},
        {"user": {"login": "bob"}},
    ]

    filtered = config.filter_pr_details(
        pr_details,
        ignore_authors=["Dependabot[Bot]", "bob"],
    )

    assert filtered == [{"user": {"login": "alice"}}]


def test_filter_pr_details_mine_only():
    pr_details = [
        {"user": {"login": "alice"}},
        {"user": {"login": "bob"}},
    ]

    filtered = config.filter_pr_details(
        pr_details,
        ignore_authors=[],
        mine_only=True,
        current_user_login="alice",
    )

    assert filtered == [{"user": {"login": "alice"}}]


def test_filter_pr_details_no_drafts():
    pr_details = [
        {"user": {"login": "alice"}, "draft": False},
        {"user": {"login": "bob"}, "draft": True},
        {"user": {"login": "carol"}, "draft": False},
    ]

    filtered = config.filter_pr_details(pr_details, ignore_authors=[], no_drafts=True)

    assert filtered == [
        {"user": {"login": "alice"}, "draft": False},
        {"user": {"login": "carol"}, "draft": False},
    ]


def test_filter_pr_details_drafts_only():
    pr_details = [
        {"user": {"login": "alice"}, "draft": False},
        {"user": {"login": "bob"}, "draft": True},
        {"user": {"login": "carol"}, "draft": False},
    ]

    filtered = config.filter_pr_details(pr_details, ignore_authors=[], drafts_only=True)

    assert filtered == [{"user": {"login": "bob"}, "draft": True}]


def test_filter_pr_details_draft_field_missing():
    """PRs without a draft field should be treated as non-draft."""
    pr_details = [
        {"user": {"login": "alice"}},
        {"user": {"login": "bob"}, "draft": True},
    ]

    filtered = config.filter_pr_details(pr_details, ignore_authors=[], no_drafts=True)

    assert filtered == [{"user": {"login": "alice"}}]


def test_normalize_ignore_authors_multiple():
    ignore_authors = [" Dependabot[Bot] ", "", "ALICE", "alice", None, "bob"]

    result = config.normalize_ignore_authors(ignore_authors)

    assert result == {"dependabot[bot]", "alice", "bob"}


def test_load_config_expand_user(tmp_path, monkeypatch):
    # Mock HOME to tmp_path
    monkeypatch.setenv("HOME", str(tmp_path))

    cfg_file = tmp_path / "myconfig.toml"
    cfg_file.write_text('organization = "home-org"')

    # Test path with ~
    result = config.load_config(str(cfg_file).replace(str(tmp_path), "~"))
    assert result["organization"] == "home-org"


def test_generate_default_config(tmp_path, monkeypatch):
    # Mock Path.home() to tmp_path
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    # First run: should create the file
    result = config.generate_default_config()
    assert result is True
    config_file = tmp_path / ".config" / "breakfast" / "config.toml"
    assert config_file.exists()
    assert 'organization = "my-org"' in config_file.read_text()
    assert 'status-style = "emoji"' in config_file.read_text()

    # Second run: should not overwrite
    result2 = config.generate_default_config()
    assert result2 is False


def _make_pr(user="alice", state="open", repo="platform-api", pr_id=1):
    return {
        "id": pr_id,
        "user": {"login": user},
        "state": state,
        "base": {"repo": {"name": repo}},
        "number": pr_id,
    }


def test_filter_pr_details_filter_state():
    pr_details = [
        _make_pr(state="open", pr_id=1),
        _make_pr(state="closed", pr_id=2),
    ]

    result = config.filter_pr_details(pr_details, [], filter_state=("open",))
    assert len(result) == 1
    assert result[0]["id"] == 1

    result = config.filter_pr_details(pr_details, [], filter_state=("closed",))
    assert len(result) == 1
    assert result[0]["id"] == 2


def test_filter_pr_details_filter_state_draft():
    draft_pr = {**_make_pr(state="open", pr_id=1), "draft": True}
    open_pr = {**_make_pr(state="open", pr_id=2), "draft": False}
    closed_pr = {**_make_pr(state="closed", pr_id=3), "draft": False}
    pr_details = [draft_pr, open_pr, closed_pr]

    # draft only
    result = config.filter_pr_details(pr_details, [], filter_state=("draft",))
    assert [r["id"] for r in result] == [1]

    # closed + draft
    result = config.filter_pr_details(pr_details, [], filter_state=("closed", "draft"))
    assert sorted(r["id"] for r in result) == [1, 3]

    # open alone still includes draft PRs (state=open)
    result = config.filter_pr_details(pr_details, [], filter_state=("open",))
    assert sorted(r["id"] for r in result) == [1, 2]


def test_filter_pr_details_filter_check():
    pr_details = [_make_pr(pr_id=1), _make_pr(pr_id=2), _make_pr(pr_id=3)]
    check_statuses = {1: "pass", 2: "fail", 3: "pending"}

    result = config.filter_pr_details(
        pr_details, [], filter_check=("fail",), check_statuses=check_statuses
    )
    assert len(result) == 1
    assert result[0]["id"] == 2


def test_filter_pr_details_filter_approval():
    pr_details = [_make_pr(pr_id=1), _make_pr(pr_id=2), _make_pr(pr_id=3)]
    approval_statuses = {1: "approved", 2: "changes", 3: "pending"}

    result = config.filter_pr_details(
        pr_details,
        [],
        filter_approval=("approved",),
        approval_statuses=approval_statuses,
    )
    assert len(result) == 1
    assert result[0]["id"] == 1


def test_filter_pr_details_combined_filters():
    pr_details = [
        _make_pr(user="alice", state="open", repo="api", pr_id=1),
        _make_pr(user="bob", state="open", repo="api", pr_id=2),
        _make_pr(user="alice", state="closed", repo="api", pr_id=3),
    ]
    check_statuses = {1: "pass", 2: "pass", 3: "pass"}

    result = config.filter_pr_details(
        pr_details,
        [],
        filter_state=("open",),
        filter_check=("pass",),
        check_statuses=check_statuses,
    )
    assert {r["id"] for r in result} == {1, 2}


def test_get_config_dir_xdg(tmp_path, monkeypatch):
    custom_path = tmp_path / "custom-xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(custom_path))

    config_dir = config.get_config_dir()
    assert config_dir == custom_path / "breakfast"


def _make_pr_with_title(title, pr_id=1, user="alice"):
    return {"id": pr_id, "user": {"login": user}, "title": title}


def test_filter_search_title_plain_string():
    pr_details = [
        _make_pr_with_title("fix login bug", pr_id=1),
        _make_pr_with_title("Add user search", pr_id=2),
        _make_pr_with_title("chore: bump deps", pr_id=3),
    ]
    result = config.filter_pr_details(pr_details, [], search_title="login")
    assert len(result) == 1
    assert result[0]["id"] == 1


def test_filter_search_title_case_insensitive():
    pr_details = [
        _make_pr_with_title("Fix Login Bug", pr_id=1),
        _make_pr_with_title("chore: bump deps", pr_id=2),
    ]
    result = config.filter_pr_details(pr_details, [], search_title="login")
    assert len(result) == 1
    assert result[0]["id"] == 1


def test_filter_search_title_regex():
    pr_details = [
        _make_pr_with_title("fix: login bug", pr_id=1),
        _make_pr_with_title("chore: bump deps", pr_id=2),
        _make_pr_with_title("feat: add search", pr_id=3),
    ]
    result = config.filter_pr_details(pr_details, [], search_title="^fix|^feat")
    assert {r["id"] for r in result} == {1, 3}


def test_filter_search_title_no_match():
    pr_details = [
        _make_pr_with_title("fix login bug", pr_id=1),
        _make_pr_with_title("add user search", pr_id=2),
    ]
    result = config.filter_pr_details(pr_details, [], search_title="nonexistent")
    assert result == []


def test_filter_search_title_none_passes_all():
    pr_details = [
        _make_pr_with_title("fix login bug", pr_id=1),
        _make_pr_with_title("add user search", pr_id=2),
    ]
    result = config.filter_pr_details(pr_details, [], search_title=None)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# _extract_option_blocks
# ---------------------------------------------------------------------------


def test_extract_option_blocks_finds_all_keys():
    blocks = config._extract_option_blocks(config._DEFAULT_CONFIG_CONTENT)
    keys = [k for k, _ in blocks]
    # Spot-check a representative sample from every section
    for expected in [
        "organization",
        "repo-filter",
        "ignore-author",
        "mine-only",
        "limit",
        "age",
        "checks",
        "approvals",
        "max-title-length",
        "format",
        "status-style",
        "legendary",
        "legendary-only",
        "cache",
        "cache-ttl",
        "no-drafts",
        "workers",
        "api-stats",
        "no-colour",
    ]:
        assert expected in keys, f"key {expected!r} not found in extracted blocks"


def test_extract_option_blocks_block_includes_description():
    blocks = dict(config._extract_option_blocks(config._DEFAULT_CONFIG_CONTENT))
    # The organization block should include its description comment
    assert "GitHub organisation" in blocks["organization"]
    assert "# organization" in blocks["organization"]


def test_extract_option_blocks_no_duplicate_keys():
    blocks = config._extract_option_blocks(config._DEFAULT_CONFIG_CONTENT)
    keys = [k for k, _ in blocks]
    assert len(keys) == len(set(keys)), "duplicate keys found in extracted blocks"


# ---------------------------------------------------------------------------
# _key_present_in_file
# ---------------------------------------------------------------------------


def test_key_present_active():
    assert config._key_present_in_file("workers", "workers = 64\n")


def test_key_present_commented():
    assert config._key_present_in_file("workers", "# workers = 64\n")


def test_key_not_present():
    assert not config._key_present_in_file("workers", "# unrelated = true\n")


def test_key_present_with_surrounding_text():
    content = "organization = my-org\n# workers = 64\nno-colour = false\n"
    assert config._key_present_in_file("workers", content)
    assert not config._key_present_in_file("cache", content)


# ---------------------------------------------------------------------------
# update_config
# ---------------------------------------------------------------------------


def test_update_config_no_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)

    result = config.update_config()
    assert result is False


def test_update_config_already_up_to_date(tmp_path, monkeypatch):
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    config_dir = tmp_path / ".config" / "breakfast"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.toml"
    # Write a file that already contains all known keys
    full_content = config._DEFAULT_CONFIG_CONTENT
    config_file.write_text(full_content)

    result = config.update_config()
    assert result is True
    # No backup should be created (nothing was changed)
    backups = list(config_dir.glob("*.bak.*"))
    assert backups == []


def test_update_config_appends_missing_options(tmp_path, monkeypatch):
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    config_dir = tmp_path / ".config" / "breakfast"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.toml"
    # Write a minimal config that is missing most options
    config_file.write_text('organization = "my-org"\n')

    result = config.update_config()
    assert result is True

    updated = config_file.read_text()
    # The original content is preserved
    assert 'organization = "my-org"' in updated
    # Missing options were appended
    assert "# workers = 64" in updated
    assert "# no-colour = false" in updated
    # organization should NOT be duplicated
    assert updated.count("organization") == 1

    # A backup was created
    backups = list(config_dir.glob("config.toml.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text() == 'organization = "my-org"\n'


def test_update_config_does_not_duplicate_commented_key(tmp_path, monkeypatch):
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    config_dir = tmp_path / ".config" / "breakfast"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.toml"
    # workers is already present (commented out) — should not be added again
    config_file.write_text(config._DEFAULT_CONFIG_CONTENT)

    result = config.update_config()
    assert result is True

    updated = config_file.read_text()
    # Count occurrences of "# workers = 64" — should appear exactly once
    assert updated.count("# workers = 64") == 1


def test_update_config_cli_flag(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from breakfast import cli

    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli.breakfast, ["--update-config"])
    assert result.exit_code == 0
    assert "No config file found" in result.output
