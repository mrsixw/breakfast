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


def get_state_dir() -> Path:
    """XDG state directory: $XDG_STATE_HOME/breakfast or ~/.local/state/breakfast."""
    xdg = os.getenv("XDG_STATE_HOME")
    if xdg:
        return Path(xdg) / "breakfast"
    return Path.home() / ".local" / "state" / "breakfast"
