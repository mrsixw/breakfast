import os
import tomllib
from pathlib import Path

import click


def get_config_dir():
    """Get the XDG-compliant configuration directory."""
    xdg_config = os.getenv("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "breakfast"
    return Path.home() / ".config" / "breakfast"


def load_config(config_path=None):
    if config_path:
        paths = [Path(config_path).expanduser().resolve()]
    else:
        # XDG-compliant pathing prioritized
        config_dir = get_config_dir()
        paths = [
            Path.cwd() / ".breakfast.toml",
            config_dir / "config.toml",
            Path.home() / ".breakfast.toml",
        ]

    merged = {}
    for path in reversed(paths):
        if path.exists():
            with open(path, "rb") as f:
                try:
                    data = tomllib.load(f)
                except Exception as e:
                    msg = f"Warning: Failed to parse config {path}: {e}"
                    click.echo(click.style(msg, fg="yellow"), err=True)
                    continue
            for key, value in data.items():
                if isinstance(value, list) and isinstance(merged.get(key), list):
                    merged[key] = value + merged[key]
                else:
                    merged[key] = value
    return merged


def generate_default_config():
    """Generate a default XDG-compliant config file."""
    config_dir = get_config_dir()
    config_path = config_dir / "config.toml"
    if config_path.exists():
        click.echo(
            click.style(f"Config file already exists at {config_path}", fg="yellow")
        )
        return False

    config_path.parent.mkdir(parents=True, exist_ok=True)
    default_content = """# breakfast configuration file
# Default organization(s) to query
# organization = "my-org"

# Default repo filter (substring match)
# repo-filter = "my-app"

# Authors to always ignore (case-insensitive)
# ignore-author = ["dependabot[bot]", "renovate[bot]"]

# Always show the age column
# age = true

# Always show CI/check status for each PR
# checks = true

# Always show review approval status for each PR
# approvals = true

# Render status cells using "emoji" (default) or "ascii"
# status-style = "emoji"

# Default output format: "table" or "json"
# format = "table"

# Truncate PR titles to this many characters (unset = no truncation)
# max-title-length = 72

# Enable disk cache for PR results (off by default)
# cache = true

# How long to cache PR results (seconds, or use suffix: 5m, 2h)
# cache-ttl = 300
"""
    config_path.write_text(default_content)
    click.echo(click.style(f"Created default config at {config_path}", fg="green"))
    return True


def normalize_ignore_authors(ignore_authors):
    if not ignore_authors:
        return set()
    return {
        author.strip().lower() for author in ignore_authors if author and author.strip()
    }


def filter_pr_details(
    pr_details,
    ignore_authors,
    mine_only=False,
    current_user_login=None,
    filter_state=None,
    filter_check=None,
    filter_approval=None,
    check_statuses=None,
    approval_statuses=None,
):
    ignore_set = normalize_ignore_authors(ignore_authors)
    current_user_login_normalized = (
        current_user_login.lower()
        if mine_only and current_user_login and current_user_login.strip()
        else None
    )
    filtered = []
    for pr_detail in pr_details:
        author_login = pr_detail.get("user", {}).get("login", "")
        author_login_normalized = author_login.lower()

        if author_login_normalized in ignore_set:
            continue
        if (
            current_user_login_normalized
            and author_login_normalized != current_user_login_normalized
        ):
            continue
        if filter_state and pr_detail.get("state", "").lower() not in {
            s.lower() for s in filter_state
        }:
            continue
        if filter_check and check_statuses is not None:
            pr_check = check_statuses.get(pr_detail["id"], "none")
            if pr_check not in filter_check:
                continue
        if filter_approval and approval_statuses is not None:
            pr_approval = approval_statuses.get(pr_detail["id"], "pending")
            if pr_approval not in filter_approval:
                continue

        filtered.append(pr_detail)
    return filtered
