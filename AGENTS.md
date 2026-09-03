# Agent Instructions

## Project Overview
- **breakfast** is a CLI tool that displays open GitHub pull requests across an organization's repos in a terminal table.
- Built with Python and Click. Uses the GitHub REST and GraphQL APIs.
- Package structure: code in `src/breakfast/`, tests in `tests/`.
- The name is tongue-in-cheek: breakfast is the first thing you consume each morning, and open PRs are the first thing you should consume at the start of your workday.

## Project Structure
- `src/breakfast/` — package source code
  - `cli.py` — Click command definition and entry point
  - `renderers.py` — Output formatters and table fitting
  - `api.py` — GitHub API interaction logic
  - `config.py` — TOML configuration and filtering
  - `ui.py` — Terminal formatting and progress emojis
  - `updater.py` — Version checking and caching
  - `cache.py` — HTTP response caching
  - `logger.py` — Logging configuration
  - `xdg.py` — XDG base directory support
- `tests/` — module-specific pytest suite
- `pyproject.toml` — project metadata, dependencies, tool config
- `VERSION` — static file containing the current version string
- `Makefile` — build, test, lint, and format targets
- `utils/` — helper scripts for release management
- `mkver.conf` — version bump configuration
- `docs/` — project documentation
  - `docs/manual/` — user-facing manual (installation, usage, options, output formats, troubleshooting)
  - `docs/design/` — technical design documents for planned features

## Agent Instruction Files
`AGENTS.md` is the single source of truth. `CLAUDE.md`, `GEMINI.md` and
`.github/copilot-instructions.md` are symlinks to it, so there is one file to
edit and drift between them is impossible.

- `AGENTS.md` — canonical. Read natively by Codex and most other agents
- `CLAUDE.md` → symlink — Claude Code
- `GEMINI.md` → symlink — Gemini
- `.github/copilot-instructions.md` → symlink — GitHub Copilot

`AGENTS.md` is the canonical file because Codex, Copilot and others read that
name natively, and it is the emerging cross-tool convention. The three tools
that insist on their own filename get a symlink instead of a copy.

On Windows, git checks symlinks out as plain text files containing the target
path unless `core.symlinks=true` and Developer Mode are both enabled.

## Environment
- Python >= 3.11
- Package manager: **uv** (not pip). Use `uv sync`, `uv run`, etc.
- Requires `GITHUB_TOKEN` environment variable at runtime.

## Common Commands
- `make test` — run tests (`uv run pytest -v`)
- `make lint` — check linting and formatting (`ruff check` + `black --check`)
- `make format` — auto-fix lint and formatting (`ruff check --fix` + `black`)
- `make build` — build a shiv executable

## Testing
- **Three layers, and the rule that separates them** (see [docs/design/testing.md](docs/design/testing.md)):
  - Unit and CLI tests (`tests/*.py`) use `pytest` with `monkeypatch`, `requests-mock`, `freezegun` and `click.testing.CliRunner`. Offline and fast. `make test`.
  - End-to-end tests (`tests/e2e/`) are pytest-bdd `.feature` files that drive the **built `./breakfast` zipapp as a subprocess** against real GitHub. `make e2e`. **Never mocked.**
  - **If it fakes any part of the system under test, it is a unit test** — `monkeypatch`, `requests-mock`, `freezegun` and `CliRunner` all replace something the end-to-end layer exists to exercise for real. It belongs in `tests/`, not `tests/e2e/`.
- The fixture repo `mrsixw/breakfast-fixtures` is frozen and archived. Its PRs are asserted by exact count. **Never modify it.**
- Run `make test` before committing. Run `make e2e` when changing CLI behaviour, packaging, or the cache.
- **Add an end-to-end scenario when the change is one only the real binary can prove.** Ask what a unit test structurally cannot see. Add one for:
  - a new or changed **exit code**, or a new user-facing error path;
  - anything about **stdout versus stderr** — `CliRunner` merges them, so only the e2e layer can prove the split;
  - a new **subcommand**, or a change to how the built artifact is packaged or invoked;
  - anything writing to or reading from **disk** — cache layers, config generation, state files;
  - **ordering** properties, e.g. that a guard fires before any network call;
  - a new **output format**, or a change to an existing one's shape.
