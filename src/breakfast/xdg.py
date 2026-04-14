import os
from pathlib import Path


def get_cache_dir() -> Path:
    """XDG cache directory: $XDG_CACHE_HOME/breakfast or ~/.cache/breakfast."""
    xdg = os.getenv("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "breakfast"
    return Path.home() / ".cache" / "breakfast"


def get_config_dir() -> Path:
    """XDG config directory: $XDG_CONFIG_HOME/breakfast or ~/.config/breakfast."""
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "breakfast"
    return Path.home() / ".config" / "breakfast"


def get_config_paths() -> list[Path]:
    """Return config file search paths in priority order (highest → lowest).

    Matches the resolution order used by ``load_config`` and ``--show-config``:
      1. ./.breakfast.toml               (current directory)
      2. ~/.config/breakfast/config.toml (XDG default)
      3. ~/.breakfast.toml               (legacy home directory)
    """
    return [
        Path.cwd() / ".breakfast.toml",
        get_config_dir() / "config.toml",
        Path.home() / ".breakfast.toml",
    ]


def get_state_dir() -> Path:
    """XDG state directory: $XDG_STATE_HOME/breakfast or ~/.local/state/breakfast."""
    xdg = os.getenv("XDG_STATE_HOME")
    if xdg:
        return Path(xdg) / "breakfast"
    return Path.home() / ".local" / "state" / "breakfast"
