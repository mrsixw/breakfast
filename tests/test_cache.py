import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from breakfast import cache, xdg

# The token every single-token test writes and reads with.
TOKEN = "token-123"

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


def test_parse_ttl_bool_rejected():
    """isinstance(True, int) is True; explicit reject so cache-ttl = true
    in TOML doesn't silently become 1 second."""
    with pytest.raises(ValueError):
        cache.parse_ttl(True)
    with pytest.raises(ValueError):
        cache.parse_ttl(False)


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
    assert cache.read_pr_cache("org", "filter", 300, token=TOKEN) is None


def test_write_then_read_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    pr_details = [{"number": 1, "title": "Hello"}]
    cache.write_pr_cache("org", "filter", pr_details, token=TOKEN)
    result = cache.read_pr_cache("org", "filter", 300, token=TOKEN)
    assert result is not None
    assert result["prs"] == pr_details
    assert result["check_statuses"] is None
    assert result["approval_statuses"] is None
    assert result["approval_details"] is None


def test_write_then_read_roundtrip_with_statuses(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    pr_details = [{"number": 1, "id": 101}]
    check_statuses = {101: "pass"}
    approval_statuses = {101: "approved"}
    approval_details = {101: {"status": "approved", "current": 2, "required": 2}}
    cache.write_pr_cache(
        "org",
        "filter",
        pr_details,
        check_statuses=check_statuses,
        approval_statuses=approval_statuses,
        approval_details=approval_details,
        token=TOKEN,
    )
    result = cache.read_pr_cache("org", "filter", 300, token=TOKEN)
    assert result["prs"] == pr_details
    assert result["check_statuses"] == check_statuses
    assert result["approval_statuses"] == approval_statuses
    assert result["approval_details"] == approval_details


def test_read_pr_cache_expired(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    pr_details = [{"number": 1}]
    cache.write_pr_cache("org", "filter", pr_details, token=TOKEN)

    # Manually backdate the fetched_at timestamp
    path = cache.cache_path("org", "filter", token=TOKEN)
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))

    assert cache.read_pr_cache("org", "filter", 300, token=TOKEN) is None


def test_read_pr_cache_not_expired(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    pr_details = [{"number": 1}]
    cache.write_pr_cache("org", "filter", pr_details, token=TOKEN)
    result = cache.read_pr_cache("org", "filter", 300, token=TOKEN)
    assert result is not None
    assert result["prs"] == pr_details


def test_read_pr_cache_corrupt_json(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    path = cache.cache_path("org", "filter", token=TOKEN)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json at all {{")
    assert cache.read_pr_cache("org", "filter", 300, token=TOKEN) is None


def test_read_pr_cache_missing_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    path = cache.cache_path("org", "filter", token=TOKEN)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat()}))
    assert cache.read_pr_cache("org", "filter", 300, token=TOKEN) is None


def test_write_pr_cache_creates_directory(monkeypatch, tmp_path):
    nested = tmp_path / "deep" / "nested"
    monkeypatch.setattr(cache, "_CACHE_DIR", nested)
    cache.write_pr_cache("org", "filter", [], token=TOKEN)
    assert nested.exists()


def test_write_pr_cache_is_atomic_no_lingering_tmp(monkeypatch, tmp_path):
    """Atomic write: no .tmp file should remain after a successful write."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_pr_cache("org", "filter", [{"number": 1}], token=TOKEN)
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []
    # The real cache file should be present and valid JSON.
    assert cache.cache_path("org", "filter", token=TOKEN).exists()


def test_write_graphql_cache_is_atomic_no_lingering_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_graphql_cache(
        "org", "filter", ["https://example.com/pr/1"], token=TOKEN
    )
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []
    assert cache.graphql_cache_path("org", "filter", token=TOKEN).exists()


def test_write_pr_cache_silent_on_failure(monkeypatch, tmp_path):
    """A write failure must not raise an exception."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "does_not_exist" / "x")
    # Make mkdir fail by pointing at a file path that already exists as a file
    blocker = tmp_path / "does_not_exist"
    blocker.write_text("I am a file, not a dir")
    monkeypatch.setattr(cache, "_CACHE_DIR", blocker / "x")
    # Should not raise
    cache.write_pr_cache("org", "filter", [{"number": 1}], token=TOKEN)


# ---------------------------------------------------------------------------
# XDG_CACHE_HOME env var
# ---------------------------------------------------------------------------


def test_get_cache_dir_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    result = xdg.get_cache_dir()
    assert result == tmp_path / "breakfast"


def test_get_cache_dir_default_without_xdg(monkeypatch):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    result = xdg.get_cache_dir()
    assert result == Path.home() / ".cache" / "breakfast"


# ---------------------------------------------------------------------------
# GraphQL cache
# ---------------------------------------------------------------------------


def test_graphql_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    urls = ["https://api.github.com/repos/org/repo/pulls/1"]
    cache.write_graphql_cache("org", "filter", urls, token=TOKEN)
    assert cache.read_graphql_cache("org", "filter", 300, token=TOKEN) == urls


def test_graphql_cache_miss_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    assert cache.read_graphql_cache("org", "filter", 300, token=TOKEN) is None


def test_graphql_cache_expired(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    urls = ["https://api.github.com/repos/org/repo/pulls/1"]
    cache.write_graphql_cache("org", "filter", urls, token=TOKEN)
    # Manually backdate the fetched_at timestamp
    path = cache.graphql_cache_path("org", "filter", token=TOKEN)
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))
    assert cache.read_graphql_cache("org", "filter", 300, token=TOKEN) is None