- **Do not** add one for filter permutations, formatting details or branch coverage. Those belong in `tests/test_cli.py`, where fixtures are free and no API calls are spent. Every live scenario costs real GitHub requests, so the suite stays small and each scenario earns its place.
- Live scenarios assert exact counts against the frozen fixture repo. If a scenario needs PR data the repo does not have, the inventory must change — see `docs/design/testing.md`; the repo is archived and needs unarchiving to amend. Never adjust an assertion to match drifted fixtures.
- **Test-driven development (red, green, refactor):** When adding tests for a bug fix or new feature, write the failing test **first**, run it and confirm it goes red, then write the code to make it green, then refactor. A test that has never been seen to fail proves nothing — it may assert behaviour that was already correct, or be miswired and pass regardless. Report the red run, not just the green one.
- If a fix was written before its tests (e.g. rule discovered mid-task), prove the tests red retroactively: `git stash push <source file>`, run the suite, confirm the failures, then `git stash pop`.
- **Testing with Cache:** Since caching is implemented, all manual testing must be performed both *with* the cache enabled and *without* the cache (e.g., clearing the cache or disabling it).
- **Real App Testing:** Always perform a real, end-to-end test of the CLI application in the terminal, not just unit tests. `make e2e` is the automated form of this and should be run alongside it.

## Work Items
- This project uses GitHub issues (not Jira). Reference the GitHub issue number in branch names and PR titles.
- Branch names should include the issue number and a short description (e.g., `issue-26_filter_pr_authors`).
- **Before creating a new branch, always sync `main` first and check its CI status:**
  ```bash
  git fetch origin main && git checkout main && git pull origin main
  ```
  Then, check the CI status of the latest completed run on `main`:
  ```bash
  gh run list --branch main --status completed --limit 1 --json conclusion --jq '.[0].conclusion'
  ```
  If the output is not `success`, stop immediately, report the build failure to the user, and do not create a branch from a broken `main` until resolved.
  Branch off the updated `main`. Never start a feature branch from a stale local copy.
- **A GitHub issue MUST exist before any work begins.** If the user requests a change and no issue exists yet, create one (or ask the user to create one) before starting implementation. Every branch, commit, and PR must reference an issue number. *Exception*: Refinements, feedback iterations, or trivial tweaks on in-flight/undelivered feature branches do not require raising new issues; make changes directly on the active branch. If you are unsure whether to raise a new GitHub issue or continue on a current active branch, always pause and ask the user directly first.
- **One issue = one branch = one PR.** Never combine fixes for multiple unrelated issues into a single PR. If changes are related and depend on each other, open them as a stack of PRs (one per issue) rather than bundling. *Exception*: Trivial tweaks or closely related follow-up iterations can be added directly to the active branch rather than stack-PRing every detail.

## Automated Workflows
This repository provides standardized automated workflows for managing issues. All agents must refer to and execute these exact steps:
- **Start work on an issue:** Follow the steps defined in [.agents/skills/start-issue/SKILL.md](.agents/skills/start-issue/SKILL.md).
- **Finish work on an issue:** Follow the steps defined in [.agents/skills/finish-issue/SKILL.md](.agents/skills/finish-issue/SKILL.md).
- **Raise a Pull Request:** Follow the steps defined in [.agents/skills/raise-pr/SKILL.md](.agents/skills/raise-pr/SKILL.md).
- **Monitor Pull Request CI:** Follow the steps defined in [.agents/skills/monitor-pr/SKILL.md](.agents/skills/monitor-pr/SKILL.md).
- **Raise a new issue:** Follow the steps defined in [.agents/skills/raise-issue/SKILL.md](.agents/skills/raise-issue/SKILL.md).

## Module API contract
- A leading `_` means "internal to this module". Anything a sibling module
  imports must not have one, and must appear in that module's `__all__`.
- Every module in `src/breakfast/` declares `__all__`. Add new public names to it.
- `constants.py` holds no underscore-prefixed names at all — a module of pure
  data has no invariants to protect.
- Reach other modules through their public names only. If you need something a
  module keeps private, widen that module's API deliberately — rename it and add
  it to `__all__` — rather than reaching past the underscore. A private name you
  had to import was never really private.
- The same applies to third-party libraries: depend on their documented API, not
  on internals that can change in a patch release.
- `tests/test_public_api.py` enforces the first two. Tests may still reach into
  the internals of the module they test — that boundary is not policed.

## Commit Messages
- Use Conventional Commits (e.g., `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`, `refactor: ...`, `test: ...`, `ci: ...`).
- Keep the summary short and imperative.

