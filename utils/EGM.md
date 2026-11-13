# utils

## Overview

Build, release and maintenance helpers for breakfast:

- **CI release pipeline:** six scripts run by `.github/workflows/ci.yml` in
  the `build`, `version` and `release` jobs.
- **Makefile helpers:** the shiv preamble and man page generation.
- **Manual tools:** a render benchmark, and a provisioner for the frozen
  end-to-end fixture repo.

None of these scripts is part of the `breakfast` Python package. However,
`preamble.py` is built into the release zipapp (`shiv --preamble`).

Citation convention: most of these are top-level shell scripts with no named
symbols, so the script path itself is the citation unit. Where a script does
define named functions, they are cited as `script:function` (for example
`setup_fixture_org.sh:survey_inventory`).

## Interface

| Script | Purpose | Invoked by |
| --- | --- | --- |
| `bump_version_if_tag_exists.sh <version>` | If tag `v<version>` already exists: `git mkver patch`, `uv lock`, commit `chore: bump version to <version>`, push; print the version in effect | CI `release` job |
| `check_binary_version.sh` | Check that `./breakfast --version` matches `VERSION` | CI `build` job |
| `create_release.sh <version>` | `gh release create v<version> --title v<version>` with the binary, man page and completions, `--generate-notes`, targeted at HEAD | CI `release` job |
| `install_git_mkver.sh` | Download the latest linux-x86_64 `git-mkver` to `/usr/local/bin` | CI `version` and `release` jobs |
| `report_next_version.sh` | Print the current version and the version `git mkver next` would release; warn on a MAJOR bump; write to `$GITHUB_STEP_SUMMARY` when set | CI `version` job |
| `read_version.py` | Print `./VERSION` | CI `release` job; `bump_version_if_tag_exists.sh`; `check_binary_version.sh` |
| `preamble.py` | shiv preamble: exit 1 on Python older than 3.11 | `make build` |
| `generate_man_page.py [TARGET_DIR]` | Write click-man pages (default `man1`) | `make man` |
| `bench_render.py` | Benchmark table auto-fit and rendering at several sizes | Manual (`uv run python utils/bench_render.py`) |
| `setup_fixture_org.sh <org> [--repo NAME] [--update] [--dry-run] [--archive] [-h]` | Seed, or reconcile, the 8-PR end-to-end fixture repo | Manual |

`utils/vhs/demo.tape` is a VHS recording script for the demo GIF, not code.

## Invariants

- Every `.sh` script runs under `set -euo pipefail` and is checked by `make
  shellcheck`, which is part of `make lint`.
- `bump_version_if_tag_exists.sh`:
  - Bumps only when `refs/tags/v<version>` exists; otherwise prints the version
    unchanged.
  - Finds the branch from `git symbolic-ref`, then `GITHUB_HEAD_REF`, then
    `GITHUB_REF_NAME`. Exits 1 if it finds none, or if the push fails.
  - The `release` job skips commits whose message starts with
    `chore: bump version`, so a bump does not release twice.
- `create_release.sh` always tags `v<version>` at the exact HEAD SHA.
- `check_binary_version.sh` exits 1 with `Version mismatch` when the binary's
  version and `VERSION` differ.
- `install_git_mkver.sh` exits non-zero with
  `No suitable git-mkver asset found` when there is no linux-x86_64 tarball.
- `report_next_version.sh` exits 1 if `VERSION` is missing, if `git mkver next`
  fails, or if its output has no `X.Y.Z` version. A MAJOR bump only produces a
  warning. `VERSION_FILE` can be overridden for bats tests.
- `setup_fixture_org.sh`:
  - Rejects unknown options and extra positional arguments.
  - Refuses to seed `mrsixw/breakfast-fixtures` (matched case-insensitively)
    unless `--update` is given.
  - Seed mode requires the org to exist, and refuses a repo that already has
    PRs or leftover `fixture-*` branches.
  - `--update` (which implies `--archive`) requires the repo to exist, be
    archived and pass `survey_inventory` (no duplicate or stray PRs). Outside
    `--dry-run` it also requires a TTY and the typed word `UNFREEZE`.
  - Dies if a `gh pr list` lookup fails (instead of creating a duplicate PR),
    or if a fixture that must not be merged has been merged.
  - The `EXIT` trap always tries to re-archive a repo it unarchived. If it
    cannot confirm the re-archive, it turns a successful exit into 75. A
    failure exit code is kept as it is.
  - INT and TERM exit with 130 and 143.
  - The final check requires 6 open, 8 total and 2 draft PRs.
  - Never force-pushes. `--dry-run` echoes the commands that would change
    something instead of running them, but still creates and removes a local
    `mktemp` directory.

## Side Effects

- **Git:** `bump_version_if_tag_exists.sh` sets the local `git config`
  user to `github-actions[bot]`, rewrites `VERSION` and `uv.lock`, then commits
  and pushes.
- **GitHub:**
  - `create_release.sh` creates the GitHub release and tag and uploads assets.
    CI provides `GITHUB_TOKEN`.
  - `setup_fixture_org.sh` uses `gh` to create or edit the repo, labels and
    PRs (create, edit, ready, reopen, close, merge). It uses `git
    clone`/`commit`/`push` for the `fixture-N` branches and, in seed mode, a
    README on `main`.
  - In seed mode, `--archive` also deletes vulnerability alerts, turns off
    issues and the wiki, and archives the repo. `--update` unarchives the repo
    and re-archives it afterwards.
- **Downloads and installs:** `install_git_mkver.sh` calls the GitHub API,
  sending `GITHUB_TOKEN` as a Bearer token when it is set. It downloads to
  `/tmp/git-mkver.tar.gz`, extracts in `/tmp`, and installs
  `/usr/local/bin/git-mkver`.
- **Files:** `generate_man_page.py` writes man pages to `TARGET_DIR`.
  `report_next_version.sh` appends to `$GITHUB_STEP_SUMMARY`.
- **In-process only:** `bench_render.py` temporarily patches
  `breakfast.cli.tabulate` and writes nothing.

## Verification

- Run: `make bats` (shell script tests in `tests/bats/`)
- Run: `make shellcheck`
