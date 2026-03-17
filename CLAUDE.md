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
- `tests/` — module-specific pytest suite
- `pyproject.toml` — project metadata, dependencies, tool config
- `Makefile` — build, test, lint, and format targets
- `utils/` — helper scripts for release management
- `mkver.conf` — version bump configuration
- `docs/` — project documentation
  - `docs/manual/` — user-facing manual (installation, usage, options, output formats, troubleshooting)
  - `docs/design/` — technical design documents for planned features

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
- **A GitHub issue MUST exist before any work begins.** If the user requests a change and no issue exists yet, create one (or ask the user to create one) before starting implementation. Every branch, commit, and PR must reference an issue number.
- **Always use git worktrees.** Each issue gets its own worktree so branches stay fully isolated — especially important when multiple agents work in parallel. Create one with `git worktree add ../breakfast-issue-N issue-N_short_description`. Never do feature work directly in the main checkout.

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

## Code Quality
- Use `ruff` (lint + import sorting) and `black` (formatting).
- Prefer running checks via CI and pre-commit hooks where possible.
- Before committing and pushing changes, run `make test`, `make lint`, and `make format` locally.
- **Never use bare `except Exception`.** Always catch the most specific exception type(s) possible (e.g. `requests.exceptions.RequestException`, `OSError`, `json.JSONDecodeError`, `KeyError`, `ValueError`, `PackageNotFoundError`). Bare `except Exception` hides bugs and swallows unexpected errors silently.

## Tone and Personality
- This project is playful and fun. Embrace whimsy — emoji, breakfast theming, and a lighthearted tone are encouraged.
- The progress spinner already uses random breakfast emoji (🥐🍳🧇). New user-facing features should follow this spirit: use emoji and colour to make output feel lively, not dry.
- Keep the fun in the UI layer (output, messages, docs). The underlying code should still be clean and well-tested.

## Documentation
- User-facing documentation lives in `docs/manual/`. Design documents live in `docs/design/`.
- **When adding, changing, or removing CLI options, features, or user-visible behaviour, you MUST update the relevant manual pages in `docs/manual/` in the same commit or PR.** This includes `options.md`, `usage.md`, `output-formats.md`, and `troubleshooting.md` as appropriate.
- **If the project structure or developer workflow changes, you MUST update `CONTRIBUTING.md`.**
- When adding a new feature design, create a document in `docs/design/` and add it to the table in `docs/design/README.md`.