## Pull Requests
- Include the issue number in PR titles (e.g., `#7: Split test deps and migrate to uv`).
- Always include `Closes #N` in the PR body so the issue is automatically closed when the PR is merged.
- **Before merging a PR, tick off all acceptance criteria checkboxes in the linked GitHub issue** that were satisfied by the PR's changes. Use `gh issue edit <N> --body "..."` to update the body. If a criterion was not met, leave it unchecked and add a comment explaining why.
- **After pushing to a branch with an open PR, wait for all CI checks to complete.** Use `gh pr checks` to monitor status. If any check fails, investigate and fix the root cause before proceeding — do not ignore failures or re-push without understanding them.
- **No PR Merges by Agents:** CRITICAL: Agents must NEVER, under any circumstances, merge pull requests. Merging PRs is strictly reserved for the human user. Any automated merge commands or attempts to merge are strictly forbidden.
- **No Force Pushing:** Agents must NOT use force pushing (`git push --force` or similar). If force pushing is absolutely necessary, the agent must first explain the reason to the user, list all other alternatives that were exhausted, and obtain explicit user confirmation before proceeding.

## mkver Usage
- `git mkver patch` mutates the version file; avoid running it as part of routine local builds on feature branches.
- Prefer running mkver only when preparing a release/version bump commit, then commit the version change explicitly.
- If a build requires mkver, reset the version file afterward to keep the working tree clean.

## CI and Releases
- CI should run tests on pull requests and pushes.
- On merges to `main`, create a release and tag; ensure the version is bumped before release.
- Add a sanity check: if a tag already exists for the current version, run `git mkver patch` to bump it before releasing.
- Prefer using Makefile targets for CI steps (add targets as needed to keep local/CI workflows consistent).
- Releases are created by CI via `gh release create --generate-notes`, which auto-formats merged PR titles as `* title by @author in <URL>` bullets.
- **Release notes format:** The `update-summary` feature reads the release body and extracts the first three bullet points (`- ` or `* `), strips Markdown headers and URLs, and caps output at 200 characters. If editing release notes manually (e.g. via the GitHub UI), use clean bullet points so `update-summary` renders useful output — avoid prose paragraphs at the top of the body.

## Code Quality
- Use `ruff` (lint + import sorting) and `black` (formatting).
- Prefer running checks via CI and pre-commit hooks where possible.
- **Before every commit and push, you MUST run all three of these in order — no exceptions:**
  1. `make format` — auto-fix formatting
  2. `make lint` — must exit clean
  3. `make test` — all tests must pass
  Skipping any of these steps is not acceptable, even for small or documentation-only changes.
- **Never use bare `except Exception`.** Always catch the most specific exception type(s) possible (e.g. `requests.exceptions.RequestException`, `OSError`, `json.JSONDecodeError`, `KeyError`, `ValueError`, `PackageNotFoundError`). Bare `except Exception` hides bugs and swallows unexpected errors silently.
- **stdout/stderr discipline:** All data output (table, JSON, summary views) must go to **stdout**. All progress messages, spinner emoji, warnings, and errors must go to **stderr** (`err=True` in Click). This keeps every output format safe to pipe or redirect independently. Tests must assert data on `result.stdout` and status/error messages on `result.stderr`.

## Tone and Personality
- This project is playful and fun. Embrace whimsy — emoji, breakfast theming, and a lighthearted tone are encouraged.
- The progress spinner already uses random breakfast emoji (🥐🍳🧇). New user-facing features should follow this spirit: use emoji and colour to make output feel lively, not dry.
- Keep the fun in the UI layer (output, messages, docs). The underlying code should still be clean and well-tested.

## Documentation
- User-facing documentation lives in `docs/manual/`. Design documents live in `docs/design/`.
- **When adding, changing, or removing CLI options, features, or user-visible behaviour, you MUST update the relevant manual pages in `docs/manual/` in the same commit or PR.** This includes `options.md`, `usage.md`, `output-formats.md`, and `troubleshooting.md` as appropriate.
- **If the project structure or developer workflow changes, you MUST update `CONTRIBUTING.md`.**
- When adding a new feature design, create a document in `docs/design/` and add it to the table in `docs/design/README.md`.

## Working Style
- **Narrate intent before acting.** If a task would take the work beyond the literal ask, say so first and wait for confirmation. Never expand scope silently.
- **Surface, don't solve.** If related work is spotted (missing docs, adjacent bugs, cleanup opportunities), flag it as an observation and ask before doing anything. "I notice X — want me to address that too?"
- **Ask when scope is ambiguous.** When an instruction could mean a narrow or a broad thing, ask which is wanted before writing a single line of code or docs.
- **Pause at natural checkpoints on large changes.** For multi-step or multi-file work, describe the plan and confirm before committing and pushing. That way the user can redirect early rather than unpicking completed work.
