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

# Default output format: "table" or "json"
# format = "table"

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
):
    ignore_set = normalize_ignore_authors(ignore_authors)
    current_user_login_normalized = (
        current_user_login.lower()
        if mine_only and current_user_login and current_user_login.strip()
        else None
    )

    if not ignore_set and not current_user_login_normalized:
        return pr_details

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
        filtered.append(pr_detail)
    return filtered
