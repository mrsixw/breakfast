import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import click

from .constants import (
    CACHE_KEY_HEX_CHARS,
    CACHE_SCHEMA_DIR,
    LEGACY_CACHE_PREFIXES,
    REPOSITORY_NAMES_CACHE_TTL,
    TTL_SUFFIX_MAP,
    USER_LOGIN_CACHE_FILE,
)
from .logger import logger
from .xdg import get_cache_dir

__all__ = [
    "RepositoryNamesCache",
    "cache_path",
    "graphql_cache_path",
    "make_cache_key",
    "migrate_legacy_cache",
    "parse_ttl",
    "read_cached_user_login",
    "read_graphql_cache",
    "read_pr_cache",
    "read_repo_pr_cache",
    "repo_pr_cache_path",
    "write_cached_user_login",
    "write_graphql_cache",
    "write_pr_cache",
    "write_repo_pr_cache",
]


def _atomic_write_text(path: Path, content: str) -> None:
    """Write *content* to *path* atomically via temp file + os.replace.

    Prevents truncated cache files when the process is interrupted mid-write.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


_CACHE_DIR = get_cache_dir()


def parse_ttl(value: str | int) -> int:
    """Parse a TTL value into seconds.

    Accepts: bare int, string int (e.g. "300"), or suffixed string ("5m", "2h", "30s").
    Raises ValueError for invalid or non-positive values.
    """
    if isinstance(value, bool):
        raise ValueError(f"Invalid TTL: {value!r}")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"TTL must be positive, got {value}")
        return value

    s = str(value).strip()
    if not s:
        raise ValueError("TTL must not be empty")

    if s[-1] in TTL_SUFFIX_MAP:
        suffix = s[-1]
        try:
            n = int(s[:-1])
        except ValueError:
            raise ValueError(f"Invalid TTL: {value!r}")
        if n <= 0:
            raise ValueError(f"TTL must be positive, got {value!r}")
        return n * TTL_SUFFIX_MAP[suffix]

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
    return hashlib.sha256(raw.encode()).hexdigest()[:CACHE_KEY_HEX_CHARS]


def _scoped_path(prefix: str, token: str, *parts: str) -> Path:
    """Return the PR-data file for *parts*, as seen by *token* (#523).

    What GitHub returns depends on the token: a fine-grained token, another
    account or an org without SSO all see different PRs. Hashing the token's
    key into every file name means a cache only ever answers for the token
    that wrote it. Neither the token nor the parts appear in the name.
    """
    raw = ":".join([_token_key(token), *(part.lower() for part in parts)])
    key = hashlib.sha256(raw.encode()).hexdigest()[:CACHE_KEY_HEX_CHARS]
    return _CACHE_DIR / CACHE_SCHEMA_DIR / f"{prefix}_{key}.json"


def cache_path(org: str, repo_filter: str, *, token: str) -> Path:
    return _scoped_path("prs", token, org, repo_filter)


def graphql_cache_path(org: str, repo_filter: str, *, token: str) -> Path:
    return _scoped_path("graphql", token, org, repo_filter)


def read_graphql_cache(
    org: str, repo_filter: str, ttl: int, *, token: str
) -> list | None:
    """Return *token*'s cached PR URL list if present and within TTL, else None."""
    path = graphql_cache_path(org, repo_filter, token=token)
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
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning(
            "cache_read_error layer=graphql path=%s error=%r", path, str(exc)
        )
        click.echo(
            click.style(f"Warning: failed to read GraphQL cache: {exc}", fg="yellow"),
            err=True,
        )
        return None


def write_graphql_cache(org: str, repo_filter: str, urls: list, *, token: str) -> None:
    """Write *token*'s PR URL list to disk cache. Silently ignores write failures."""
    path = graphql_cache_path(org, repo_filter, token=token)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "organization": org,
            "repo_filter": repo_filter,
            "url_count": len(urls),
            "urls": urls,
        }
        _atomic_write_text(path, json.dumps(payload))
        logger.debug("cache_write layer=graphql path=%s url_count=%d", path, len(urls))
    except OSError as exc:
        logger.warning(
            "cache_write_error layer=graphql path=%s error=%r", path, str(exc)
        )
        click.echo(
            click.style(f"Warning: failed to write GraphQL cache: {exc}", fg="yellow"),
            err=True,
        )


