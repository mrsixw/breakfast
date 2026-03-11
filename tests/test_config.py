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


def test_normalize_ignore_authors_multiple():
    ignore_authors = [" Dependabot[Bot] ", "", "ALICE", "alice", None, "bob"]

    result = config.normalize_ignore_authors(ignore_authors)

    assert result == {"dependabot[bot]", "alice", "bob"}


def test_load_config_expand_user(tmp_path, monkeypatch):
    import os
    # Mock HOME to tmp_path
    monkeypatch.setenv("HOME", str(tmp_path))
    
    cfg_file = tmp_path / "myconfig.toml"
    cfg_file.write_text('organization = "home-org"')
    
    # Test path with ~
    result = config.load_config(str(cfg_file).replace(str(tmp_path), "~"))
    assert result["organization"] == "home-org"
