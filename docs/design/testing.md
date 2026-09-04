# Testing Strategy

How breakfast is tested, and — more usefully — which layer a new test belongs in.

## The layers

| Layer | Location | Runs the binary? | Network? | Command |
| --- | --- | --- | --- | --- |
| Unit | `tests/test_*.py` | no | no | `make test` |
| CLI | `tests/test_cli.py` | no (in-process `CliRunner`) | no (faked) | `make test` |
| Shell | `tests/bats/` | n/a — it tests the *scripts* | no (stubbed) | `make bats` |
| End-to-end | `tests/e2e/` | **yes**, the built zipapp as a subprocess | **yes**, real GitHub | `make e2e` |

### The rule

**If it fakes any part of the system under test, it is a unit test.** It belongs
in `tests/`, not `tests/e2e/`.

Faking means `monkeypatch`, but equally `requests-mock`, `freezegun` or
`CliRunner` — each replaces something this layer exists to exercise for real:
the network, the clock, the process boundary.

The distinction was lost once already, which is why it is written down rather
than assumed. See [#99](https://github.com/mrsixw/breakfast/issues/99).

### What end-to-end buys that the other layers cannot

- Real process exit codes, not `Result.exit_code`.
- Genuinely separate stdout and stderr, so the project's stream discipline is
  actually testable.
- The **shiv zipapp itself** — packaging, the `utils/preamble.py` Python-version
  guard, the console entry point.
- Real files on disk: the cache, and `--init-config` output.
- Cross-process behaviour: one run writes the cache, the next reads it.
- Real HTTP: auth headers, pagination, retries, rate-limit handling — all of
  `api.py` that the mocked layer replaces wholesale.

## Running them

```bash
make test      # unit + CLI. Offline, fast. e2e is excluded by default.
make bats      # the shell scripts. Offline, fast.
make e2e       # builds the zipapp, then runs everything in tests/e2e
make e2e-ci    # CI variant: uses an already-built binary, fails instead of skipping

uv run pytest -v -m "e2e and not live" tests/e2e   # offline e2e subset
```

`make test` stays offline because `addopts = "-m 'not e2e'"` in
`pyproject.toml`. A bare `uv run pytest` inherits that. `make e2e` passes
`-m e2e` on the command line, which overrides it.

### Skips versus failures

Locally, a missing zipapp or token **skips** with an actionable message. In CI,
`BREAKFAST_E2E_REQUIRE` and `BREAKFAST_E2E_REQUIRE_LIVE` turn both into hard
failures, so the suite cannot quietly rot to green.

| Variable | Effect |
| --- | --- |
| `BREAKFAST_E2E_BINARY` | Path to the zipapp under test (default: `./breakfast`) |
| `BREAKFAST_E2E_REQUIRE` | Fail rather than skip when the zipapp is missing |
| `BREAKFAST_E2E_REQUIRE_LIVE` | Fail rather than skip when no token is set |
| `BREAKFAST_E2E_TIMEOUT` | Per-invocation subprocess timeout in seconds (default 90) |

## The shell layer

Python is not the only thing this repository ships. `install.sh` is the
published `curl | bash` install path, and `utils/` holds the scripts that cut
releases and provision the end-to-end fixtures. They went untested for as long
as they did because `tests/` is a pytest suite and has no way to harness a shell
script — see [#466](https://github.com/mrsixw/breakfast/issues/466).

[bats](https://github.com/bats-core/bats-core) fills that gap, and
[shellcheck](https://www.shellcheck.net) covers the static half. Both arrive
through `npx`, exactly as `markdownlint-cli2` does, so there is nothing to
install by hand:

```bash
make bats        # the shell test suite
make shellcheck  # static analysis (also part of `make lint`)
```

### How the scripts are driven

Each test runs the **real script as a subprocess** with its collaborators — `gh`,
`git`, `curl`, `tar`, `install` — replaced by stubs on `PATH`, and with `HOME`
redirected into the test's temporary directory. Nothing reaches the network, and
an installer test cannot scribble on the machine running it.

`tests/bats/helpers/common.bash` provides the machinery: `stub` writes an
executable that records its arguments before running a body, so a test can
assert *what the script asked for* rather than only what it printed.

Two helpers are worth knowing about:

- **`helpers/fake_gh`** is a stateful fake rather than a stub. The fixture
  provisioner reads its own writes — it reconciles a pull request, then counts
  the inventory to check the result — so a fake that logged mutations without
  applying them would let a broken reconcile loop still pass verification.
- **`helpers/run_pty.py`** runs a script on a real pseudo-terminal. Anything
  that gates on `[[ -t 0 ]]` and prompts with `read` cannot be tested through a
  pipe, and `script(1)` takes incompatible arguments on macOS and Linux.
  Python's `pty` module behaves the same on both.

### By the project's own rule, this is a unit layer

It fakes part of the system under test, so it belongs in `tests/`, not
`tests/e2e/`. The scripts it covers mostly *cannot* be exercised for real
without cutting a release or writing to the frozen fixture repository, which is
precisely why the stubs earn their place here.

## Why the tests are written in Gherkin

`tests/e2e/` uses [pytest-bdd](https://pytest-bdd.readthedocs.io/). The
`.feature` files describe behaviour in terms of what a user runs and what they
see, which suits a layer whose entire subject is observable CLI behaviour. It
also makes the boundary unmistakable: nothing in `tests/e2e/` looks like the
mocked suites, so the two are hard to confuse again.

The layout:

```text
tests/e2e/
  conftest.py          fixtures and the collection hook, nothing else
  steps/
    steps.py           running the binary, and its streams
    fixture_repo.py    assertions about the frozen fixture repo
  features/            the .feature files
  test_e2e.py          scenarios("features") — binds all of them
```

`scenarios()` walks directories, so **one** binding module covers every feature
file; there is no reason for one per feature.

`conftest.py` is the odd name in that tree, and it is not one we picked —
pytest hardcodes it. It is the only filename pytest loads fixtures and hooks
from without a registered plugin, and what it defines applies to every test in
its directory and below. That is why `pytest_collection_modifyitems` lives
there specifically: hooks come from `conftest.py` and plugins, nowhere else.
Everything that *could* move out already has, which is what the `steps/`
package is.

`conftest.py` ends with `from .steps.… import *`, and those star imports are
load-bearing. `@given`/`@when`/`@then` register a step by injecting a pytest
fixture into the *defining* module's namespace under a generated name
(`pytestbdd_stepdef_*`). pytest only scans conftest and test modules for
fixtures, so a step in a plain module stays invisible until that namespace is
pulled in. Rewrite them as named imports and every scenario loses its steps.

A feature-level tag such as `@e2e` becomes a pytest marker on every scenario in
that file. As a backstop, a `pytest_collection_modifyitems` hook stamps `e2e` on
everything in the directory, so an untagged feature file can never leak into
`make test`.

> **Note on `AGENTS.md`'s "documented APIs, not internals" rule:** pytest-bdd
> reaches into `_pytest` privates. Our own code touches only its public
> `scenario`, `scenarios`, `given`, `when`, `then` and `parsers`. pytest-bdd
> 8.1.0 is verified working against the locked pytest 9.1.1; it does emit a
> `PytestRemovedIn10Warning` about `FixtureDef(baseid=...)`, which will need
> revisiting before pytest 10.

## When to add a scenario

Ask what a unit test **structurally cannot see**. If the answer is "nothing",
the test belongs in `tests/test_cli.py`.

Worth a scenario:

- A new or changed **exit code**, or a new user-facing error path.
- Anything about **stdout versus stderr** — `CliRunner` merges them.
- A new **subcommand**, or a change to how the artifact is packaged or invoked.
- Anything touching **disk** — cache layers, config generation, state files.
- **Ordering** properties, such as a guard firing before any network call.
- A new **output format**, or a change to an existing one's shape.

Not worth one: filter permutations, formatting details, branch coverage. Those
belong in the unit layer, where fixtures are free and no API calls are spent.

Every live scenario costs real GitHub requests, so the suite stays deliberately
small. A scenario that merely repeats what `tests/test_cli.py` already proves is
worse than no scenario — it costs quota and implies coverage it does not add.

If a scenario needs pull-request data the fixture repo does not have, the
**inventory changes** — never the assertion. Adjusting an expected count to
match drifted fixtures destroys the guarantee the whole layer rests on.

## Environment isolation

The subprocess environment is an **allowlist**, not a blocklist: it starts empty
and copies only `PATH` (the zipapp shebang is `#!/usr/bin/env python3`) and
`TMPDIR`. Starting from nothing is what makes the "no token is set" scenarios
trustworthy.

Four traps this closes, each found the hard way:

- **`XDG_*` must be absolute.** `xdg._xdg_override` silently ignores relative
  paths and falls back to `Path.home()` — which would write into your real cache.
- **`COLUMNS` must be pinned.** `renderers` calls `shutil.get_terminal_size()`,
  which honours `COLUMNS`; unset in a pipe it falls back to 80 and the table
  starts *dropping columns*.
- **cwd must be a temp directory.** `xdg.get_config_paths()[0]` is
  `Path.cwd() / ".breakfast.toml"`, so a stray file in the repo root would
  change results.
- **`SHIV_ROOT` is session-scoped.** Otherwise each scenario re-extracts the
  1.3 MB zipapp into a fresh `HOME`.

Also set: `BREAKFAST_NO_UPDATE_CHECK=1` (or every run hits the releases API),
`TZ=UTC` and `LC_ALL=C.UTF-8`.

Assert on stderr with `in`, never equality — `cli.py` emits seasonal easter eggs
on certain dates. They are gated on colour, so `--no-colour` suppresses them.

## The fixture repository

Live scenarios query **`mrsixw/breakfast-fixtures`**, a frozen repository whose
pull requests never change. That is what lets scenarios assert exact counts
rather than vague invariants.

> **Never modify it.** Every count below is asserted in
> `tests/e2e/features/pr_listing.feature`.

| # | Title | State | Draft | Labels |
| --- | --- | --- | --- | --- |
| 1 | Open PR with no labels | open | no | — |
| 2 | Open PR labelled bug | open | no | `bug` |
| 3 | Open PR labelled enhancement | open | no | `enhancement` |
| 4 | Open PR with two labels | open | no | `bug`, `wip` |
| 5 | Draft PR awaiting work | open | yes | — |
| 6 | Second draft PR | open | yes | `enhancement` |
| 7 | Closed without merging | closed | no | — |
| 8 | Merged fixture PR | merged | no | — |

Derived expectations: default (open) **6** · `--no-drafts` **4** ·
`--drafts-only` **2** · `--label bug` **2** · `--exclude-label bug` **4** ·
`--fetch-state all` **8** · `--filter-author mrsixw` **6** ·
`--filter-author octocat` **0** · `--ignore-author mrsixw` **0**.

A **canary scenario** asserts the whole inventory in one place, so drift
produces one obvious failure rather than eight confusing ones.

### Why scoped `-o mrsixw:breakfast-fixtures`

`api.get_github_prs` paginates *every* repository belonging to an owner
(`GRAPHQL_REPOSITORY_PAGE_SIZE = 25`) and applies repo filters client-side
afterwards. `mrsixw` has ~48 repos, so each live scenario costs two GraphQL
pages, rising by one per 25 new repos. The scoped syntax keeps the *result* set
correct; it does not reduce the pagination cost. A dedicated organisation with a
single repository would cost one page permanently — tracked as
[#456](https://github.com/mrsixw/breakfast/issues/456).

The filter is a substring/glob match, and `breakfast` does not contain
`breakfast-fixtures`, so only the fixture repo matches.

### What a single author cannot cover

All fixture PRs are authored by `mrsixw`, so these cannot be *discriminated*
end-to-end: `--filter-reviewer` (you cannot request review from yourself),
`--needs-my-review`, `--filter-approval approved` (you cannot approve your own
PR), and multi-bucket `--summarise-user-prs`.

The suite proves the *wiring* instead, via positive/negative pairs —
`--filter-author mrsixw` → 6 versus `--filter-author octocat` → 0 demonstrates
that the option reaches the filter and the filter reaches the renderer, which is
what end-to-end owes you. Multi-author combinatorics stay in `tests/test_cli.py`,
where fixtures are free.

Adding a `breakfast-fixture-bot` machine account would unlock the rest. It costs
a second credential to manage and is tracked in
[#452](https://github.com/mrsixw/breakfast/issues/452).

### Recreating it from scratch

The inventory is built by [`utils/setup_fixture_org.sh`](../../utils/setup_fixture_org.sh),
not by copy-pasting a recipe out of this document. The script is the executable
form of the table above: it creates the repository, the three labels, the eight
branches and their pull requests, applies the labels, closes fixture 7, merges
fixture 8, and then **verifies** the result really is six open / eight total /
two drafts before it will let you freeze anything.

```bash
# See what it would do, touching nothing.
./utils/setup_fixture_org.sh <org> --dry-run

# Provision for real.
./utils/setup_fixture_org.sh <org>

# Only once `make e2e` is green against the new fixtures:
./utils/setup_fixture_org.sh <org> --archive
```

Three things the script does that a fenced code block could not:

- It **refuses** to seed `mrsixw/breakfast-fixtures`. That repo is frozen and
  asserted by exact count, so the guard is case-insensitive and the only way
  past it is `--update`, which repairs rather than seeds — see below.
- It reads each pull request number back from `gh` instead of assuming they are
  numbered 1 through 8. One stray pull request would otherwise shift every later
  `gh pr edit` onto the wrong target — silently, since the labels would still
  apply cleanly to whatever they hit.
- It refuses to seed a repository that already holds pull requests, so a second
  run cannot quietly double the inventory — and refuses one holding orphaned
  `fixture-*` branches from a half-finished run, because re-pushing those would
  need a force push.

GitHub has no API for creating an organisation, so the organisation itself must
exist before you start — see [organizations/plan](https://github.com/organizations/plan).
The script checks for it and says so rather than failing eight steps later.

Archive **last**, after verifying with `make e2e` — an archived repo is
read-only, so a mistake in the inventory would need unarchiving to fix. That is
why `--archive` is opt-in rather than the default. Settings changes are also
rejected once archived, which is why the flag turns off Dependabot alerts,
issues and the wiki *before* it archives. Archiving makes those largely
redundant anyway (no bot can open a pull request on a read-only repo), but they
cost nothing and document the intent.

Archiving does **not** hide the pull requests: the suite was re-run after
archiving and all 25 scenarios still pass, confirming the GraphQL query has no
`isArchived` filter.

### Repairing the frozen fixtures

Freezing the repository is not the same as never touching it again. If the
inventory ever drifts — a label removed, a draft readied, a fixture deleted —
the same script repairs it in place:

```bash
# See what it would change, touching nothing.
./utils/setup_fixture_org.sh mrsixw --repo breakfast-fixtures --update --dry-run

# Repair for real. Asks you to type UNFREEZE before it unarchives anything.
./utils/setup_fixture_org.sh mrsixw --repo breakfast-fixtures --update
```

`--update` reconciles rather than seeds: for each of the eight fixtures it looks
the pull request up **by title**, creates it if it is missing, and otherwise
corrects its labels, its draft flag and its state until they match the table
above. Nothing already correct is touched, so a run against undrifted fixtures
is a read-only no-op.

The unfreezing is deliberately noisy, because an unfrozen fixture repository is
a live hazard to CI:

- It **asserts the repository is archived** before it starts. Finding it thawed
  means an earlier run never refroze it, and the inventory may have drifted
  while it was writable — so the script stops and tells a human to look.
- It **surveys the live inventory while the repository is still read-only**, and
  refuses to thaw one holding duplicate or undocumented pull requests. Neither
  can be deleted through the API, so discovering them halfway through a repair
  would be the worst of both worlds.
- It prints the exact `gh repo unarchive` command it is about to run, and will
  not run it until you type `UNFREEZE` at an interactive prompt. There is no
  non-interactive escape hatch: with no terminal, it refuses.
- The refreeze hangs off an `EXIT` trap, so it fires on success, on any failure,
  and on Ctrl-C alike. The trap is armed *before* the unarchive request is sent,
  not after it succeeds: a transport failure can still have applied the change
  server-side.
- The trap does not trust `gh repo archive`'s exit status — archiving an already
  archived repository is an error too. It asks the repository what state it is
  actually in, and if that is anything but archived it shouts, prints the manual
  `gh repo archive` command, and **exits 75 even when the repair itself
  succeeded**. A green exit is how a tired human decides it is safe to walk
  away, so an unconfirmed refreeze must never produce one.
- It leaves `main` alone. Update mode only reconciles pull requests; it will not
  rewrite the README of a repository it just unfroze.

One drift it cannot repair: a fixture that has been **merged** when the
inventory says it should be open or closed. A merge cannot be undone through the
API, so the script dies and says the repository must be rebuilt elsewhere.

## Cost and flakiness

Roughly 70 API requests per full live run: each scenario costs ~2 GraphQL
repository pages plus one REST call per pull request. Against 5000/hour that is
comfortable, but note CI triggers on both `push` and `pull_request`, so a branch
push runs it twice.

`--checks` and `--approvals` are deliberately **not** exercised live: both are
per-PR GraphQL and would multiply the cost for little return.

`api.py` already retries `{502, 503, 504}` up to `MAX_RETRIES`, which absorbs
most transient failures; a 90-second subprocess timeout sits on top.
`pytest-rerunfailures` is deliberately **not** used — it converts real breakage
into intermittent noise. A failure should be read, not retried.

## CI

The `e2e` job runs `needs: [build]` and `release` is gated behind it, which is
issue #99's "post-build but before release". It downloads the artifact the
`build` job produced rather than rebuilding, so the bits under test are the bits
that ship.

Two details that will otherwise cost an afternoon:

- Artifacts travel as zips and **do not preserve the executable bit**, hence the
  `chmod +x` step.
- The job uses the built-in `secrets.GITHUB_TOKEN`, which is provided read-only
  to pull requests from forks and can read public repositories. Verified
  sufficient for the live scenarios in CI, so there is **no fork guard** and
  forks run the full suite. If a scenario ever needs `secrets.GH_TOKEN`, a guard
  skipping fork pull requests must come back — `secrets.*` is not exposed to
  them, and the job would fail rather than skip.