def test_graphql_cache_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.graphql_cache_path("org", "filter", token=TOKEN).parent.mkdir(
        parents=True, exist_ok=True
    )
    cache.graphql_cache_path("org", "filter", token=TOKEN).write_text("}{ bad json")
    assert cache.read_graphql_cache("org", "filter", 300, token=TOKEN) is None


def test_graphql_cache_uses_separate_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    assert cache.graphql_cache_path("org", "f", token=TOKEN) != cache.cache_path(
        "org", "f", token=TOKEN
    )


# ---------------------------------------------------------------------------
# click.echo(err=True) for cache warnings (#240)
# ---------------------------------------------------------------------------


def test_read_graphql_cache_corrupt_warns_to_stderr(tmp_path, monkeypatch):
    """Corrupt GraphQL cache emits warning via click.echo(err=True)."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.graphql_cache_path("org", "f", token=TOKEN).parent.mkdir(
        parents=True, exist_ok=True
    )
    cache.graphql_cache_path("org", "f", token=TOKEN).write_text("}{ bad json")

    echo_calls = []
    monkeypatch.setattr(
        cache.click, "echo", lambda msg, **kw: echo_calls.append((msg, kw))
    )
    monkeypatch.setattr(cache.click, "style", lambda msg, **kw: msg)

    result = cache.read_graphql_cache("org", "f", 300, token=TOKEN)

    assert result is None
    warning_calls = [c for c in echo_calls if "Warning" in str(c[0])]
    assert len(warning_calls) == 1
    assert warning_calls[0][1].get("err") is True


def test_write_graphql_cache_failure_warns_to_stderr(tmp_path, monkeypatch):
    """Failed GraphQL cache write emits warning via click.echo(err=True)."""
    # Place a file at _CACHE_DIR so mkdir() raises NotADirectoryError (OSError subclass)
    blocker = tmp_path / "cache_dir"
    blocker.write_text("not a directory")
    monkeypatch.setattr(cache, "_CACHE_DIR", blocker)

    echo_calls = []
    monkeypatch.setattr(
        cache.click, "echo", lambda msg, **kw: echo_calls.append((msg, kw))
    )
    monkeypatch.setattr(cache.click, "style", lambda msg, **kw: msg)

    cache.write_graphql_cache("org", "f", ["url1"], token=TOKEN)

    warning_calls = [c for c in echo_calls if "Warning" in str(c[0])]
    assert len(warning_calls) == 1
    assert warning_calls[0][1].get("err") is True


def test_read_pr_cache_corrupt_warns_to_stderr(tmp_path, monkeypatch):
    """Corrupt PR cache emits warning via click.echo(err=True)."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.cache_path("org", "f", token=TOKEN).parent.mkdir(parents=True, exist_ok=True)
    cache.cache_path("org", "f", token=TOKEN).write_text("}{ bad json")

    echo_calls = []
    monkeypatch.setattr(
        cache.click, "echo", lambda msg, **kw: echo_calls.append((msg, kw))
    )
    monkeypatch.setattr(cache.click, "style", lambda msg, **kw: msg)

    result = cache.read_pr_cache("org", "f", 300, token=TOKEN)

    assert result is None
    warning_calls = [c for c in echo_calls if "Warning" in str(c[0])]
    assert len(warning_calls) == 1
    assert warning_calls[0][1].get("err") is True


