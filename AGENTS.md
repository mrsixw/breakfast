# Agent Instructions

## Work Items
- This project uses GitHub issues (not Jira). Reference the GitHub issue number in branch names and PR titles.

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
