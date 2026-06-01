---
name: start-issue
description: Start work on a new GitHub issue. Fetches issue details, generates standard branch names, and sets up the branch.
---

# Start Issue Skill

Standardized procedure to initialize work on a new issue branch.

## When to use this skill
- Use this skill when the user requests to start work on a new issue, checkout a new issue branch, or when executing a command or intent like `/start-issue <issue-number>`.

## How to use it

### Steps

1. **Sync main first:**
   ```bash
   git fetch origin main && git checkout main && git pull origin main
   ```

2. **Look up the issue title dynamically using the GitHub CLI (`gh`):**
   ```bash
   gh issue view <issue-number> --json title --jq .title
   ```
   *(If the GitHub CLI is not authenticated or available, fall back to any available GitHub/MCP tool).*

3. **Derive a branch name from the issue title:**
   - Format: `issue-<N>_<short_description>`
   - Short description: lowercase, underscores, 3–5 words max, no articles or filler words
   - Example: issue title "Add version to separator comment" → `issue-306_version_separator_comment`

4. **Create and checkout the branch:**
   ```bash
   git checkout -b <branch-name>
   ```

5. **Confirm to the user:** Report the issue title, the derived branch name, and that you are ready to start coding.
