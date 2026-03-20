# PR Caching Design for breakfast

> **Tracking issue:** [#45 — Cache GitHub API responses locally](https://github.com/mrsixw/breakfast/issues/45)

## Overview

Add a local disk cache for GitHub API responses so repeated runs within a short
window skip redundant API calls. If you run `breakfast` twice in five minutes,
the second run should be instant — no network round-trips, no rate-limit
pressure, just a warm plate of cached PRs. 🍳

```bash
breakfast          # fetches from API, writes cache
breakfast          # cache hit — served in milliseconds
breakfast --no-cache  # always fetches fresh
```

## What to Cache

**Cache: raw PR detail objects** after the `_fetch_pr_detail` REST calls, before
any in-memory filtering. This means `--ignore-author` and `--mine-only` can vary
between runs without re-fetching the underlying data.

**Also cache: CI check statuses and review approval statuses.**
_(Added in [#113 — filter options](https://github.com/mrsixw/breakfast/issues/113))_
When `--checks`, `--approvals`, or the corresponding filter flags are used, the
fetched statuses are stored in the same cache file alongside the PR details.
Subsequent runs within the TTL reuse the cached statuses without hitting the API
again.

## Cache Key

SHA-256 of `"{org.lower()}:{filter.lower()}"`, truncated to the first 16 hex
characters → filename `prs_{hash16}.json`.

```
org=MyOrg, filter=Platform  →  prs_3f8a1d9c2b047e56.json
org=myorg, filter=platform  →  prs_3f8a1d9c2b047e56.json  (same — normalised)
```

Using a content-derived hash rather than a slugified name keeps filenames short
and safe for any input, while still being one-file-per-query.

## Cache File Format

```json
{
  "fetched_at": "2026-03-11T18:30:45+00:00",
  "organization": "my-org",
  "repo_filter": "platform",
  "pr_count": 42,
  "prs": [{}, {}]
}
```

`fetched_at` is an ISO-8601 UTC timestamp used to evaluate TTL. `pr_count` is
redundant but useful for humans inspecting the file.

### Extended format (added in #113)

When check or approval statuses have been fetched, they are stored in the same
file as optional top-level keys:

```json
{
  "fetched_at": "2026-03-11T18:30:45+00:00",
  "organization": "my-org",
  "repo_filter": "platform",
  "pr_count": 42,
  "prs": [{}, {}],
  "check_statuses": {"101": "pass", "102": "fail"},
  "approval_statuses": {"101": "approved", "102": "pending"}
}
```

`check_statuses` and `approval_statuses` are omitted when `--checks`/`--approvals`
were not used in the run that wrote the cache. Older cache files without these
fields are handled gracefully — the statuses are treated as uncached and fetched
on demand. JSON requires string keys; they are converted back to `int` on read.

## Cache Location

Follows the XDG Base Directory spec — the same convention as `updater.py`:

```
~/.cache/breakfast/prs_{hash16}.json              (default)
$XDG_CACHE_HOME/breakfast/prs_{hash16}.json       (if XDG_CACHE_HOME is set)
```

## TTL and `--cache-ttl`

Default: **300 seconds (5 minutes)**. Configurable via CLI flag or config file:

```bash
breakfast --cache-ttl 300    # plain integer → seconds
breakfast --cache-ttl 5m     # minutes suffix
breakfast --cache-ttl 2h     # hours suffix
breakfast --cache-ttl 30s    # explicit seconds suffix
```

Supported suffixes: `s`, `m`, `h`. Invalid formats (unknown suffix, zero,
negative, non-numeric) exit with a clear error message and code 1.

`cache-ttl` can also be set in `.breakfast.toml` or
`~/.config/breakfast/config.toml`. CLI takes precedence over config file.

## `--no-cache`

Bypasses reading from **and** writing to the cache for that invocation.
This is intentionally **not** a config file option — a persistent no-cache
setting defeats the purpose of having a cache.

## Behaviour Table

| Scenario | Behaviour |
|----------|-----------|
| Cache miss / TTL expired | Fetch from API, write cache |
| Cache hit within TTL | Read from cache, skip API fetch |
| `--no-cache` | Always fetch from API, never read/write cache |
| Cache file corrupt or unreadable | Warning to stderr, fall back to live fetch |
| Cache directory unwritable | Warning to stderr, proceed without caching |
| `--checks` / `--approvals` enabled, statuses cached | Statuses read from cache, no API call |
| `--checks` / `--approvals` enabled, statuses not cached | Statuses fetched from API and written to cache |

Cache failures are **never fatal** — a warning appears on stderr but results
are always returned, either from cache or from a live fetch.

## Implementation Plan

### New module: `src/breakfast/cache.py`

```python
_CACHE_DIR = _get_cache_dir()  # module-level — enables monkeypatch in tests

def parse_ttl(value: str | int) -> int:
    """Parse a TTL value to seconds. Accepts int or string with s/m/h suffix."""
    ...

def make_cache_key(organization: str, repo_filter: str) -> str:
    """Return the first 16 hex chars of SHA-256("{org}:{filter}") (lowercased)."""
    ...

def cache_path(organization: str, repo_filter: str) -> Path:
    """Return the Path for a given org+filter cache file."""
    ...

def read_pr_cache(organization: str, repo_filter: str, ttl: int) -> list | None:
    """Return cached PR list if present and fresh, else None."""
    ...

def write_pr_cache(organization: str, repo_filter: str, pr_details: list) -> None:
    """Persist PR details to cache. Silently no-ops on any I/O error."""
    ...
```

All file I/O is wrapped in `try/except Exception` — cache failure must never
prevent results from being shown.

`_get_cache_dir()` mirrors the implementation in `updater.py`:

```python
def _get_cache_dir() -> Path:
    xdg_cache = os.getenv("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache) / "breakfast"
    return Path.home() / ".cache" / "breakfast"
```

### `src/breakfast/cli.py`

- Add `--cache-ttl` option (default `None`; accepts int or suffix string)
- Add `--no-cache` flag (`is_flag=True`, default `False`)
- Resolve effective TTL: CLI → config → `300`
- Wrap the PR fetch with cache read/write logic before invoking `get_github_prs`
- Update `--show-config` output to include `cache-ttl` and `no-cache`

### `src/breakfast/config.py`

Add `cache-ttl` as a commented-out entry in the `generate_default_config()`
template so users see it when they run `--init-config`:

```toml
# How long to cache PR results (seconds, or use suffix: 5m, 2h)
# cache-ttl = 300
```

### Testing

**New `tests/test_cache.py`:**

- `parse_ttl` with valid inputs: bare int, `"300"`, `"5m"`, `"2h"`, `"30s"`
- `parse_ttl` with invalid inputs: zero, negative, bad suffix, empty string
- `make_cache_key` is deterministic and lowercase-normalised for any input
- `read_pr_cache` hit/miss/expired/corrupt/missing-keys all behave correctly
- `write_pr_cache` creates directory, roundtrip read returns same list, silent on write failure
- `XDG_CACHE_HOME` env var respected

All cache tests use `monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path)` —
the same pattern as `test_updater.py`.

**Additions to `tests/test_cli.py`:**

- Cache hit skips `get_github_prs` call
- `--no-cache` always calls `get_github_prs` even with a valid cache present
- `--no-cache` writes nothing to the cache directory
- Invalid `--cache-ttl` value exits with code 1
- Config `cache-ttl = "5m"` is respected when no CLI flag is provided
- Corrupt cache triggers a live fetch (no crash)

## What Goes in Config vs What Doesn't

**Belongs in config:**
- `cache-ttl` — a stable per-user preference (some environments have slower networks)

**Does NOT belong in config:**
- `--no-cache` — a per-invocation override; a persistent no-cache defeats the purpose

## Example User Workflows

### Everyday use (cache is transparent)

```bash
breakfast -r my-app     # fetches from API, caches result
breakfast -r my-app     # instant — served from cache
breakfast -r my-app --ignore-author dependabot[bot]   # still instant — filtered in-memory
```

### Longer-lived cache for slow networks

```toml
# ~/.config/breakfast/config.toml
cache-ttl = "30m"
```

```bash
breakfast    # cache stays fresh for 30 minutes between runs
```

### Force a fresh fetch

```bash
breakfast --no-cache    # always hits the API, but caches the result for next time
```