def test_write_pr_cache_failure_warns_to_stderr(tmp_path, monkeypatch):
    """Failed PR cache write emits warning via click.echo(err=True)."""
    # Place a file at _CACHE_DIR so mkdir() raises NotADirectoryError (OSError subclass)
    blocker = tmp_path / "cache_dir"
    blocker.write_text("not a directory")
    monkeypatch.setattr(cache, "_CACHE_DIR", blocker)

    echo_calls = []
    monkeypatch.setattr(
        cache.click, "echo", lambda msg, **kw: echo_calls.append((msg, kw))
    )
    monkeypatch.setattr(cache.click, "style", lambda msg, **kw: msg)

    cache.write_pr_cache("org", "f", [{"id": 1}], token=TOKEN)

    warning_calls = [c for c in echo_calls if "Warning" in str(c[0])]
    assert len(warning_calls) == 1
    assert warning_calls[0][1].get("err") is True


# ---------------------------------------------------------------------------
# per-repo PR cache
# ---------------------------------------------------------------------------


def test_write_then_read_repo_pr_cache_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    prs = [{"number": 1, "id": 101, "title": "hello"}]
    cache.write_repo_pr_cache("myorg", "myrepo", prs, token=TOKEN)
    result = cache.read_repo_pr_cache("myorg", "myrepo", 300, token=TOKEN)
    assert result is not None
    assert result["prs"] == prs
    assert result["check_statuses"] is None
    assert result["approval_statuses"] is None
    assert result["approval_details"] is None


def test_write_then_read_repo_pr_cache_with_statuses(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    prs = [{"number": 1, "id": 101}]
    checks = {101: "pass"}
    approvals = {101: "approved"}
    details = {101: {"status": "approved", "current": 1, "required": 1}}
    cache.write_repo_pr_cache(
        "myorg",
        "myrepo",
        prs,
        check_statuses=checks,
        approval_statuses=approvals,
        approval_details=details,
        token=TOKEN,
    )
    result = cache.read_repo_pr_cache("myorg", "myrepo", 300, token=TOKEN)
    assert result["prs"] == prs
    assert result["check_statuses"] == checks
    assert result["approval_statuses"] == approvals
    assert result["approval_details"] == details


def test_read_repo_pr_cache_miss_no_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    assert cache.read_repo_pr_cache("myorg", "myrepo", 300, token=TOKEN) is None


def test_read_repo_pr_cache_expired(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_repo_pr_cache("myorg", "myrepo", [{"number": 1}], token=TOKEN)
    path = cache.repo_pr_cache_path("myorg", "myrepo", token=TOKEN)
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))
    assert cache.read_repo_pr_cache("myorg", "myrepo", 300, token=TOKEN) is None


