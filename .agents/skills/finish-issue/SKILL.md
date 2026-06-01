---
name: finish-issue
description: Finish work on the current issue branch. Runs quality gates (formatting, linting, tests), handles uv.lock version drift, and pushes to remote.
---

# Finish Issue Skill

Standardized procedure to finalize work, run quality checks, and push an issue branch to remote.

## When to use this skill
- Use this skill when the user requests to finish work on an issue, push changes, run final checks, or when executing a command or intent like `/finish-issue`.

## How to use it

### Steps

1. **Run the full quality gate in order — stop and report if anything fails:**
   ```bash
   make format && make lint && make test
   ```

2. **Check for a dirty `uv.lock`:**
   ```bash
   git diff --name-only
   ```
   If `uv.lock` is the only modified file (version drift from `uv sync`), stage and commit it:
   ```bash
   git add uv.lock
   git commit -m "chore: update uv.lock"
   ```
   If other files are dirty, stop and ask the user what to do — do not auto-commit unknown changes.

3. **Push the branch to the remote repository:**
   ```bash
   git push -u origin HEAD
   ```

4. **Confirm to the user:** Report that the branch is pushed and ready for a Pull Request.
