# breakfast Blueprint

## System Overview

breakfast is a Python and Click CLI that lists open GitHub pull requests across
one or more owners (orgs or users). It prints them as a terminal table, or as
Markdown, CSV, JSON, a format template, or a per-author or per-repo summary. It
is shipped as a single shiv zipapp (`./breakfast`, built by `make build`).

User-facing documentation is in [README.md](./README.md) and
[docs/manual/](./docs/manual/README.md). Design records are in
[docs/design/](./docs/design/README.md). This file is the architectural
contract for code directories only.

Run order of the main command (`cli.py:breakfast`):

```text
subcommand? ──yes──► completions / update  (no config, no token)
   │ no
early exits: --colour-diagnostics, --search regex check, --init-config, --update-config
   ▼
load_config ──► merge CLI flags with TOML ──► validation exits ──► --show-config exit
   ▼
guards: --no-drafts/--drafts-only conflict ──► owner ──► token
   ▼
[--mine-only / --needs-my-review] REST /user  (or user.json when offline)
   ▼
Layer 1  full PR cache ── hit ──────────────────────────────────────────┐
   ▼ miss                                                               │
Layer 2  GraphQL URL-list cache ── miss ──► api.get_github_prs         │
         (repo-name listing, then GraphQL search)                       │
   ▼                                                                    │
drop --exclude-repo URLs                                                │
   ▼                                                                    │
Layer 2.5 per-repo PR cache ── miss ──► REST PR detail (+ REST checks)  │
   ▼                                                                    │
approvals: batched GraphQL reviews (REST fallback per PR)               │
   ▼                                                                    │
statuses for cache hits (REST checks, approvals) ◄──────────────────────┘
   ▼
config.filter_pr_details ──► sort ──► --legendary-only ──► --limit
   ▼
renderers / ui ──► stdout        progress, warnings, errors ──► stderr
   ▼
finish_run: update check, easter eggs, --api-stats
```

## Subdirectories & System Boundaries

- src: [./src/EGM.md](./src/EGM.md) - Package source root.
  - src/breakfast: [./src/breakfast/EGM.md](./src/breakfast/EGM.md) - The CLI:
    entry point and orchestration, GitHub API layer, disk cache, config and
    filters, renderers, terminal UI, self-updater, and XDG and logging
    support.
- utils: [./utils/EGM.md](./utils/EGM.md) - Scripts for building, releasing
  and maintenance:
  - CI release: version bump, release creation, binary version check,
    next-version report, git-mkver install, reading `VERSION`.
  - Makefile helpers: the shiv preamble and man pages.
  - Manual tools: the render benchmark and the fixture repo provisioner.

Not covered by contracts: `tests/` (pytest, bats and the e2e suites),
`docs/` (prose), and generated output (`build/`, `completions/`, `man1/`).

## Global Invariants

- **Streams:** PR data, `--show-config` and colour diagnostics go to stdout.
  Progress, warnings and errors go to stderr (`ui.py:emit_progress`,
  `ui.py:error_exit`, `click.echo(err=True)`). Known exception: the
  `--init-config` and `--update-config` messages, including errors, go to
  stdout (`config.py`).
- **Guards before network:** subcommands return before any config or token
  handling (`cli.py:breakfast`). The PR listing exits 1 if the owner or the
  token is missing, before any GitHub request.
- **Exit codes:**
  - 0 on success and for the informational exits (`--show-config`,
    `--init-config`, `--colour-diagnostics`, and `--update-config`, which
    exits 0 even when the update fails).
  - 1 for validation, config, GitHub API and offline-without-cache errors.
  - 2 for Click usage errors (bad choice or range, unknown option).
- **Module API contract:** every module in `src/breakfast/` except the empty
  `__init__.py` declares `__all__`, and names with a leading `_` are private.
  `tests/test_public_api.py` checks that `__all__` is present and valid and
  that no module imports another's private names. `constants.py` holding only
  data is a convention; the test does not check it.
- **Cache safety:**
  - The PR caches are opt-in. Only `user.json` and the update-check
    `latest_version.json` are written without `--cache`.
  - Every `cache.py` write is atomic (temp file, then `os.replace`). The
    update-check cache write is not.
  - Data from offline mode or a network fallback is never written back as
    fresh.
- **Versioning:** `VERSION` is set by `git mkver` from Conventional Commit
  messages (`mkver.conf`). When the release tag already exists, CI runs
  `git mkver patch` (`utils/bump_version_if_tag_exists.sh`). That writes the
  next computed version (`{Next}`), which may be a minor or major bump, not
  only a patch.

## Global Side Effects

- **GitHub:** `api.github.com` REST and GraphQL, authenticated with
  `GH_TOKEN` or `GITHUB_TOKEN`.
- **Releases and self-update:** release lookup at
  `api.github.com/repos/mrsixw/breakfast/releases/latest`; binary download from
  `github.com/mrsixw/breakfast/releases`.
- **XDG directories:**
  - cache: `$XDG_CACHE_HOME/breakfast` (PR caches, `user.json`,
    `latest_version.json`);
  - config: `$XDG_CONFIG_HOME/breakfast/config.toml`, plus `./.breakfast.toml`
    and `~/.breakfast.toml`;
  - state: `$XDG_STATE_HOME/breakfast` (`breakfast.log`, holiday-gift markers).
- **CI only:** git commits and pushes for version bumps, GitHub releases and
  tags.
- **Manual only:** archive and unarchive of the frozen `mrsixw/breakfast-fixtures`
  repo (`utils/setup_fixture_org.sh`).

## System Verification

- Run: `make test` (every test in `tests/` except the `e2e` marker)
- Run: `make bats` (shell scripts)
- Run: `make lint` (ruff, black, markdownlint, shellcheck, typos)
- Run: `make e2e` (built binary against real GitHub)
