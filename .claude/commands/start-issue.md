Start work on a GitHub issue: sync main, look up the issue title, and create the branch.

Usage: /start-issue <issue-number>

## Steps

1. Sync main first:
   ```
   git fetch origin main && git checkout main && git pull origin main
   ```

2. Look up the issue title using the GitHub MCP tool (`mcp__github__issue_read`) for owner `mrsixw`, repo `breakfast`, and the provided issue number.

3. Derive a branch name from the issue title:
   - Format: `issue-<N>_<short_description>`
   - Short description: lowercase, underscores, 3–5 words max, no articles or filler words
   - Example: issue title "Add version to separator comment" → `issue-306_version_separator_comment`

4. Create and checkout the branch:
   ```
   git checkout -b <branch-name>
   ```

5. Confirm to the user: issue title, branch name, and that they're ready to work.
