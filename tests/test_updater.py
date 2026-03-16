import json
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError

import requests

from breakfast import updater


def test_parse_version_tuple():
    assert updater._parse_version_tuple("1.2.3") == (1, 2, 3)
    assert updater._parse_version_tuple("0.10.0") == (0, 10, 0)
    assert updater._parse_version_tuple("bad") == ()
    assert updater._parse_version_tuple(None) == ()


def test_check_for_update_newer_available(monkeypatch):
    monkeypatch.setattr(updater, "pkg_version", lambda _name: "0.9.0")
    monkeypatch.setattr(updater, "get_latest_version", lambda: "0.10.0")

    result = updater.check_for_update()

    assert result is not None
    assert "v0.9.0" in result
    assert "v0.10.0" in result
    assert "fresh breakfast" in result


def test_check_for_update_up_to_date(monkeypatch):
    monkeypatch.setattr(updater, "pkg_version", lambda _name: "0.10.0")
    monkeypatch.setattr(updater, "get_latest_version", lambda: "0.10.0")

    assert updater.check_for_update() is None


def test_check_for_update_no_latest(monkeypatch):
    monkeypatch.setattr(updater, "pkg_version", lambda _name: "0.10.0")
    monkeypatch.setattr(updater, "get_latest_version", lambda: None)

    assert updater.check_for_update() is None


def test_check_for_update_handles_errors(monkeypatch):
    def boom(_name):
        raise PackageNotFoundError("breakfast")

    monkeypatch.setattr(updater, "pkg_version", boom)
    monkeypatch.setattr(updater, "get_latest_version", lambda: "1.0.0")

    assert updater.check_for_update() is None


def test_get_latest_version_from_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_CACHE_DIR", tmp_path)
    cache_file = tmp_path / "latest_version.json"
    cache_file.write_text(
        json.dumps(
            {
                "latest_version": "1.2.3",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )

    assert updater.get_latest_version() == "1.2.3"


def test_get_latest_version_expired_cache_fetches(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_CACHE_DIR", tmp_path)
    # Note: SECRET_GITHUB_TOKEN is in api.py, but updater uses it if imported.
    # Looking at src/breakfast/updater.py to see how it uses token.
    # Wait, let me check updater.py imports.

    cache_file = tmp_path / "latest_version.json"
    old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
    cache_file.write_text(
        json.dumps(
            {
                "latest_version": "0.1.0",
                "checked_at": old_time.isoformat(),
            }
        )
    )

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"tag_name": "v2.0.0"}

    monkeypatch.setattr(
        updater.requests,
        "get",
        lambda *args, **kwargs: FakeResp(),
    )

    assert updater.get_latest_version() == "2.0.0"


def test_get_latest_version_api_failure_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_CACHE_DIR", tmp_path)

    def fail(*args, **kwargs):
        raise requests.exceptions.ConnectionError("nope")

    monkeypatch.setattr(updater.requests, "get", fail)

    assert updater.get_latest_version() is None


def test_write_and_read_version_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_CACHE_DIR", tmp_path)

    updater._write_version_cache("3.0.0")
    assert updater._read_version_cache() == "3.0.0"


def test_get_cache_dir_xdg(tmp_path, monkeypatch):
    custom_path = tmp_path / "custom-cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(custom_path))

    cache_dir = updater._get_cache_dir()
    assert cache_dir == custom_path / "breakfast"
