import json
import os
import time
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

import requests

from .api import SECRET_GITHUB_TOKEN
from .logger import logger

_UPDATE_CHECK_REPO = "mrsixw/breakfast"


def _get_cache_dir():
    """Get the XDG-compliant cache directory."""
    xdg_cache = os.getenv("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache) / "breakfast"
    return Path.home() / ".cache" / "breakfast"


_CACHE_DIR = _get_cache_dir()
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
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.debug("version_cache_read_error error=%r", str(exc))
        return None


def _write_version_cache(latest_version):
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = _CACHE_DIR / "latest_version.json"
        cache_file.write_text(
            json.dumps(
                {
                    "latest_version": latest_version,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
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
        tag = resp.json().get("tag_name", "")
        latest = tag.lstrip("v")
        logger.debug(
            "update_check_response status=%d elapsed_ms=%d latest=%s",
            resp.status_code,
            elapsed_ms,
            latest,
        )
        _write_version_cache(latest)
        return latest
    except requests.exceptions.RequestException as exc:
        logger.debug("update_check_request_failed error=%r", str(exc))
        return None


def _parse_version_tuple(version_str):
    try:
        return tuple(int(x) for x in version_str.split("."))
    except (ValueError, AttributeError) as exc:
        logger.debug(
            "parse_version_failed version_str=%r error=%r", version_str, str(exc)
        )
        return ()


def check_for_update():
    try:
        current = pkg_version("breakfast")
        latest = get_latest_version()
        if not latest:
            return None
        if _parse_version_tuple(latest) > _parse_version_tuple(current):
            return (
                f"🍳 A fresh breakfast is ready! "
                f"v{current} → v{latest} "
                f"— update at https://github.com/{_UPDATE_CHECK_REPO}/releases/latest"
            )
        return None
    except PackageNotFoundError as exc:
        logger.debug("package_not_found error=%r", str(exc))
        return None
