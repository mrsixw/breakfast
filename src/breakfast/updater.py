import json
import re
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

import requests

from .api import SECRET_GITHUB_TOKEN
from .logger import logger
from .xdg import get_cache_dir

_UPDATE_CHECK_REPO = "mrsixw/breakfast"

_CACHE_DIR = get_cache_dir()
_CACHE_TTL_SECONDS = 86400  # 24 hours


def _read_version_cache():
    cache_file = _CACHE_DIR / "latest_version.json"
    try:
        if not cache_file.exists():
            return None
        data = json.loads(cache_file.read_text())
        cached_at = datetime.fromisoformat(data["checked_at"])
        age = (datetime.now(timezone.utc) - cached_at).total_seconds()
        if age > _CACHE_TTL_SECONDS:
            return None
        return data.get("latest_version")
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.debug("version_cache_read_error error=%r", str(exc))
        return None


def _read_cached_release_body():
    """Return the cached release body string, or None if absent/expired."""
    cache_file = _CACHE_DIR / "latest_version.json"
    try:
        if not cache_file.exists():
            return None
        data = json.loads(cache_file.read_text())
        cached_at = datetime.fromisoformat(data["checked_at"])
        age = (datetime.now(timezone.utc) - cached_at).total_seconds()
        if age > _CACHE_TTL_SECONDS:
            return None
        return data.get("release_body")
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None


def _write_version_cache(latest_version, release_body=None):
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = _CACHE_DIR / "latest_version.json"
        payload = {
            "latest_version": latest_version,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        if release_body is not None:
            payload["release_body"] = release_body
        cache_file.write_text(json.dumps(payload))
    except OSError as exc:
        logger.debug("version_cache_write_error error=%r", str(exc))


def get_latest_version():
    cached = _read_version_cache()
    if cached:
        return cached
    try:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if SECRET_GITHUB_TOKEN:
            headers["Authorization"] = f"token {SECRET_GITHUB_TOKEN}"
        logger.debug(
            "update_check_request url=%s",
            f"https://api.github.com/repos/{_UPDATE_CHECK_REPO}/releases/latest",
        )
        t0 = time.monotonic()
        resp = requests.get(
            f"https://api.github.com/repos/{_UPDATE_CHECK_REPO}/releases/latest",
            headers=headers,
            timeout=5,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "")
        latest = tag.lstrip("v")
        release_body = data.get("body") or None
        logger.debug(
            "update_check_response status=%d elapsed_ms=%d latest=%s",
            resp.status_code,
            elapsed_ms,
            latest,
        )
        _write_version_cache(latest, release_body=release_body)
        return latest
    except requests.exceptions.RequestException as exc:
        logger.debug("update_check_request_failed error=%r", str(exc))
        return None


def _parse_version_tuple(version_str):
    try:
        parts = []
        for segment in version_str.split("."):
            m = re.match(r"\d+", segment)
            if not m:
                break
            parts.append(int(m.group()))
        return tuple(parts)
    except (ValueError, AttributeError) as exc:
        logger.debug(
            "parse_version_failed version_str=%r error=%r", version_str, str(exc)
        )
        return ()


def get_release_summary(body: str, max_chars: int = 200) -> str:
    """Extract a short human-readable summary from a GitHub release body.

    Picks the first few bullet points, strips Markdown headers and bare URLs,
    and truncates to max_chars.
    """
    if not body:
        return ""
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith(("- ", "* ", "• ")):
            lines.append(stripped)
            if len(lines) >= 3:
                break
    if not lines:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(stripped)
                break
    summary = " ".join(lines)
    summary = re.sub(r"https?://\S+", "", summary).strip()
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1] + "…"
    return summary


def check_for_update(show_summary: bool = False):
    try:
        current = pkg_version("breakfast")
        latest = get_latest_version()
        if not latest:
            return None
        if _parse_version_tuple(latest) > _parse_version_tuple(current):
            msg = (
                f"\U0001f373 A fresh breakfast is ready! "
                f"v{current} → v{latest} "
                f"— update at https://github.com/{_UPDATE_CHECK_REPO}/releases/latest"
            )
            if show_summary:
                body = _read_cached_release_body()
                if body:
                    summary = get_release_summary(body)
                    if summary:
                        msg += f"\n  📋 {summary}"
            return msg
        return None
    except PackageNotFoundError as exc:
        logger.debug("package_not_found error=%r", str(exc))
        return None
