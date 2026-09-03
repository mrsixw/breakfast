# Testing Strategy

How breakfast is tested, and — more usefully — which layer a new test belongs in.

## The layers

| Layer | Location | Runs the binary? | Network? | Command |
| --- | --- | --- | --- | --- |
| Unit | `tests/test_*.py` | no | no | `make test` |
| CLI | `tests/test_cli.py` | no (in-process `CliRunner`) | no (faked) | `make test` |
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
> `scenario`, `scenarios`, `given`, `when`, `then` and `parsers`.

### Why `pytest` is pinned below 10

pytest-bdd 8.1.0 — the latest release — calls
`FixtureManager._register_fixture` and `FixtureDef(baseid=...)`, both of which
pytest 9 already flags as `PytestRemovedIn10Warning`. On pytest 10 the suite
would stop collecting entirely, and because `release` is gated on the `e2e` job
that blocks releases rather than merely failing a test.

Nothing else pins pytest, so `uv` would be free to resolve 10 on any `uv sync`
and the first sign would be a red job on an unrelated pull request. The pin in
the `test` and `dev` extras makes the constraint deliberate instead.

### How everything else is pinned

That pin was the first, and for a while the only one, which made it look
arbitrary. Every dependency now carries a floor and a ceiling:

- **Floor** — the version currently in `uv.lock`, the one actually tested. A
  lock refresh cannot silently resolve backwards to something never exercised.
- **Ceiling** — the next breaking bump. The next major, or the next *minor* for
  0.x projects like `ruff`, `wcwidth`, `tabulate` and `click-man`, where minors
  are where breakage lives.

`uv.lock` already pins exact versions, and CI runs `uv sync`, so installs are
reproducible with or without these ranges. The ranges do a different job: they
bound what `uv lock` may resolve *to* when it is next regenerated. `pytest<10`
is the case that motivated them — a major bump landing on an unrelated pull
request and reading as that change's fault.

The `pytest` ceiling is the one exception to the rule above: it is not "the next
major after the tested version" by coincidence but by necessity, for the
pytest-bdd reason given above.

The trade: ceilings on the four runtime dependencies constrain anyone installing
`breakfast` as a library. For a CLI that ships as a zipapp, bounding what the
released artifact can be built against is worth more than that flexibility.

**Remove the pin** once pytest-bdd ships a release that no longer uses those
APIs. Tracked in [#454](https://github.com/mrsixw/breakfast/issues/454).

The warnings are deliberately **not** filtered. They are the signal that the
upstream fix has landed: when they stop appearing, the pin can go.

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
single repository would cost one page permanently — worth revisiting if the
budget ever tightens.

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
a second credential to manage and is tracked separately.

### Recreating it from scratch

```bash
gh repo create mrsixw/breakfast-fixtures --public \
  --description "Frozen PR fixtures for breakfast's end-to-end suite. Do not modify."
cd "$(mktemp -d)" && gh repo clone mrsixw/breakfast-fixtures && cd breakfast-fixtures

printf '# breakfast-fixtures\n\n> [!WARNING]\n> Frozen fixtures for the breakfast end-to-end suite. Changing anything here\n> breaks CI on mrsixw/breakfast. See docs/design/testing.md in that repo.\n' > README.md
git add README.md && git commit -m "docs: add fixture warning" && git push

gh label create wip --color ededed --force
for l in bug enhancement; do gh label create "$l" --force 2>/dev/null || true; done

# Eight branches, one commit each, then eight PRs.
n=1
for title in \
  "Open PR with no labels" "Open PR labelled bug" \
  "Open PR labelled enhancement" "Open PR with two labels" \
  "Draft PR awaiting work" "Second draft PR" \
  "Closed without merging" "Merged fixture PR"; do
  git checkout -q main && git checkout -q -b "fixture-$n"
  echo "$title" > "fixture-$n.txt"
  git add . && git commit -q -m "$title" && git push -q -u origin "fixture-$n"
  if [ "$n" -eq 5 ] || [ "$n" -eq 6 ]; then
    gh pr create --draft --title "$title" --body "Frozen fixture. Do not modify."
  else
    gh pr create --title "$title" --body "Frozen fixture. Do not modify."
  fi
  n=$((n+1))
done

gh pr edit 2 --add-label bug
gh pr edit 3 --add-label enhancement
gh pr edit 4 --add-label bug --add-label wip
gh pr edit 6 --add-label enhancement
gh pr close 7
gh pr merge 8 --merge

# Freeze it. Archiving is the strongest lock available: archived repos are
# read-only and accept no new PRs, but existing ones stay queryable — the
# GraphQL query has no isArchived filter.
gh api -X DELETE repos/mrsixw/breakfast-fixtures/vulnerability-alerts
gh repo edit mrsixw/breakfast-fixtures --enable-issues=false --enable-wiki=false
gh repo archive mrsixw/breakfast-fixtures --yes
```

Archive **last**, after verifying with `make e2e` — an archived repo is
read-only, so a mistake in the inventory would need unarchiving to fix. Settings
changes are also rejected once archived, which is why the Dependabot and
issues/wiki steps come first. Archiving makes those largely redundant anyway (no
bot can open a pull request on a read-only repo), but they cost nothing and
document the intent.

Archiving does **not** hide the pull requests: the suite was re-run after
archiving and all 25 scenarios still pass, confirming the GraphQL query has no
`isArchived` filter.

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
