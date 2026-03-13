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


def test_get_config_dir_xdg(tmp_path, monkeypatch):
    custom_path = tmp_path / "custom-xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(custom_path))

    config_dir = config.get_config_dir()
    assert config_dir == custom_path / "breakfast"