class RepositoryNamesCache:
    """Disk cache of an owner's repository names.

    Repositories come and go far less often than PRs, so names are kept for a
    day by default. PR discovery lists names to narrow its searches, and this
    saves listing thousands of repositories on every uncached run.

    One instance answers for one token, the one discovery uses for its owner,
    so a run whose owners use different tokens builds one cache per token.
    """

    def __init__(
        self,
        *,
        token: str,
        ttl: int = REPOSITORY_NAMES_CACHE_TTL,
        refresh: bool = False,
    ):
        """
        Args:
            token: The token discovery lists repositories with; only its
                lists are read or written (#523).
            ttl: Seconds a cached list stays fresh.
            refresh: Ignore cached lists (as ``--refresh`` does) while still
                writing fresh ones.
        """
        self.token = token
        self.ttl = ttl
        self.refresh = refresh

    def path(self, owner: str, include_archived: bool) -> Path:
        mode = "include-archived" if include_archived else ""
        return _scoped_path("repos", self.token, owner, mode)

    def read(self, owner: str, include_archived: bool) -> list | None:
        """Return cached repository names if present and fresh, else None."""
        if self.refresh:
            return None
        path = self.path(owner, include_archived)
        try:
            if not path.exists():
                logger.debug(
                    "cache_miss layer=repos path=%s reason=file_not_found", path
                )
                return None
            data = json.loads(path.read_text())
            fetched_at = datetime.fromisoformat(data["fetched_at"])
            age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
            if age > self.ttl:
                logger.debug(
                    "cache_miss layer=repos path=%s reason=expired age=%.0fs ttl=%ss",
                    path,
                    age,
                    self.ttl,
                )
                return None
            logger.debug(
                "cache_hit layer=repos path=%s age=%.0fs repo_count=%d",
                path,
                age,
                len(data["names"]),
            )
            return data["names"]
        except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            logger.warning(
                "cache_read_error layer=repos path=%s error=%r", path, str(exc)
            )
            return None

    def write(self, owner: str, include_archived: bool, names: list) -> None:
        """Write repository names to disk. Silently ignores write failures."""
        path = self.path(owner, include_archived)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "organization": owner,
                "include_archived": include_archived,
                "repo_count": len(names),
                "names": names,
            }
            _atomic_write_text(path, json.dumps(payload))
            logger.debug(
                "cache_write layer=repos path=%s repo_count=%d", path, len(names)
            )
        except OSError as exc:
            logger.warning(
                "cache_write_error layer=repos path=%s error=%r", path, str(exc)
            )


