import os
from pathlib import Path


def _xdg_override(env_var: str) -> Path | None:
    """Return ``Path($env_var)`` only if it is set to an absolute path.

    Per the XDG Base Directory Specification, relative paths in
    ``$XDG_*_HOME`` variables must be considered invalid and ignored.
    """
    value = os.getenv(env_var)
    if value and Path(value).is_absolute():
        return Path(value)
    return None


def get_cache_dir() -> Path:
    """XDG cache directory: $XDG_CACHE_HOME/breakfast or ~/.cache/breakfast."""
    override = _xdg_override("XDG_CACHE_HOME")
    if override is not None:
        return override / "breakfast"
    return Path.home() / ".cache" / "breakfast"


def get_config_dir() -> Path:
    """XDG config directory: $XDG_CONFIG_HOME/breakfast or ~/.config/breakfast."""
    override = _xdg_override("XDG_CONFIG_HOME")
    if override is not None:
        return override / "breakfast"
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
    override = _xdg_override("XDG_STATE_HOME")
    if override is not None:
        return override / "breakfast"
    return Path.home() / ".local" / "state" / "breakfast"
