from pathlib import Path

from breakfast import xdg


def test_get_cache_dir_with_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert xdg.get_cache_dir() == tmp_path / "breakfast"


def test_get_cache_dir_default(monkeypatch):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    assert xdg.get_cache_dir() == Path.home() / ".cache" / "breakfast"


def test_get_config_dir_with_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert xdg.get_config_dir() == tmp_path / "breakfast"


def test_get_config_dir_default(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert xdg.get_config_dir() == Path.home() / ".config" / "breakfast"


def test_get_state_dir_with_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert xdg.get_state_dir() == tmp_path / "breakfast"


def test_get_state_dir_default(monkeypatch):
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    assert xdg.get_state_dir() == Path.home() / ".local" / "state" / "breakfast"


def test_get_config_paths_returns_three_paths(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    paths = xdg.get_config_paths()
    assert len(paths) == 3
    assert paths[0] == tmp_path / ".breakfast.toml"
    assert paths[1] == Path.home() / ".config" / "breakfast" / "config.toml"
    assert paths[2] == Path.home() / ".breakfast.toml"


def test_get_config_paths_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    paths = xdg.get_config_paths()
    assert paths[1] == tmp_path / "xdg" / "breakfast" / "config.toml"


def test_get_cache_dir_ignores_relative_xdg(monkeypatch):
    """Per the XDG spec, relative $XDG_*_HOME values must be ignored."""
    monkeypatch.setenv("XDG_CACHE_HOME", "./relative")
    assert xdg.get_cache_dir() == Path.home() / ".cache" / "breakfast"


def test_get_config_dir_ignores_relative_xdg(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "./relative")
    assert xdg.get_config_dir() == Path.home() / ".config" / "breakfast"


def test_get_state_dir_ignores_relative_xdg(monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", "./relative")
    assert xdg.get_state_dir() == Path.home() / ".local" / "state" / "breakfast"


def test_get_cache_dir_ignores_empty_xdg(monkeypatch):
    """Empty XDG vars should also fall through to the default."""
    monkeypatch.setenv("XDG_CACHE_HOME", "")
    assert xdg.get_cache_dir() == Path.home() / ".cache" / "breakfast"
