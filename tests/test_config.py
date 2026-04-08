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
