# Claude Instructions

## Project Overview
- **breakfast** is a CLI tool that displays open GitHub pull requests across an organization's repos in a terminal table.
- Built with Python and Click. Uses the GitHub REST and GraphQL APIs.
- Package structure: code in `src/breakfast/`, tests in `tests/`.
- The name is tongue-in-cheek: breakfast is the first thing you consume each morning, and open PRs are the first thing you should consume at the start of your workday.

## Project Structure
- `src/breakfast/` — package source code
  - `cli.py` — Click command definition and entry point
  - `api.py` — GitHub API interaction logic
  - `config.py` — TOML configuration and filtering
  - `ui.py` — Terminal formatting and progress emojis
  - `updater.py` — Version checking and caching
  - `cache.py` — HTTP response caching
  - `logger.py` — Logging configuration
  - `xdg.py` — XDG base directory support
- `tests/` — module-specific pytest suite
- `pyproject.toml` — project metadata, dependencies, tool config
- `Makefile` — build, test, lint, and format targets
- `utils/` — helper scripts for release management
- `mkver.conf` — version bump configuration
- `docs/` — project documentation
  - `docs/manual/` — user-facing manual (installation, usage, options, output formats, troubleshooting)
  - `docs/design/` — technical design documents for planned features

## Agent Instruction Files
This project maintains per-agent instruction files that all convey the same rules:
- `CLAUDE.md` — Claude Code (this file)
- `GEMINI.md` — Gemini
- `AGENTS.md` — OpenAI Codex
- `.github/copilot-instructions.md` — GitHub Copilot

When updating project rules, update **all four files** to keep them consistent.

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
- Tests use `pytest` with `monkeypatch` for mocking and `click.testing.CliRunner` for CLI tests.
- Run `make test` before committing.
- **Testing with Cache:** Since caching is implemented, all manual testing must be performed both *with* the cache enabled and *without* the cache (e.g., clearing the cache or disabling it).
- **Real App Testing:** Always perform a real, end-to-end test of the CLI application in the terminal, not just unit tests.

## Work Items
- This project uses GitHub issues (not Jira). Reference the GitHub issue number in branch names and PR titles.
- Branch names should include the issue number and a short description (e.g., `issue-26_filter_pr_authors`).
- **A GitHub issue MUST exist before any work begins.** If the user requests a change and no issue exists yet, create one (or ask the user to create one) before starting implementation. Every branch, commit, and PR must reference an issue number. *Exception*: Refinements, feedback iterations, or trivial tweaks on in-flight/undelivered feature branches do not require raising new issues; make changes directly on the active branch. If you are unsure whether to raise a new GitHub issue or continue on a current active branch, always pause and ask the user directly first.
- **One issue = one branch = one PR.** Never combine fixes for multiple unrelated issues into a single PR. If changes are related and depend on each other, open them as a stack of PRs (one per issue) rather than bundling. *Exception*: Trivial tweaks or closely related follow-up iterations can be added directly to the active branch rather than stack-PRing every detail.

## Automated Workflows
This repository provides standardized automated workflows for managing issues. All agents must refer to and execute these exact steps:
- **Start work on an issue:** Follow the steps defined in [.agents/skills/start-issue/SKILL.md](.agents/skills/start-issue/SKILL.md).
- **Finish work on an issue:** Follow the steps defined in [.agents/skills/finish-issue/SKILL.md](.agents/skills/finish-issue/SKILL.md).
- **Raise a Pull Request:** Follow the steps defined in [.agents/skills/raise-pr/SKILL.md](.agents/skills/raise-pr/SKILL.md).
- **Monitor Pull Request CI:** Follow the steps defined in [.agents/skills/monitor-pr/SKILL.md](.agents/skills/monitor-pr/SKILL.md).
- **Raise a new issue:** Follow the steps defined in [.agents/skills/raise-issue/SKILL.md](.agents/skills/raise-issue/SKILL.md).

## Commit Messages
- Use Conventional Commits (e.g., `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`, `refactor: ...`, `test: ...`, `ci: ...`).
- Keep the summary short and imperative.

## Pull Requests
- Include the issue number in PR titles (e.g., `#7: Split test deps and migrate to uv`).
- Always include `Closes #N` in the PR body so the issue is automatically closed when the PR is merged.
- **After pushing to a branch with an open PR, wait for all CI checks to complete.** Use `gh pr checks` to monitor status. If any check fails, investigate and fix the root cause before proceeding — do not ignore failures or re-push without understanding them.

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
