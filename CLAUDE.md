# Claude Instructions

## Project Overview
- **breakfast** is a CLI tool that displays open GitHub pull requests across an organization's repos in a terminal table.
- Built with Python and Click. Uses the GitHub REST and GraphQL APIs.
- Single-module project: main code in `breakfast.py`, tests in `test_breakfast.py`.

## Project Structure
- `breakfast.py` — CLI entry point and all application logic
- `test_breakfast.py` — all tests (pytest)
- `pyproject.toml` — project metadata, dependencies, tool config
- `Makefile` — build, test, lint, and format targets
- `utils/read_version.py` — version helper for CI
- `mkver.conf` — version bump configuration

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

## Work Items
- This project uses GitHub issues (not Jira). Reference the GitHub issue number in branch names and PR titles.
- Branch names should include the issue number and a short description (e.g., `issue-26_filter_pr_authors`).
- **A GitHub issue MUST exist before any work begins.** If the user requests a change and no issue exists yet, create one (or ask the user to create one) before starting implementation. Every branch, commit, and PR must reference an issue number.

## Commit Messages
- Use Conventional Commits (e.g., `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`, `refactor: ...`, `test: ...`, `ci: ...`).
- Keep the summary short and imperative.

## Pull Requests
- Include the issue number in PR titles (e.g., `#7: Split test deps and migrate to uv`).
- Ensure CI is green before requesting review or merging PRs.

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
