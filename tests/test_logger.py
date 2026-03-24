import logging
from pathlib import Path

import pytest

from breakfast import logger as logger_module


@pytest.fixture(autouse=True)
def reset_logger():
    """Remove all handlers from the breakfast logger after each test."""
    yield
    log = logging.getLogger("breakfast")
    for handler in log.handlers[:]:
        handler.close()
        log.removeHandler(handler)
    log.setLevel(logging.NOTSET)


def test_configure_creates_log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        logger_module, "_get_log_path", lambda: tmp_path / "breakfast" / "breakfast.log"
    )
    logger_module.configure()
    assert (tmp_path / "breakfast" / "breakfast.log").exists()


def test_configure_creates_parent_directory(tmp_path, monkeypatch):
    log_path = tmp_path / "nested" / "dir" / "breakfast.log"
    monkeypatch.setattr(logger_module, "_get_log_path", lambda: log_path)
    logger_module.configure()
    assert log_path.exists()


def test_log_file_overwritten_on_second_configure(tmp_path, monkeypatch):
    log_path = tmp_path / "breakfast.log"
    monkeypatch.setattr(logger_module, "_get_log_path", lambda: log_path)

    # First run
    logger_module.configure()
    logger_module.logger.info("first run message")
    for h in logger_module.logger.handlers:
        h.flush()

    # Reset handlers to simulate a second invocation
    for h in logger_module.logger.handlers[:]:
        h.close()
        logger_module.logger.removeHandler(h)

    # Second run — should overwrite
    logger_module.configure()
    logger_module.logger.info("second run message")
    for h in logger_module.logger.handlers:
        h.flush()

    content = log_path.read_text()
    assert "second run message" in content
    assert "first run message" not in content


def test_log_contains_startup_message(tmp_path, monkeypatch):
    log_path = tmp_path / "breakfast.log"
    monkeypatch.setattr(logger_module, "_get_log_path", lambda: log_path)
    logger_module.configure()
    logger_module.logger.info("startup org=testorg repo_filter='' cache_enabled=False")
    for h in logger_module.logger.handlers:
        h.flush()

    content = log_path.read_text()
    assert "startup" in content
    assert "testorg" in content


def test_configure_silent_on_os_error(monkeypatch):
    """configure() should not raise even if the log file cannot be created."""
    monkeypatch.setattr(
        logger_module, "_get_log_path", lambda: Path("/no/such/path/breakfast.log")
    )
    # Should not raise
    logger_module.configure()


def test_log_format_includes_level_and_timestamp(tmp_path, monkeypatch):
    log_path = tmp_path / "breakfast.log"
    monkeypatch.setattr(logger_module, "_get_log_path", lambda: log_path)
    logger_module.configure()
    logger_module.logger.debug("test_event key=value")
    for h in logger_module.logger.handlers:
        h.flush()

    line = log_path.read_text().strip().splitlines()[0]
    # Expect: "YYYY-MM-DD HH:MM:SS DEBUG   test_event key=value"
    assert "DEBUG" in line
    assert "test_event" in line
    # Timestamp portion: 10 chars date + space + 8 chars time
    assert line[4] == "-"  # YYYY-...