def read_pr_cache(
    org: str, repo_filter: str, ttl: int, *, token: str, ignore_ttl: bool = False
) -> dict | None:
    """Return *token*'s cached data if present and within TTL, else None.

    If ignore_ttl is True, expired cache data will still be returned on a hit.
    Another token's cache is never returned, however it is asked for.

    On a hit, returns a dict with keys:
      "prs"              – list of PR detail dicts
      "fetched_at"       - ISO string of when cache was fetched
      "check_statuses"   – dict[int, str] or None (absent from older caches)
      "approval_statuses"– dict[int, str] or None (absent from older caches)
      "approval_details" – dict[int, dict] or None (absent from older caches)
    """
    path = cache_path(org, repo_filter, token=token)
    try:
        if not path.exists():
            logger.debug(
                "cache_miss layer=pr_detail path=%s reason=file_not_found", path
            )
            return None
        data = json.loads(path.read_text())
        fetched_at = datetime.fromisoformat(data["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        if not ignore_ttl and age > ttl:
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
            "fetched_at": data["fetched_at"],
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
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning(
            "cache_read_error layer=pr_detail path=%s error=%r", path, str(exc)
        )
        click.echo(
            click.style(f"Warning: failed to read PR cache: {exc}", fg="yellow"),
            err=True,
        )
        return None


def repo_pr_cache_path(org: str, repo_name: str, *, token: str) -> Path:
    return _scoped_path("pr_repo", token, org, repo_name)


def read_repo_pr_cache(
    org: str, repo_name: str, ttl: int, *, token: str
) -> dict | None:
    """Return *token*'s cached PR details for one repo, or None on miss/expiry."""
    path = repo_pr_cache_path(org, repo_name, token=token)
    try:
        if not path.exists():
            logger.debug("cache_miss layer=repo_pr path=%s reason=file_not_found", path)
            return None
        data = json.loads(path.read_text())
        fetched_at = datetime.fromisoformat(data["fetched_at"])
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        if age > ttl:
            logger.debug(
                "cache_miss layer=repo_pr path=%s reason=expired age=%.0fs ttl=%ss",
                path,
                age,
                ttl,
            )
            return None
        raw_checks = data.get("check_statuses")
        raw_approvals = data.get("approval_statuses")
        raw_approval_details = data.get("approval_details")
        logger.debug(
            "cache_hit layer=repo_pr path=%s age=%.0fs pr_count=%d",
            path,
            age,
            len(data["prs"]),
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
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning(
            "cache_read_error layer=repo_pr path=%s error=%r", path, str(exc)
        )
        click.echo(
            click.style(f"Warning: failed to read repo PR cache: {exc}", fg="yellow"),
            err=True,
        )
        return None


def write_repo_pr_cache(
    org: str,
    repo_name: str,
    pr_details: list,
    check_statuses: dict | None = None,
    approval_statuses: dict | None = None,
    approval_details: dict | None = None,
    *,
    token: str,
) -> None:
    """Write *token*'s PR details for a single repo to disk cache."""
    path = repo_pr_cache_path(org, repo_name, token=token)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "organization": org,
            "repo": repo_name,
            "pr_count": len(pr_details),
            "prs": pr_details,
        }
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
        _atomic_write_text(path, json.dumps(payload))
        logger.debug(
            "cache_write layer=repo_pr path=%s pr_count=%d", path, len(pr_details)
        )
    except OSError as exc:
        logger.warning(
            "cache_write_error layer=repo_pr path=%s error=%r", path, str(exc)
        )
        click.echo(
            click.style(f"Warning: failed to write repo PR cache: {exc}", fg="yellow"),
            err=True,
        )


def _token_key(token: str) -> str:
    """Return the key a token's login is filed under; never the token itself."""
    return hashlib.sha256(token.encode()).hexdigest()[:CACHE_KEY_HEX_CHARS]


def _read_cached_logins() -> dict[str, str]:
    """Return user.json's token-key to login table, or {} if absent or unusable.

    A file from before logins were kept per token holds a bare ``login`` and
    no ``logins`` table. It cannot say whose login it is, so it reads as empty
    and the next live lookup replaces it.
    """
    path = _CACHE_DIR / USER_LOGIN_CACHE_FILE
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("cache_read_error layer=user_login error=%r", str(exc))
        return {}
    logins = data.get("logins") if isinstance(data, dict) else None
    if not isinstance(logins, dict):
        return {}
    return {k: v for k, v in logins.items() if isinstance(v, str) and v}


def read_cached_user_login(token: str | None) -> str | None:
    """Return the login last looked up live with *token*, or None.

    Only *token*'s own entry is ever returned, so switching tokens can make
    an offline run skip ``--mine-only`` with a warning, but never filter by
    another account's login.
    """
    if not token:
        return None
    return _read_cached_logins().get(_token_key(token))


def write_cached_user_login(token: str | None, login: str) -> None:
    """Record *login* for *token* in user.json, keeping other tokens' entries."""
    if not token:
        return
    logins = _read_cached_logins()
    logins[_token_key(token)] = login
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / USER_LOGIN_CACHE_FILE
        _atomic_write_text(path, json.dumps({"logins": logins}))
        logger.debug("cache_write layer=user_login login=%s", login)
    except OSError as exc:
        logger.warning("cache_write_error layer=user_login error=%r", str(exc))


def write_pr_cache(
    org: str,
    repo_filter: str,
    pr_details: list,
    check_statuses: dict | None = None,
    approval_statuses: dict | None = None,
    approval_details: dict | None = None,
    *,
    token: str,
) -> None:
    """Write *token*'s pr_details (and optional statuses) to disk cache."""
    path = cache_path(org, repo_filter, token=token)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
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
        _atomic_write_text(path, json.dumps(payload))
        logger.debug(
            "cache_write layer=pr_detail path=%s pr_count=%d", path, len(pr_details)
        )
    except OSError as exc:
        logger.warning(
            "cache_write_error layer=pr_detail path=%s error=%r", path, str(exc)
        )
        click.echo(
            click.style(f"Warning: failed to write PR cache: {exc}", fg="yellow"),
            err=True,
        )


# Exactly the names the unscoped cache used: a prefix, a CACHE_KEY_HEX_CHARS
# key and .json, or the .json.tmp an interrupted write left behind. Nothing
# looser: this deletes files, and the directory also holds user.json and the
# update check's cache, so a broad pattern is one rename away from data loss.
_LEGACY_CACHE_FILE = re.compile(
    rf"^(?:{'|'.join(map(re.escape, LEGACY_CACHE_PREFIXES))})"
    rf"_[0-9a-f]{{{CACHE_KEY_HEX_CHARS}}}\.json(?:\.tmp)?$"
)


def migrate_legacy_cache() -> int:
    """Delete the PR data written before it was scoped per token (#523).

    Those files can hold another token's private PRs, and no current read
    looks at them, so they are removed rather than left to rot. Once they are
    gone there is nothing to match, so this is a one-time cleanup with no
    marker file. ``user.json`` and the update-check cache are left alone.

    Returns:
        How many files were removed. A file that cannot be removed is logged
        and skipped, and the next run tries again.
    """
    try:
        entries = list(_CACHE_DIR.iterdir())
    except OSError:
        return 0
    removed = 0
    for path in entries:
        if not _LEGACY_CACHE_FILE.match(path.name) or not path.is_file():
            continue
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("cache_migrate_error path=%s error=%r", path, str(exc))
            continue
        removed += 1
    logger.debug("cache_migrate removed=%d", removed)
    return removed
