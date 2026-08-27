"""Fixtures for the end-to-end suite.

These tests drive the **built** ``./breakfast`` zipapp as a subprocess. Nothing
here fakes any part of ``breakfast`` — if a test needs to, it is a unit test and
belongs in ``tests/``. See ``docs/design/testing.md``.

Step definitions live in ``steps/``; only fixtures and the collection hook
belong in this file.
"""

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

# These star imports are load-bearing, not laziness. `@given`/`@when`/`@then`
# register a step by injecting a pytest fixture into the *defining* module's
# namespace, under a generated name (`pytestbdd_stepdef_*`). pytest only scans
# conftest and test modules for fixtures, so a step defined in a plain module is
# invisible until its namespace is pulled in here. Replace these with named
# imports and every scenario fails to find its steps.
from .steps.fixture_repo import *  # noqa: F401,F403
from .steps.steps import *  # noqa: F401,F403

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BINARY = REPO_ROOT / "breakfast"

# The zipapp shebang is `#!/usr/bin/env python3`, so PATH is load-bearing.
# Everything else is deliberately withheld: starting from an empty environment
# is what makes the "no token" scenarios trustworthy.
_PASSTHROUGH = ("PATH", "TMPDIR")


def pytest_collection_modifyitems(items):
    """Stamp ``e2e`` on everything here, tagged or not.

    Feature-level ``@e2e`` tags already become markers, but an untagged feature
    file must never leak into ``make test``.
    """
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.e2e)


@dataclass(frozen=True)
class RunResult:
    """One completed ``breakfast`` invocation."""

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


@pytest.fixture(scope="session")
def shiv_root(tmp_path_factory):
    """Extract the zipapp once per session, not once per scenario."""
    return tmp_path_factory.mktemp("shiv-root")


@pytest.fixture(scope="session")
def breakfast_binary():
    """Locate the built zipapp, or skip/fail with something actionable."""
    override = os.environ.get("BREAKFAST_E2E_BINARY")
    path = Path(override).resolve() if override else DEFAULT_BINARY
    if not path.is_file():
        message = f"zipapp not found at {path} — run `make build` first"
        if os.environ.get("BREAKFAST_E2E_REQUIRE"):
            pytest.fail(message)
        pytest.skip(message)
    if not os.access(path, os.X_OK):
        pytest.fail(f"{path} is not executable — `chmod +x` it after download")
    return path


@pytest.fixture
def sandbox(tmp_path):
    """Per-scenario HOME, XDG dirs and cwd."""
    dirs = {n: tmp_path / n for n in ("home", "cache", "config", "state", "cwd")}
    for directory in dirs.values():
        directory.mkdir(parents=True)
    return dirs


@pytest.fixture
def cli_env(sandbox, shiv_root):
    """A hermetic environment for the subprocess."""
    env = {key: os.environ[key] for key in _PASSTHROUGH if key in os.environ}
    env.update(
        # xdg._xdg_override ignores relative paths and falls back to Path.home(),
        # so every one of these must be absolute or the real cache leaks in.
        HOME=str(sandbox["home"]),
        XDG_CACHE_HOME=str(sandbox["cache"]),
        XDG_CONFIG_HOME=str(sandbox["config"]),
        XDG_STATE_HOME=str(sandbox["state"]),
        SHIV_ROOT=str(shiv_root),
        # Otherwise every run hits the releases API and may print a banner.
        BREAKFAST_NO_UPDATE_CHECK="1",
        # renderers uses shutil.get_terminal_size(), which honours COLUMNS; in a
        # pipe without it the table falls back to 80 and starts dropping columns.
        COLUMNS="200",
        LINES="50",
        LC_ALL="C.UTF-8",
        LANG="C.UTF-8",
        PYTHONIOENCODING="utf-8",
        PYTHONUNBUFFERED="1",
        TZ="UTC",
    )
    return env


@pytest.fixture(autouse=True)
def _live_gate(request, cli_env):
    """Give ``live`` scenarios a token, or skip locally and fail in CI."""
    if request.node.get_closest_marker("live") is None:
        return
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        message = "live scenario needs GH_TOKEN or GITHUB_TOKEN"
        if os.environ.get("BREAKFAST_E2E_REQUIRE_LIVE"):
            pytest.fail(message)
        pytest.skip(message)
    cli_env["GH_TOKEN"] = token


@pytest.fixture
def run_breakfast(breakfast_binary, cli_env, sandbox):
    """Run the zipapp and capture its real streams."""

    def _run(args, *, timeout=int(os.environ.get("BREAKFAST_E2E_TIMEOUT", "90"))):
        argv = [str(breakfast_binary), *args]
        try:
            completed = subprocess.run(
                argv,
                cwd=sandbox["cwd"],
                env=cli_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            pytest.fail(
                f"`{shlex.join(argv)}` timed out after {timeout}s\n"
                f"--- stdout ---\n{exc.stdout}\n--- stderr ---\n{exc.stderr}"
            )
        return RunResult(argv, completed.returncode, completed.stdout, completed.stderr)

    return _run
