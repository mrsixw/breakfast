---
name: raise-pr
description: Generate a detailed, high-depth pull request body and create a PR on GitHub. Analyzes changes and creates a highly informative PR description.
---

# Raise PR Skill

Standardized procedure to generate and submit a highly detailed, high-depth pull request on GitHub for this project.

## When to use this skill
- Use this skill when you have completed work on an issue branch, run all verification checks, and are ready to create a GitHub Pull Request for the active branch.

## How to use it

### Steps

1. **Analyze workspace changes:**
   Review your local git changes, commit history, and test outcomes to collect all context:
   - Identify which files were created, modified, or deleted.
   - Collect the exact names of any new unit tests added (e.g., in `tests/test_*.py`).
   - Identify the linked GitHub issue number from your branch name (`issue-<N>_...`).

2. **Generate a detailed, high-depth PR body:**
   Construct a pull request body matching the standard project PR template structure. Your description must be rich and thorough (avoiding generic or one-sentence summaries).

   #### Template Format:
   ```markdown
   ## Summary

   - **[Brief feature description]**: [Explain the high-level intent].
   - **Key Changes**:
     - Detail the specific classes, functions, or logic flows modified (e.g., in `src/breakfast/`).
     - List any new configuration keys or command-line arguments introduced.
     - List new files, directories, or assets added to the codebase.
   - **Abstractions & Design Decisions**: Explain any architectural or design patterns utilized (e.g., modular directory structures, custom index iterables).

   ## Test plan

   - [x] `make format && make lint && make test` passes (verify all checks are clean).
   - [x] **[Specific unit tests run or added]**:
     - `test_func_a` — verifies [intent].
     - `test_func_b` — verifies [intent].
   - [x] **Manual Verification / Smoke Test**:
     - Verify CLI execution (e.g., `uv run breakfast --version` runs cleanly).
     - Run any targeted CLI configurations to confirm visual correctness.

   Closes #<issue-number>

   🤖 Prepared by [Antigravity](https://github.com/google-deepmind)
   ```

3. **Verify the PR Title format:**
   Ensure the Pull Request title matches the mandatory convention:
   `#<issue-number>: <description>`
   - *Example*: `#313: Color PR number column with calendar color`

4. **Create the PR using the GitHub CLI (`gh`):**
   Execute the `gh pr create` command using the derived title and generated body:
   ```bash
   gh pr create --title "#<issue-number>: <short-description>" --body "<generated-body-content>"
   ```
   *(If the GitHub CLI is not authenticated or available, output the formatted title and body so the user can easily copy and paste them into the GitHub web interface).*

5. **Confirm to the user:** Report the generated PR URL and a summary of the details submitted.
