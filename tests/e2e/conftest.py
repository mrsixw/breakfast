"""Fixtures and shared steps for the end-to-end suite.

These tests drive the **built** ``./breakfast`` zipapp as a subprocess. Nothing
here monkeypatches ``breakfast.*`` — if a test needs to, it is a unit test and
belongs in ``tests/``. See ``docs/design/testing.md``.
"""

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, then, when

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


# ── Shared steps ───────────────────────────────────────────────────────────


@given("no GitHub token is set")
def _no_token(cli_env):
    cli_env.pop("GH_TOKEN", None)
    cli_env.pop("GITHUB_TOKEN", None)


@given(parsers.parse('the GitHub token is "{value}"'))
def _bogus_token(cli_env, value):
    cli_env["GH_TOKEN"] = value


@when(parsers.parse("I run `breakfast {args}`"), target_fixture="result")
def _run_with_args(run_breakfast, args):
    return run_breakfast(shlex.split(args))


@then(parsers.parse("the exit code is {code:d}"))
def _exit_code(result, code):
    assert result.returncode == code, f"stderr was:\n{result.stderr}"


@then("stdout is empty")
def _stdout_empty(result):
    assert result.stdout.strip() == "", f"stdout was:\n{result.stdout}"


@then(parsers.parse('stdout contains "{text}"'))
def _stdout_contains(result, text):
    assert text in result.stdout, f"stdout was:\n{result.stdout}"


@then(parsers.parse('stdout does not contain "{text}"'))
def _stdout_lacks(result, text):
    assert (
        text not in result.stdout
    ), f"{text!r} leaked onto stdout, which the shell evaluates:\n{result.stdout}"


@then(parsers.parse('stderr contains "{text}"'))
def _stderr_contains(result, text):
    assert text in result.stderr, f"stderr was:\n{result.stderr}"


@then("stdout is valid JSON", target_fixture="payload")
def _stdout_json(result):
    return json.loads(result.stdout)


@then("stdout reports the version from the VERSION file")
def _version_matches(result):
    expected = (REPO_ROOT / "VERSION").read_text().strip()
    assert result.stdout.strip().endswith(
        expected
    ), f"expected version {expected!r}, stdout was:\n{result.stdout}"


@then("the config file exists in the sandbox")
def _config_written(sandbox):
    path = sandbox["config"] / "breakfast" / "config.toml"
    assert path.is_file(), f"{path} was not created — is XDG_CONFIG_HOME honoured?"


@then("running it again reports that the config already exists")
def _config_idempotent(run_breakfast):
    second = run_breakfast(["--init-config"])
    assert second.returncode == 0
    assert "already exists" in second.stdout, second.stdout


# ── Live-scenario steps ────────────────────────────────────────────────────

# The frozen fixture repo. Its pull requests never change, so scenarios can
# assert exact counts. See docs/design/testing.md.
FIXTURE_INVENTORY = {
    "Open PR with no labels": "open",
    "Open PR labelled bug": "open",
    "Open PR labelled enhancement": "open",
    "Open PR with two labels": "open",
    "Draft PR awaiting work": "open",
    "Second draft PR": "open",
    "Closed without merging": "closed",
    "Merged fixture PR": "closed",
}


@then(parsers.parse("the JSON payload has {count:d} entries"))
def _payload_count(payload, count):
    assert len(payload) == count, [entry.get("title") for entry in payload]


@then("the payload matches the recorded fixture inventory")
def _inventory_canary(payload):
    """Fail loudly here, in one place, if the fixture repo has drifted."""
    seen = {entry["title"] for entry in payload}
    expected = set(FIXTURE_INVENTORY)
    assert seen == expected, (
        "fixture repo drifted from docs/design/testing.md\n"
        f"  unexpected: {sorted(seen - expected)}\n"
        f"  missing:    {sorted(expected - seen)}"
    )


@then(parsers.parse('every entry has the fields "{fields}"'))
def _payload_fields(payload, fields):
    required = [field.strip() for field in fields.split(",")]
    for entry in payload:
        missing = [field for field in required if field not in entry]
        assert not missing, f"{entry.get('title')!r} is missing {missing}"


@then(parsers.parse('the cache directory holds a "{pattern}" file'))
def _cache_file_written(sandbox, pattern):
    cache_dir = sandbox["cache"] / "breakfast"
    matches = list(cache_dir.glob(pattern))
    assert matches, f"no {pattern} in {cache_dir}: {list(cache_dir.iterdir())}"


@then("a second offline run prints byte-identical output")
def _offline_replay(result, run_breakfast):
    replay = run_breakfast(
        [
            "-o",
            "mrsixw:breakfast-fixtures",
            "--cache",
            "--offline",
            "--format",
            "json",
            "--no-colour",
        ]
    )
    assert replay.returncode == 0, replay.stderr
    assert "Offline Mode" in replay.stderr, replay.stderr
    assert replay.stdout == result.stdout


@then(parsers.parse("stderr reports at least {count:d} processed pull requests"))
def _processed_count(result, count):
    match = re.search(r"PRs processed:\s+(\d+)", result.stderr)
    assert match, f"no 'PRs processed' line in:\n{result.stderr}"
    assert int(match.group(1)) >= count
