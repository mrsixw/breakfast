# Contributing to breakfast

Thanks for your interest in contributing to **breakfast**! This guide covers setup, development workflow, and project conventions.

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) package manager (not pip). If you do not already have it, install it with `python -m pip install --user uv`.
- A `GITHUB_TOKEN` environment variable for running the tool

## Getting Started

1. Fork and clone the repository.
2. Create a virtual environment and install dev dependencies:

   ```bash
   make .venv
   ```

   This runs `uv venv` and `uv sync --extra dev` to set up everything you need.

3. Run the tests to make sure things work:

   ```bash
   make test
   ```

## Project Structure

- `breakfast.py` — CLI entry point and all application logic
- `test_breakfast.py` — all tests (pytest)
- `pyproject.toml` — project metadata, dependencies, tool config
- `Makefile` — build, test, lint, and format targets
- `utils/read_version.py` — version helper for CI
- `mkver.conf` — version bump configuration

## Development Workflow

### Branching

- Create a branch from `main` with the issue number and a short description:

  ```
  issue-26_filter_pr_authors
  ```

### Running Tests

```bash
make test        # uv run pytest -v
```

Tests use `pytest` with `monkeypatch` for mocking and `click.testing.CliRunner` for CLI tests.

### Linting and Formatting

```bash
make lint        # ruff check + black --check
make format      # ruff check --fix + black
```

Run both `make test` and `make lint` before committing.

### Building

```bash
make build       # builds a shiv executable
```

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `test:` — adding or updating tests
- `chore:` — maintenance tasks
- `ci:` — CI/CD changes

Keep the summary short and imperative (e.g., `feat: add label filtering`).

## Pull Requests

- Include the issue number in the PR title (e.g., `#7: Split test deps and migrate to uv`).
- Ensure CI is green before requesting review.
- Keep PRs focused — one issue per PR where possible.

## Code Quality

- **Linter:** [ruff](https://docs.astral.sh/ruff/) (lint rules: E, F, I)
- **Formatter:** [black](https://black.readthedocs.io/) (line length 88, target Python 3.11)
- Run checks locally before pushing. CI will also verify these.

## mkver / Versioning

- Do **not** run `git mkver patch` on feature branches — it mutates the version file.
- Version bumps happen when preparing a release, not during regular development.
