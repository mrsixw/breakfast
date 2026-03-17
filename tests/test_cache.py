import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from breakfast import cache

# ---------------------------------------------------------------------------
# parse_ttl
# ---------------------------------------------------------------------------


def test_parse_ttl_bare_int():
    assert cache.parse_ttl(300) == 300


def test_parse_ttl_string_int():
    assert cache.parse_ttl("300") == 300


def test_parse_ttl_seconds_suffix():
    assert cache.parse_ttl("30s") == 30


def test_parse_ttl_minutes_suffix():
    assert cache.parse_ttl("5m") == 300


def test_parse_ttl_hours_suffix():
    assert cache.parse_ttl("2h") == 7200


def test_parse_ttl_zero_raises():
    with pytest.raises(ValueError):
        cache.parse_ttl(0)


def test_parse_ttl_negative_raises():
    with pytest.raises(ValueError):
        cache.parse_ttl(-1)


def test_parse_ttl_zero_string_raises():
    with pytest.raises(ValueError):
        cache.parse_ttl("0")


def test_parse_ttl_negative_minutes_raises():
    with pytest.raises(ValueError):
        cache.parse_ttl("-5m")


def test_parse_ttl_bad_suffix_raises():
    with pytest.raises(ValueError):
        cache.parse_ttl("5x")


def test_parse_ttl_empty_string_raises():
    with pytest.raises(ValueError):
        cache.parse_ttl("")


# ---------------------------------------------------------------------------
# make_cache_key
# ---------------------------------------------------------------------------


def test_make_cache_key_deterministic():
    k1 = cache.make_cache_key("myorg", "platform")
    k2 = cache.make_cache_key("myorg", "platform")
    assert k1 == k2


def test_make_cache_key_case_normalised():
    assert cache.make_cache_key("MyOrg", "Platform") == cache.make_cache_key(
        "myorg", "platform"
    )


def test_make_cache_key_length():
    key = cache.make_cache_key("org", "filter")
    assert len(key) == 16


def test_make_cache_key_differs_by_input():
    assert cache.make_cache_key("org1", "filter") != cache.make_cache_key(
        "org2", "filter"
    )


# ---------------------------------------------------------------------------
# read_pr_cache / write_pr_cache
# ---------------------------------------------------------------------------


def test_read_pr_cache_miss_no_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    assert cache.read_pr_cache("org", "filter", 300) is None


def test_write_then_read_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    pr_details = [{"number": 1, "title": "Hello"}]
    cache.write_pr_cache("org", "filter", pr_details)
    result = cache.read_pr_cache("org", "filter", 300)
    assert result == pr_details


def test_read_pr_cache_expired(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    pr_details = [{"number": 1}]
    cache.write_pr_cache("org", "filter", pr_details)

    # Manually backdate the fetched_at timestamp
    path = cache.cache_path("org", "filter")
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))

    assert cache.read_pr_cache("org", "filter", 300) is None


def test_read_pr_cache_not_expired(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    pr_details = [{"number": 1}]
    cache.write_pr_cache("org", "filter", pr_details)
    result = cache.read_pr_cache("org", "filter", 300)
    assert result is not None


def test_read_pr_cache_corrupt_json(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = cache.cache_path("org", "filter")
    path.write_text("not json at all {{")
    assert cache.read_pr_cache("org", "filter", 300) is None


def test_read_pr_cache_missing_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = cache.cache_path("org", "filter")
    path.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat()}))
    assert cache.read_pr_cache("org", "filter", 300) is None


def test_write_pr_cache_creates_directory(monkeypatch, tmp_path):
    nested = tmp_path / "deep" / "nested"
    monkeypatch.setattr(cache, "_CACHE_DIR", nested)
    cache.write_pr_cache("org", "filter", [])
    assert nested.exists()


def test_write_pr_cache_silent_on_failure(monkeypatch, tmp_path):
    """A write failure must not raise an exception."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "does_not_exist" / "x")
    # Make mkdir fail by pointing at a file path that already exists as a file
    blocker = tmp_path / "does_not_exist"
    blocker.write_text("I am a file, not a dir")
    monkeypatch.setattr(cache, "_CACHE_DIR", blocker / "x")
    # Should not raise
    cache.write_pr_cache("org", "filter", [{"number": 1}])


# ---------------------------------------------------------------------------
# XDG_CACHE_HOME env var
# ---------------------------------------------------------------------------


def test_get_cache_dir_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    result = cache._get_cache_dir()
    assert result == tmp_path / "breakfast"


def test_get_cache_dir_default_without_xdg(monkeypatch):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    result = cache._get_cache_dir()
    assert result == Path.home() / ".cache" / "breakfast"


# ---------------------------------------------------------------------------
# GraphQL cache
# ---------------------------------------------------------------------------


def test_graphql_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    urls = ["https://api.github.com/repos/org/repo/pulls/1"]
    cache.write_graphql_cache("org", "filter", urls)
    assert cache.read_graphql_cache("org", "filter", 300) == urls


def test_graphql_cache_miss_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    assert cache.read_graphql_cache("org", "filter", 300) is None


def test_graphql_cache_expired(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    urls = ["https://api.github.com/repos/org/repo/pulls/1"]
    cache.write_graphql_cache("org", "filter", urls)
    # Manually backdate the fetched_at timestamp
    path = cache.graphql_cache_path("org", "filter")
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))
    assert cache.read_graphql_cache("org", "filter", 300) is None


def test_graphql_cache_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.graphql_cache_path("org", "filter").parent.mkdir(parents=True, exist_ok=True)
    cache.graphql_cache_path("org", "filter").write_text("}{bad json")
    assert cache.read_graphql_cache("org", "filter", 300) is None


def test_graphql_cache_uses_separate_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    assert cache.graphql_cache_path("org", "f") != cache.cache_path("org", "f")
