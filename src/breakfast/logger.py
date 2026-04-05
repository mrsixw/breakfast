import logging
from pathlib import Path

from .xdg import get_state_dir

_LOG_FILENAME = "breakfast.log"


def _get_log_path() -> Path:
    return get_state_dir() / _LOG_FILENAME


logger = logging.getLogger("breakfast")


def configure() -> None:
    """Configure file logging for the current invocation.

    Opens the log file in write mode so each run starts with a fresh log.
    The cache directory is created if it does not already exist.
    Silently does nothing if the log file cannot be opened.
    """
    log_path = _get_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    except OSError:
        pass
