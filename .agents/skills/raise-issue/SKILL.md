---
name: raise-issue
description: Raise a detailed, structured issue on GitHub. Gathers context, builds reproduction steps, expected outcomes, and acceptance criteria.
---

# Raise Issue Skill

Standardized procedure to generate and raise a high-quality, deeply detailed issue on GitHub for this project.

## When to use this skill
- Use this skill when you identify a bug, a required enhancement, or a new feature that does not have an active GitHub issue yet.
- Remember: **A GitHub issue MUST exist before any coding work begins.** Always use this skill to create the issue first.

## How to use it

### Steps

1. **Analyze the problem or requirement:**
   Collect all relevant details:
   - For bugs: exact error tracebacks, terminal output, reproduction commands, and conditions.
   - For features: the proposed feature goals, user benefit, command-line flags, configuration structures, and CLI outputs.

2. **Generate a detailed, structured description:**
   Determine whether the issue is a **Bug** or a **Feature/Enhancement**, and choose the corresponding structure.

   #### Structure for Bug Issues:
   ```markdown
   ## Problem
   [Detailed description of what is failing and why it is wrong/suboptimal. Include any traceback error logs here.]

   ## Steps to reproduce / Reproduction
   \`\`\`bash
   [Exact shell command or python sequence to trigger the bug]
   \`\`\`

   ## Expected behaviour
   [Explain what the CLI/application should ideally output or do.]

   ## Actual behaviour
   [Explain what the CLI/application is currently outputting or doing.]

   ## Suspected Cause (optional)
   [If a specific file, class, function, or recent commit is suspected, reference it here.]
   ```

   #### Structure for Feature/Enhancement Issues:
   ```markdown
   ## Description / Problem
   [High-level explanation of the new feature, why it is beneficial, and what user problem it solves.]

   ## Proposed Solution
   [Explain how it should be implemented, listing CLI flags, configuration parameters, and code structure.]

   ## Examples
   \`\`\`bash
   # Show command examples if applicable
   breakfast -o spec --new-flag
   \`\`\`

   ## Acceptance Criteria
   - [ ] [Feature behaves as expected under condition A]
   - [ ] [Configuration overrides CLI values correctly]
   - [ ] [Updated manual pages in docs/manual/ reflect changes]
   - [ ] [make format && make lint && make test all pass]
   ```

3. **Verify the Title format:**
   Ensure the issue title is clean and descriptive.
   - **Important**: Do not use conventional commit prefixes (like `feat:` or `fix:`) in GitHub issue titles, as these are reserved for commits and PRs. Keep the title imperative and natural.
   - *Example*: "Support per-org scoped repo filter with org:filter syntax"

4. **Create the issue using the GitHub CLI (`gh`):**
   Execute the `gh issue create` command using the derived title and generated body:
   ```bash
   gh issue create --title "<title>" --body "<body>"
   ```
   *(If the GitHub CLI is not authenticated or available, output the formatted title and body so the user can easily copy and paste them into the GitHub web interface).*

5. **Confirm to the user:** Report the generated issue URL, issue number, and a summary of the details.
