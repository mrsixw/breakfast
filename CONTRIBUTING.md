# Contributing to breakfast

Thanks for your interest in contributing to **breakfast**! This guide covers setup, development workflow, and project conventions.

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) package manager (not pip). If you do not already have it, install it with `python -m pip install --user uv`.
- A `GITHUB_TOKEN` environment variable for running the tool

## Getting Started

1. Fork and clone the repository.
2. Install from source and set up dev dependencies:

   ```bash
   make .venv
   ```

   This runs `uv venv` and `uv sync --extra dev` to set up everything you need.

3. Run the tests to make sure things work:

   ```bash
   make test
   ```

## Project Structure

- `src/breakfast/` — package source code
  - `cli.py` — Click command definition and entry point
  - `api.py` — GitHub API interaction logic
  - `config.py` — TOML configuration and filtering
  - `ui.py` — Terminal formatting and progress emojis
  - `updater.py` — Version checking and caching
- `tests/` — module-specific pytest suite
- `pyproject.toml` — project metadata, dependencies, tool config
- `VERSION` — static file containing the current version string
- `Makefile` — build, test, lint, and format targets
- `utils/` — shell and python scripts for release management
- `mkver.conf` — version bump configuration

## Development Workflow

### Branching

- Create a branch from `main` with the issue number and a short description:

  ```text
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

### Testing the man page locally

Generate and view the man page without installing:

```bash
make man
man -l man1/breakfast.1.gz
```

### Testing shell completions locally

Generate the completion scripts:

```bash
make completions
```

Then load them in your current shell session:

**Bash:**

```bash
source completions/breakfast.bash
breakfast <tab>
```

**Zsh:**

```zsh
fpath=($(pwd)/completions $fpath)
autoload -Uz compinit && compinit
breakfast <tab>
```

**Fish:**

```fish
source completions/breakfast.fish
breakfast <tab>
```

These are temporary — they only apply to the current shell session and do not affect your system installation.

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

## Agent Instruction Files

This project maintains per-agent instruction files so that AI coding assistants follow the same conventions:

| File | Agent |
| ------ | ------- |
| `CLAUDE.md` | Claude Code |
| `GEMINI.md` | Gemini |
| `AGENTS.md` | OpenAI Codex |
| `.github/copilot-instructions.md` | GitHub Copilot |

All four files convey the same project rules. **When updating project conventions, update all four files in the same PR.**

## Code Quality

- **Linter:** [ruff](https://docs.astral.sh/ruff/) (lint rules: E, F, I)
- **Formatter:** [black](https://black.readthedocs.io/) (line length 88, target Python 3.11)
- Run checks locally before pushing. CI will also verify these.

## mkver / Versioning

- Do **not** run `git mkver patch` on feature branches — it mutates the version file.
- Version bumps happen when preparing a release, not during regular development.

## Releases

Releases are created automatically by CI on every push to `main` (excluding version-bump commits). The workflow runs:

```bash
gh release create vX.Y.Z --generate-notes
```

GitHub auto-generates release notes from merged PR titles, formatted as:

```markdown
## What's Changed
* #N: PR title by @author in https://github.com/.../pull/N

**Full Changelog**: https://github.com/.../compare/vX...vY
```

### Release notes and `update-summary`

The `update-summary` config option lets users opt in to seeing a short digest of the release body when a new version is available. It works by:

1. Picking the first three bullet-point lines (`-`, `*`, or `•` prefixes)
2. Stripping Markdown headers and bare URLs
3. Capping the result at 200 characters

The auto-generated `--generate-notes` format is compatible (the `## What's Changed` header is stripped, bullet lines are picked up, and the Full Changelog URL is stripped). However, the output includes `by @author in` tails left after URL removal, which can look awkward.

**If you edit release notes manually** (e.g. via the GitHub UI after the release is created), use clean bullet points for the best `update-summary` output:

```markdown
- Add --sort option for custom PR ordering
- Fix --checks with per-repo cache hits
- New --exclude-label filter
```

Avoid opening with prose paragraphs — without bullet points, `update-summary` falls back to the first non-empty line of the body, which is usually a poor summary.
