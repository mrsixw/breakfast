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
