import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .logger import logger
from .xdg import get_cache_dir

_CACHE_DIR = get_cache_dir()

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


def graphql_cache_path(org: str, repo_filter: str) -> Path:
    key = make_cache_key(org, repo_filter)
    return _CACHE_DIR / f"graphql_{key}.json"


def read_graphql_cache(org: str, repo_filter: str, ttl: int) -> list | None:
    """Return cached PR URL list if present and within TTL, else None."""
    path = graphql_cache_path(org, repo_filter)
    try:
        if not path.exists():
            logger.debug("cache_miss layer=graphql path=%s reason=file_not_found", path)
            return None
        data = json.loads(path.read_text())
        fetched_at = datetime.fromisoformat(data["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        if age > ttl:
            logger.debug(
                "cache_miss layer=graphql path=%s reason=expired age=%.0fs ttl=%ss",
                path,
                age,
                ttl,
            )
            return None
        logger.debug(
            "cache_hit layer=graphql path=%s age=%.0fs url_count=%d",
            path,
            age,
            len(data["urls"]),
        )
        return data["urls"]
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning(
            "cache_read_error layer=graphql path=%s error=%r", path, str(exc)
        )
        print(f"Warning: failed to read GraphQL cache: {exc}", file=sys.stderr)
        return None


def write_graphql_cache(org: str, repo_filter: str, urls: list) -> None:
    """Write PR URL list to disk cache. Silently ignores write failures."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = graphql_cache_path(org, repo_filter)
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "organization": org,
            "repo_filter": repo_filter,
            "url_count": len(urls),
            "urls": urls,
        }
        path.write_text(json.dumps(payload))
        logger.debug("cache_write layer=graphql path=%s url_count=%d", path, len(urls))
    except OSError as exc:
        logger.warning(
            "cache_write_error layer=graphql path=%s error=%r",
            graphql_cache_path(org, repo_filter),
            str(exc),
        )
        print(f"Warning: failed to write GraphQL cache: {exc}", file=sys.stderr)


def read_pr_cache(org: str, repo_filter: str, ttl: int) -> dict | None:
    """Return cached data if present and within TTL, else None.

    On a hit, returns a dict with keys:
      "prs"              – list of PR detail dicts
      "check_statuses"   – dict[int, str] or None (absent from older caches)
      "approval_statuses"– dict[int, str] or None (absent from older caches)
      "approval_details" – dict[int, dict] or None (absent from older caches)
    """
    path = cache_path(org, repo_filter)
    try:
        if not path.exists():
            logger.debug(
                "cache_miss layer=pr_detail path=%s reason=file_not_found", path
            )
            return None
        data = json.loads(path.read_text())
        fetched_at = datetime.fromisoformat(data["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        if age > ttl:
            logger.debug(
                "cache_miss layer=pr_detail path=%s reason=expired age=%.0fs ttl=%ss",
                path,
                age,
                ttl,
            )
            return None
        # JSON keys are always strings; convert back to int for PR IDs.
        raw_checks = data.get("check_statuses")
        raw_approvals = data.get("approval_statuses")
        raw_approval_details = data.get("approval_details")
        pr_count = len(data["prs"])
        logger.debug(
            "cache_hit layer=pr_detail path=%s age=%.0fs pr_count=%d",
            path,
            age,
            pr_count,
        )
        return {
            "prs": data["prs"],
            "check_statuses": (
                {int(k): v for k, v in raw_checks.items()}
                if raw_checks is not None
                else None
            ),
            "approval_statuses": (
                {int(k): v for k, v in raw_approvals.items()}
                if raw_approvals is not None
                else None
            ),
            "approval_details": (
                {int(k): v for k, v in raw_approval_details.items()}
                if raw_approval_details is not None
                else None
            ),
        }
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning(
            "cache_read_error layer=pr_detail path=%s error=%r", path, str(exc)
        )
        print(f"Warning: failed to read PR cache: {exc}", file=sys.stderr)
        return None


def write_pr_cache(
    org: str,
    repo_filter: str,
    pr_details: list,
    check_statuses: dict | None = None,
    approval_statuses: dict | None = None,
    approval_details: dict | None = None,
) -> None:
    """Write pr_details (and optional statuses) to disk cache."""
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
        # Store with string keys (JSON requirement); restored to int on read.
        if check_statuses is not None:
            payload["check_statuses"] = {str(k): v for k, v in check_statuses.items()}
        if approval_statuses is not None:
            payload["approval_statuses"] = {
                str(k): v for k, v in approval_statuses.items()
            }
        if approval_details is not None:
            payload["approval_details"] = {
                str(k): v for k, v in approval_details.items()
            }
        path.write_text(json.dumps(payload))
        logger.debug(
            "cache_write layer=pr_detail path=%s pr_count=%d", path, len(pr_details)
        )
    except OSError as exc:
        logger.warning(
            "cache_write_error layer=pr_detail path=%s error=%r",
            cache_path(org, repo_filter),
            str(exc),
        )
        print(f"Warning: failed to write PR cache: {exc}", file=sys.stderr)
