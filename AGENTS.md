# Agent Instructions

## Commit Messages
- Use Conventional Commits (e.g., `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`, `refactor: ...`, `test: ...`, `ci: ...`).
- Keep the summary short and imperative.

## Pull Requests
- Include the issue number in PR titles (e.g., `#7: Split test deps and migrate to uv`).

## mkver Usage
- `git mkver patch` mutates the version file; avoid running it as part of routine local builds on feature branches.
- Prefer running mkver only when preparing a release/version bump commit, then commit the version change explicitly.
- If a build requires mkver, reset the version file afterward to keep the working tree clean.
