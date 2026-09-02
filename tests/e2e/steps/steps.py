"""The general step definitions: running the binary, inspecting its streams.

Nothing here knows what a pull request is. Steps that do belong in
``fixture_repo``.
"""

import json
import shlex
from pathlib import Path

from pytest_bdd import given, parsers, then, when

REPO_ROOT = Path(__file__).resolve().parents[3]


@given("no GitHub token is set")
def _no_token(cli_env):
    cli_env.pop("GH_TOKEN", None)
    cli_env.pop("GITHUB_TOKEN", None)


@given(parsers.parse('the GitHub token is "{value}"'))
def _bogus_token(cli_env, value):
    cli_env["GH_TOKEN"] = value


@given(parsers.parse('the config file contains "{line}"'))
def _config_line(sandbox, line):
    """Append one line to the sandbox config, creating it on first use.

    Repeat the step to build up a multi-line file. Use TOML's single-quoted
    literal strings for values, so the Gherkin double quotes stay unambiguous.
    """
    path = sandbox["config"] / "breakfast" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


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


# ── Cache directory ────────────────────────────────────────────────────────


@given("the cache directory is empty")
def _cache_dir_empty(sandbox):
    """Prove the cache is cold before a scenario claims a run warmed it.

    Without this, "the cache directory holds a prs_*.json file" passes whether
    or not the run under test wrote anything — a stale file, or a sandbox
    fixture that stopped isolating, would both go unnoticed.
    """
    cache_dir = sandbox["cache"] / "breakfast"
    leftovers = (
        sorted(p.name for p in cache_dir.glob("*.json")) if cache_dir.is_dir() else []
    )
    assert not leftovers, f"cache was not cold, {cache_dir} already held: {leftovers}"


@then(parsers.parse('the cache directory holds a "{pattern}" file'))
def _cache_file_written(sandbox, pattern):
    cache_dir = sandbox["cache"] / "breakfast"
    matches = list(cache_dir.glob(pattern))
    assert matches, f"no {pattern} in {cache_dir}: {list(cache_dir.iterdir())}"
