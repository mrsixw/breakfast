import json
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError

import requests

from breakfast import updater, xdg


def test_parse_version_tuple():
    assert updater._parse_version_tuple("1.2.3") == (1, 2, 3)
    assert updater._parse_version_tuple("0.10.0") == (0, 10, 0)
    assert updater._parse_version_tuple("bad") == ()
    assert updater._parse_version_tuple(None) == ()


def test_parse_version_tuple_prerelease_alpha():
    assert updater._parse_version_tuple("1.0.0a1") == (1, 0, 0)


def test_parse_version_tuple_prerelease_dash():
    assert updater._parse_version_tuple("1.0.0-beta") == (1, 0, 0)


def test_parse_version_tuple_prerelease_rc():
    assert updater._parse_version_tuple("2.1.0rc3") == (2, 1, 0)


def test_parse_version_tuple_prerelease_compared_correctly():
    assert updater._parse_version_tuple("1.0.0a1") < updater._parse_version_tuple(
        "1.0.1"
    )
    assert updater._parse_version_tuple("2.0.0-beta") < updater._parse_version_tuple(
        "2.0.1"
    )


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
        status_code = 200

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


def test_write_version_cache_stores_release_body(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_CACHE_DIR", tmp_path)

    body = "- fix: some thing\n- feat: other"
    updater._write_version_cache("3.0.0", release_body=body)
    assert updater._read_cached_release_body() == body


def test_write_version_cache_no_body_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_CACHE_DIR", tmp_path)

    updater._write_version_cache("3.0.0")
    assert updater._read_cached_release_body() is None


def test_get_release_summary_bullet_points():
    body = (
        "## What's new\n- fix: bug squashed\n- feat: cool thing\n"
        "- chore: cleanup\n- extra: fourth"
    )
    summary = updater.get_release_summary(body)
    assert "fix: bug squashed" in summary
    assert "feat: cool thing" in summary
    assert "extra: fourth" not in summary  # only first 3 bullets


def test_get_release_summary_strips_headers():
    body = "# Release v1.0\n## Changes\n- fix: something"
    summary = updater.get_release_summary(body)
    assert "#" not in summary
    assert "fix: something" in summary


def test_get_release_summary_strips_urls():
    body = "- fix: see https://github.com/org/repo/issues/1 for details"
    summary = updater.get_release_summary(body)
    assert "https://" not in summary
    assert "fix: see" in summary


def test_get_release_summary_truncates():
    body = "- " + "x" * 300
    summary = updater.get_release_summary(body, max_chars=50)
    assert len(summary) <= 50
    assert summary.endswith("…")


def test_get_release_summary_empty_body():
    assert updater.get_release_summary("") == ""
    assert updater.get_release_summary(None) == ""


def test_check_for_update_with_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(updater, "pkg_version", lambda _name: "0.9.0")
    monkeypatch.setattr(updater, "get_latest_version", lambda: "0.10.0")
    updater._write_version_cache("0.10.0", release_body="- feat: cool new feature")

    result = updater.check_for_update(show_summary=True)

    assert result is not None
    assert "cool new feature" in result
    assert "📋" in result


def test_check_for_update_without_summary_does_not_include_body(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(updater, "pkg_version", lambda _name: "0.9.0")
    monkeypatch.setattr(updater, "get_latest_version", lambda: "0.10.0")
    updater._write_version_cache("0.10.0", release_body="- feat: cool new feature")

    result = updater.check_for_update(show_summary=False)

    assert result is not None
    assert "cool new feature" not in result


def test_check_for_update_summary_missing_body_still_shows_banner(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(updater, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(updater, "pkg_version", lambda _name: "0.9.0")
    monkeypatch.setattr(updater, "get_latest_version", lambda: "0.10.0")
    updater._write_version_cache("0.10.0")  # no body

    result = updater.check_for_update(show_summary=True)

    assert result is not None
    assert "fresh breakfast" in result
    assert "📋" not in result


def test_get_latest_version_stores_release_body(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "_CACHE_DIR", tmp_path)

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"tag_name": "v2.0.0", "body": "- feat: new thing"}

    monkeypatch.setattr(updater.requests, "get", lambda *a, **kw: FakeResp())

    updater.get_latest_version()
    assert updater._read_cached_release_body() == "- feat: new thing"


def test_get_cache_dir_xdg(tmp_path, monkeypatch):
    custom_path = tmp_path / "custom-cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(custom_path))

    cache_dir = xdg.get_cache_dir()
    assert cache_dir == custom_path / "breakfast"
