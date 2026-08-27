"""Steps that assert against the frozen fixture repository.

These are the ones that cost real GitHub requests, and the ones whose numbers
must match the inventory table in ``docs/design/testing.md``.
"""

import re

from pytest_bdd import parsers, then

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
