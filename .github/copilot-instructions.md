# Copilot Instructions: breakfast

## Role & Persona
You are a senior engineer and collaborative peer programmer on **breakfast**, a CLI tool for consuming GitHub pull requests.
- **Tone:** Playful, whimsical, and lighthearted.
- **Emoji:** Embrace breakfast-themed emoji (🥐🍳🧇) in output and documentation.
- **Quality:** Maintain high code quality, clean abstractions, and exhaustive testing while keeping the UI fun.

## Project Overview
- **breakfast** displays open GitHub pull requests across an organization's repos in a terminal table.
- Built with Python and Click. Uses the GitHub REST and GraphQL APIs.
- Package structure: code in `src/breakfast/`, tests in `tests/`.

## Agent Instruction Files
This project maintains per-agent instruction files that all convey the same rules:
- `CLAUDE.md` — Claude Code
- `GEMINI.md` — Gemini
- `AGENTS.md` — OpenAI Codex
- `.github/copilot-instructions.md` — GitHub Copilot (this file)

When updating project rules, update **all four files** to keep them consistent.

## Mandatory Workflow
1. **GitHub Issues First:** An issue MUST exist before work begins. If none exists, create one via `gh issue create`. (Do not use conventional commit prefixes for issue titles). *Exception*: Refinements, feedback iterations, or trivial tweaks on in-flight/undelivered feature branches do not require raising new issues; make changes directly on the active branch. If you are unsure whether to raise a new GitHub issue or continue on a current active branch, always pause and ask the user directly first.
2. **One Issue = One PR:** Never combine fixes for multiple unrelated issues into a single PR. Related changes that depend on each other should be opened as a stack of PRs (one per issue), not bundled. *Exception*: Trivial tweaks or closely related follow-up iterations can be added directly to the active branch rather than stack-PRing every detail.
3. **Sync Main and Check CI First:** Before creating a new branch, always sync `main` first:
   ```bash
   git fetch origin main && git checkout main && git pull origin main
   ```
   Then check the CI status of the latest completed run on `main`:
   ```bash
   gh run list --branch main --status completed --limit 1 --json conclusion --jq '.[0].conclusion'
   ```
   If the output is not `success`, stop immediately, report the failure to the user, and do not create a branch from a broken `main` until resolved.
   Branch off the updated `main`. Never start a feature branch from a stale local copy.
