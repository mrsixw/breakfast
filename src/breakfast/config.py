import tomllib
from pathlib import Path

import click


def load_config(config_path=None):
    if config_path:
        paths = [Path(config_path)]
    else:
        paths = [
            Path(".breakfast.toml"),
            Path.home() / ".config" / "breakfast" / "config.toml",
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
