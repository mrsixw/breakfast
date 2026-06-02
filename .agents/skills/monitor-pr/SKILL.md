---
name: monitor-pr
description: Monitor the CI checks status of a Pull Request on GitHub, parse logs on failure, and address any non-passing tests.
---

# Monitor PR Skill

Standardized procedure to track pull request CI checks on GitHub and address any test or linting failures.

## When to use this skill
- Use this skill after raising a pull request (e.g., using `raise-pr`), or when the user requests to check, monitor, or track the CI/test status of an active PR.

## How to use it

### Steps

1. **Check CI checks status:**
   Use the GitHub CLI (`gh`) to retrieve the status of all active checks on the current branch:
   ```bash
   gh pr checks
   ```

2. **Wait for completion (if pending):**
   If any checks are marked as `pending`:
   - Set a one-shot wakeup timer using the `schedule` tool (e.g., set for 120 seconds with the prompt `"Check CI status for PR"`).
   - Stop calling tools to yield back control while the timer is running.
   - Do NOT run a shell `sleep` loop or poll continuously in a terminal process.

3. **Handle successful runs:**
   If all checks are marked as `pass` or `success`:
   - Confirm to the user that CI has successfully completed and all tests are passing.
   - Inform the user that the PR is ready for review and merge.

4. **Diagnose and fix failures (if any check fails):**
   If any check fails (status is `fail` or `failure`):
   - **Identify the failing check:** Look at the name of the failing check (e.g., `test`, `lint`, `docs-lint`).
   - **View failing logs:** Retrieve the CI run details or logs:
     ```bash
     gh run list --branch <current-branch> --limit 1
     gh run view <run-id> --log-failed
     ```
   - **Reproduce locally:** Execute the matching local quality check target to reproduce the failure in your workspace:
     - For test failures: `make test` (or run a specific test: `uv run pytest -k <failing_test_name>`)
     - For lint/format failures: `make lint` or `make format`
   - **Fix the issue:** Debug the codebase, resolve the failing tests/lint issues, and run the complete verification suite locally (`make format && make lint && make test`) to confirm the fix.
   - **Push the fix:** Stage the modified files, commit them using conventional commits (`fix: address failing CI check`), and push them to origin (`git push`).
   - **Resume monitoring:** Go back to Step 1 to monitor the fresh CI run.