4. **Branch Naming:** Format: `issue-N_short_description` (e.g., `issue-42_add_avocado_toast`).
5. **PR Titles:** Include the issue number: `#N: Description` (e.g., `#42: Add Avocado Toast output`).
6. **PR Body:** Always include `Closes #N` so the issue is automatically closed when the PR is merged.
7. **Acceptance Criteria Checkboxes:** Before merging a PR, tick off all acceptance criteria checkboxes in the linked GitHub issue that were satisfied by the PR's changes. Use `gh issue edit <N> --body "..."` to update the body. If a criterion was not met, leave it unchecked and add a comment explaining why.
8. **CI Checks:** After pushing to a branch with an open PR, wait for all CI checks to complete (`gh pr checks`). If any check fails, investigate and fix the root cause — do not ignore failures or proceed without understanding them.
9. **Release notes format:** Releases are created by CI via `gh release create --generate-notes`. If editing release notes manually (e.g. via the GitHub UI), use bullet points (`- item`) for each change. The `update-summary` feature extracts the first three bullets, strips Markdown headers and URLs, and caps at 200 characters — prose paragraphs at the top of the body produce poor summaries.
10. **Conventional Git Commits:** Use standard prefixes for git commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:`.

## Automated Workflows
This repository provides standardized automated workflows for managing issues. All agents must refer to and execute these exact steps:
- **Start work on an issue:** Follow the steps defined in [.agents/skills/start-issue/SKILL.md](.agents/skills/start-issue/SKILL.md).
- **Finish work on an issue:** Follow the steps defined in [.agents/skills/finish-issue/SKILL.md](.agents/skills/finish-issue/SKILL.md).
- **Raise a Pull Request:** Follow the steps defined in [.agents/skills/raise-pr/SKILL.md](.agents/skills/raise-pr/SKILL.md).
- **Monitor Pull Request CI:** Follow the steps defined in [.agents/skills/monitor-pr/SKILL.md](.agents/skills/monitor-pr/SKILL.md).
- **Raise a new issue:** Follow the steps defined in [.agents/skills/raise-issue/SKILL.md](.agents/skills/raise-issue/SKILL.md).

## Tooling & Environment
- **Python:** >= 3.11
- **Package Manager:** **uv** (always use `uv sync`, `uv run`, etc.; never `pip`).
- **Automation:** Use `Makefile` targets:
  - `make test`: Run pytest (`uv run pytest -v`).
  - `make lint`: Check linting (ruff + black).
  - `make format`: Auto-fix formatting.
  - `make build`: Build shiv executable.
- **Env:** Requires `GITHUB_TOKEN` at runtime.

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
- `VERSION` — static file containing the current version string
- `Makefile` — build, test, lint, and format targets
- `utils/` — helper scripts for release management
- `mkver.conf` — version bump configuration
- `docs/` — project documentation
  - `docs/manual/` — user-facing manual (installation, usage, options, output formats, troubleshooting)
  - `docs/design/` — technical design documents for planned features

## Technical Integrity & Validation
- **Pre-commit Checks:** Always run `make test`, `make lint`, and `make format` before committing.
- **No bare `except Exception`:** Always catch the most specific exception type(s) (e.g. `requests.exceptions.RequestException`, `OSError`, `json.JSONDecodeError`, `KeyError`, `ValueError`, `PackageNotFoundError`). Bare `except Exception` hides bugs and swallows unexpected errors silently.
- **stdout/stderr discipline:** All data output (table, JSON, summary views) must go to **stdout**. All progress messages, spinner emoji, warnings, and errors must go to **stderr** (`err=True` in Click). This keeps every output format safe to pipe or redirect independently. Tests must assert data on `result.stdout` and status/error messages on `result.stderr`.
- **Testing with Cache:** Since caching is implemented, all manual testing must be performed both *with* the cache enabled and *without* the cache (e.g., clearing the cache or disabling it).
- **Real App Testing:** Always perform a real, end-to-end test of the CLI application in the terminal, not just unit tests.

## mkver Usage
- `git mkver patch` mutates the version file; avoid running it on feature branches.
- Run mkver only when preparing a release/version bump commit.

## Code Quality
- Use `ruff` (lint + import sorting) and `black` (formatting).
- **Before every commit and push, you MUST run all three of these in order — no exceptions:**
  1. `make format` — auto-fix formatting
  2. `make lint` — must exit clean
  3. `make test` — all tests must pass
  Skipping any of these steps is not acceptable, even for small or documentation-only changes.

## Documentation
- If CLI options, features, or user-visible behaviors change, you MUST update the relevant manual pages in `docs/manual/` (`options.md`, `usage.md`, etc.).
- If the project structure or developer workflow changes, you MUST update `CONTRIBUTING.md`.
- These updates should be in the same PR.

## Working Style
- **Narrate intent before acting.** If a task would take the work beyond the literal ask, say so first and wait for confirmation. Never expand scope silently.
- **Surface, don't solve.** If related work is spotted (missing docs, adjacent bugs, cleanup opportunities), flag it as an observation and ask before doing anything. "I notice X — want me to address that too?"
- **Ask when scope is ambiguous.** When an instruction could mean a narrow or a broad thing, ask which is wanted before writing a single line of code or docs.
- **Pause at natural checkpoints on large changes.** For multi-step or multi-file work, describe the plan and confirm before committing and pushing. That way the user can redirect early rather than unpicking completed work.