def test_read_repo_pr_cache_not_expired(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_repo_pr_cache("myorg", "myrepo", [{"number": 1}], token=TOKEN)
    result = cache.read_repo_pr_cache("myorg", "myrepo", 300, token=TOKEN)
    assert result is not None


def test_repo_pr_cache_key_differs_from_whole_blob_key(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    # repo_pr_cache_path uses (org, repo_name), not (org, repo_filter)
    p1 = cache.repo_pr_cache_path("org", "my-repo", token=TOKEN)
    p2 = cache.cache_path("org", "my-repo", token=TOKEN)
    assert p1 != p2
    assert p1.name.startswith("pr_repo_")
    assert p2.name.startswith("prs_")


def test_read_pr_cache_expired_but_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    pr_details = [{"number": 1}]
    cache.write_pr_cache("org", "filter", pr_details, token=TOKEN)

    # Manually backdate the fetched_at timestamp
    path = cache.cache_path("org", "filter", token=TOKEN)
    data = json.loads(path.read_text())
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    data["fetched_at"] = old_time
    path.write_text(json.dumps(data))

    # Should miss normally
    assert cache.read_pr_cache("org", "filter", 300, token=TOKEN) is None
    # Should hit with ignore_ttl=True
    result = cache.read_pr_cache("org", "filter", 300, ignore_ttl=True, token=TOKEN)
    assert result is not None
    assert result["prs"] == pr_details
    assert result["fetched_at"] == old_time


# ---------------------------------------------------------------------------
# user login cache (#334)
# ---------------------------------------------------------------------------


def test_write_and_read_cached_user_login(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_cached_user_login("token-one", "alice")
    assert cache.read_cached_user_login("token-one") == "alice"


def test_read_cached_user_login_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    assert cache.read_cached_user_login("token-one") is None


def test_read_cached_user_login_returns_none_on_corrupt_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    (tmp_path / "user.json").write_text("not json{{")
    assert cache.read_cached_user_login("token-one") is None


@pytest.mark.parametrize("payload", ["[]", '"alice"', '{"logins": []}'])
def test_read_cached_user_login_returns_none_on_wrong_shape(
    monkeypatch, tmp_path, payload
):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    (tmp_path / "user.json").write_text(payload)
    assert cache.read_cached_user_login("token-one") is None


def test_read_cached_user_login_returns_none_on_invalid_utf8(monkeypatch, tmp_path):
    """A damaged file must not crash the offline or rate-limit fallback."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    (tmp_path / "user.json").write_bytes(b'{"logins": {"\xff\xfe": "alice"}}')
    assert cache.read_cached_user_login("token-one") is None
    cache.write_cached_user_login("token-one", "bob")
    assert cache.read_cached_user_login("token-one") == "bob"


@pytest.mark.parametrize("value", [1, None, ""])
def test_read_cached_user_login_ignores_a_non_login_value(monkeypatch, tmp_path, value):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    key = cache._token_key("token-one")
    (tmp_path / "user.json").write_text(json.dumps({"logins": {key: value}}))
    assert cache.read_cached_user_login("token-one") is None


def test_write_cached_user_login_overwrites(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_cached_user_login("token-one", "alice")
    cache.write_cached_user_login("token-one", "bob")
    assert cache.read_cached_user_login("token-one") == "bob"


def test_cached_user_login_is_kept_per_token(monkeypatch, tmp_path):
    """Two tokens share user.json but never each other's login."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_cached_user_login("work-token", "alice")
    cache.write_cached_user_login("home-token", "bob")

    assert cache.read_cached_user_login("work-token") == "alice"
    assert cache.read_cached_user_login("home-token") == "bob"
    assert cache.read_cached_user_login("third-token") is None


def test_cached_user_login_never_stores_the_token(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_cached_user_login("ghp_secret_token", "alice")
    assert "ghp_secret_token" not in (tmp_path / "user.json").read_text()


def test_pre_token_user_json_is_ignored_then_replaced(monkeypatch, tmp_path):
    """The old {"login": ...} file cannot say whose login it is, so it is unused."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    (tmp_path / "user.json").write_text('{"login": "alice"}')

    assert cache.read_cached_user_login("token-one") is None
    cache.write_cached_user_login("token-one", "bob")
    assert cache.read_cached_user_login("token-one") == "bob"


def test_no_token_never_reads_or_writes_a_login(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_cached_user_login(None, "alice")
    assert not (tmp_path / "user.json").exists()
    assert cache.read_cached_user_login(None) is None


# ---------------------------------------------------------------------------
# Repository names cache
# ---------------------------------------------------------------------------


def test_repository_names_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    names_cache = cache.RepositoryNamesCache(token=TOKEN)

    names_cache.write("Acme", False, ["api", "web"])

    assert names_cache.read("acme", False) == ["api", "web"]
    assert list(tmp_path.glob(f"{cache.CACHE_SCHEMA_DIR}/repos_*.json"))


def test_repository_names_cache_miss_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)

    assert cache.RepositoryNamesCache(token=TOKEN).read("acme", False) is None


def test_repository_names_cache_keeps_archived_modes_apart(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    names_cache = cache.RepositoryNamesCache(token=TOKEN)

    names_cache.write("acme", False, ["api"])

    assert names_cache.read("acme", True) is None


def test_repository_names_cache_lasts_a_day_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    names_cache = cache.RepositoryNamesCache(token=TOKEN)
    names_cache.write("acme", False, ["api"])
    path = next(tmp_path.glob(f"{cache.CACHE_SCHEMA_DIR}/repos_*.json"))
    data = json.loads(path.read_text())

    data["fetched_at"] = (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat()
    path.write_text(json.dumps(data))
    assert names_cache.read("acme", False) == ["api"]

    data["fetched_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    path.write_text(json.dumps(data))
    assert names_cache.read("acme", False) is None


def test_repository_names_cache_refresh_skips_reads_but_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.RepositoryNamesCache(token=TOKEN).write("acme", False, ["old"])
    refreshing = cache.RepositoryNamesCache(refresh=True, token=TOKEN)

    assert refreshing.read("acme", False) is None
    refreshing.write("acme", False, ["new"])
    assert cache.RepositoryNamesCache(token=TOKEN).read("acme", False) == ["new"]


def test_repository_names_cache_corrupt_file_is_a_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    names_cache = cache.RepositoryNamesCache(token=TOKEN)
    names_cache.write("acme", False, ["api"])
    next(tmp_path.glob(f"{cache.CACHE_SCHEMA_DIR}/repos_*.json")).write_text(
        "}{ bad json"
    )

    assert names_cache.read("acme", False) is None


def test_repository_names_cache_write_failure_is_ignored(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    monkeypatch.setattr(cache, "_CACHE_DIR", blocker)

    cache.RepositoryNamesCache(token=TOKEN).write("acme", False, ["api"])


# ---------------------------------------------------------------------------
# Token scoping (#523)
# ---------------------------------------------------------------------------

WORK_TOKEN = "work-token"
HOME_TOKEN = "home-token"


def test_pr_cache_answers_only_for_the_token_that_wrote_it(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_pr_cache("org", "filter", [{"number": 1}], token=WORK_TOKEN)

    assert cache.read_pr_cache("org", "filter", 300, token=HOME_TOKEN) is None
    assert (
        cache.read_pr_cache("org", "filter", 300, token=HOME_TOKEN, ignore_ttl=True)
        is None
    )
    assert cache.read_pr_cache("org", "filter", 300, token=WORK_TOKEN)["prs"] == [
        {"number": 1}
    ]


def test_graphql_cache_answers_only_for_the_token_that_wrote_it(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    urls = ["https://github.com/org/repo/pull/1"]
    cache.write_graphql_cache("org", "filter", urls, token=WORK_TOKEN)

    assert cache.read_graphql_cache("org", "filter", 300, token=HOME_TOKEN) is None
    assert cache.read_graphql_cache("org", "filter", 300, token=WORK_TOKEN) == urls


def test_repo_pr_cache_answers_only_for_the_token_that_wrote_it(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_repo_pr_cache("org", "repo", [{"number": 1}], token=WORK_TOKEN)

    assert cache.read_repo_pr_cache("org", "repo", 300, token=HOME_TOKEN) is None
    assert cache.read_repo_pr_cache("org", "repo", 300, token=WORK_TOKEN)["prs"] == [
        {"number": 1}
    ]


def test_repository_names_answer_only_for_the_token_that_wrote_them(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.RepositoryNamesCache(token=WORK_TOKEN).write("org", False, ["api"])

    assert cache.RepositoryNamesCache(token=HOME_TOKEN).read("org", False) is None
    assert cache.RepositoryNamesCache(token=WORK_TOKEN).read("org", False) == ["api"]


def test_cache_files_never_hold_the_token(monkeypatch, tmp_path):
    """Neither a file name nor a file body may reveal the token."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    secret = "ghp_secret_token"
    cache.write_pr_cache("org", "filter", [{"number": 1}], token=secret)
    cache.write_graphql_cache("org", "filter", ["u"], token=secret)
    cache.write_repo_pr_cache("org", "repo", [{"number": 1}], token=secret)
    cache.RepositoryNamesCache(token=secret).write("org", False, ["api"])

    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert len(files) == 4
    for path in files:
        assert secret not in str(path.relative_to(tmp_path))
        assert secret not in path.read_text()


def test_scoped_cache_files_live_in_the_schema_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_pr_cache("org", "filter", [], token=WORK_TOKEN)

    assert cache.cache_path("org", "filter", token=WORK_TOKEN).parent == (
        tmp_path / cache.CACHE_SCHEMA_DIR
    )
    assert not list(tmp_path.glob("prs_*.json"))


def test_token_is_required_by_every_pr_data_function(monkeypatch, tmp_path):
    """Leaving the token out is an error, never a silently shared cache."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    with pytest.raises(TypeError):
        cache.write_pr_cache("org", "filter", [])
    with pytest.raises(TypeError):
        cache.read_graphql_cache("org", "filter", 300)
    with pytest.raises(TypeError):
        cache.read_repo_pr_cache("org", "repo", 300)
    with pytest.raises(TypeError):
        cache.RepositoryNamesCache()


# ---------------------------------------------------------------------------
# One-time removal of the unscoped cache (#523)
# ---------------------------------------------------------------------------

LEGACY_KEY = "0123456789abcdef"


def test_migration_removes_every_unscoped_cache_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    legacy = [
        f"prs_{LEGACY_KEY}.json",
        f"graphql_{LEGACY_KEY}.json",
        f"pr_repo_{LEGACY_KEY}.json",
        f"repos_{LEGACY_KEY}.json",
        f"prs_{LEGACY_KEY}.json.tmp",
    ]
    for name in legacy:
        (tmp_path / name).write_text("{}")

    assert cache.migrate_legacy_cache() == len(legacy)
    assert not any((tmp_path / name).exists() for name in legacy)


def test_migration_keeps_everything_else(monkeypatch, tmp_path):
    """Only files breakfast itself named are touched: the directory may be shared."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    cache.write_cached_user_login(WORK_TOKEN, "alice")
    cache.write_pr_cache("org", "filter", [], token=WORK_TOKEN)
    kept = ["latest_version.json", "prs_notes.json", f"prs_{LEGACY_KEY}.txt"]
    for name in kept:
        (tmp_path / name).write_text("{}")

    assert cache.migrate_legacy_cache() == 0
    assert all((tmp_path / name).exists() for name in kept)
    assert cache.read_cached_user_login(WORK_TOKEN) == "alice"
    assert cache.read_pr_cache("org", "filter", 300, token=WORK_TOKEN) is not None


def test_migration_without_a_cache_directory_removes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / "never_created")
    assert cache.migrate_legacy_cache() == 0


def test_migration_skips_a_file_it_cannot_remove(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)
    stuck = tmp_path / f"prs_{LEGACY_KEY}.json"
    gone = tmp_path / f"repos_{LEGACY_KEY}.json"
    stuck.write_text("{}")
    gone.write_text("{}")
    real_unlink = Path.unlink

    def unlink(self, *args, **kwargs):
        if self == stuck:
            raise PermissionError("read-only")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)

    assert cache.migrate_legacy_cache() == 1
    assert stuck.exists()
    assert not gone.exists()
