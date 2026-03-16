import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _get_cache_dir() -> Path:
    """Get the XDG-compliant cache directory."""
    xdg_cache = os.getenv("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache) / "breakfast"
    return Path.home() / ".cache" / "breakfast"


_CACHE_DIR = _get_cache_dir()

_SUFFIX_MAP = {"s": 1, "m": 60, "h": 3600}


def parse_ttl(value: str | int) -> int:
    """Parse a TTL value into seconds.

    Accepts: bare int, string int (e.g. "300"), or suffixed string ("5m", "2h", "30s").
    Raises ValueError for invalid or non-positive values.
    """
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"TTL must be positive, got {value}")
        return value

    s = str(value).strip()
    if not s:
        raise ValueError("TTL must not be empty")

    if s[-1] in _SUFFIX_MAP:
        suffix = s[-1]
        try:
            n = int(s[:-1])
        except ValueError:
            raise ValueError(f"Invalid TTL: {value!r}")
        if n <= 0:
            raise ValueError(f"TTL must be positive, got {value!r}")
        return n * _SUFFIX_MAP[suffix]

    try:
        n = int(s)
    except ValueError:
        raise ValueError(f"Invalid TTL: {value!r}")
    if n <= 0:
        raise ValueError(f"TTL must be positive, got {value!r}")
    return n


def make_cache_key(org: str, repo_filter: str) -> str:
    """Return a 16-hex-char key for (org, repo_filter), case-normalised."""
    raw = f"{org.lower()}:{repo_filter.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cache_path(org: str, repo_filter: str) -> Path:
    key = make_cache_key(org, repo_filter)
    return _CACHE_DIR / f"prs_{key}.json"


def read_pr_cache(org: str, repo_filter: str, ttl: int) -> list | None:
    """Return cached pr_details if present and within TTL, else None."""
    path = cache_path(org, repo_filter)
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        fetched_at = datetime.fromisoformat(data["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        if age > ttl:
            return None
        return data["prs"]
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"Warning: failed to read PR cache: {exc}", file=sys.stderr)
        return None


def write_pr_cache(org: str, repo_filter: str, pr_details: list) -> None:
    """Write pr_details to disk cache. Silently ignores write failures."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = cache_path(org, repo_filter)
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "organization": org,
            "repo_filter": repo_filter,
            "pr_count": len(pr_details),
            "prs": pr_details,
        }
        path.write_text(json.dumps(payload))
    except OSError as exc:
        print(f"Warning: failed to write PR cache: {exc}", file=sys.stderr)
