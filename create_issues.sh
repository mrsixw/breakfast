#!/usr/bin/env bash
# Creates all proposed issues on GitHub.
# Requires: gh CLI authenticated (`gh auth login`)
# Usage: ./create_issues.sh

set -euo pipefail

create_issue() {
    local title="$1"
    local body="$2"
    echo "Creating: $title"
    gh issue create --repo mrsixw/breakfast --title "$title" --body "$body"
    echo ""
}

create_issue "Support multiple organizations in a single run" "$(cat <<'EOF'
## Summary
Allow users to scan PRs across multiple GitHub organizations in one invocation.

## Problem
Currently `--organization` / `-o` accepts only a single organization. Users who work across multiple orgs must run `breakfast` multiple times and mentally merge the results.

## Proposed behavior
- Accept repeated `--organization` flags: `breakfast -o org1 -o org2 -r app`
- Aggregate all PRs into a single table, with the existing Repo column disambiguating
- Progress output should show which org is currently being fetched

## Implementation notes
- Change the `-o` Click option to `multiple=True`
- Loop over each organization in `get_github_prs` (or call it per-org and merge)
- Ensure JSON output includes an `organization` field so consumers can distinguish

## Acceptance criteria
- Multiple `-o` flags accepted and all orgs' PRs displayed together
- Single `-o` still works as before (no breaking change)
- JSON output includes org context
EOF
)"

create_issue "Add --draft / --no-draft filter flag" "$(cat <<'EOF'
## Summary
Add a flag to filter PRs by draft status.

## Problem
Draft PRs are often work-in-progress and clutter the output when users are looking for reviewable PRs. Conversely, sometimes users want to see *only* drafts to check progress.

## Proposed behavior
- `--no-draft` — exclude draft PRs (show only non-draft)
- `--draft` — show only draft PRs
- Default (neither flag) — show all PRs (current behavior, no breaking change)

## Implementation notes
- The `draft` field is already returned by the GitHub PR detail API
- Add filtering in `filter_pr_details` or alongside existing filtering logic
- Consider adding a "Draft" indicator column or prefix in the table output

## Acceptance criteria
- `--draft` shows only draft PRs
- `--no-draft` excludes draft PRs
- Default behavior unchanged
- Works with both table and `--json` output
EOF
)"

create_issue "Add --sort option for table output ordering" "$(cat <<'EOF'
## Summary
Let users sort the PR table by a chosen column.

## Problem
Output order is currently determined by API response order, which is unpredictable and not useful for scanning. Users often want to see oldest PRs first, or group by repo/author.

## Proposed behavior
- `--sort age` — sort by PR age (oldest or newest first)
- `--sort repo` — sort alphabetically by repo name
- `--sort author` — sort alphabetically by author
- `--sort files` / `--sort additions` / `--sort comments` — sort by size metrics
- Optional `--reverse` flag to flip sort direction

## Implementation notes
- Sort the `pr_data` / `pr_details` list before rendering
- Default sort could remain as-is (API order) for backwards compatibility
- Apply sorting before table rendering and JSON output

## Acceptance criteria
- `--sort <column>` sorts output by the specified column
- `--reverse` flips the sort direction
- Works with both table and `--json` output
EOF
)"

create_issue "Add --label filter to include or exclude PRs by label" "$(cat <<'EOF'
## Summary
Filter the PR list by GitHub labels.

## Problem
Users often want to focus on specific categories of PRs (e.g. bugs, features) or exclude certain labels (e.g. `wip`, `on-hold`). There is currently no way to filter by label.

## Proposed behavior
- `--label bug` — only show PRs with the "bug" label
- `--exclude-label wip` — exclude PRs with the "wip" label
- Both flags repeatable for multiple labels
- Label matching should be case-insensitive

## Implementation notes
- Label data is already fetched in the PR detail response
- Add label filtering alongside existing `filter_pr_details` logic
- For `--label`, a PR must have *at least one* of the specified labels (OR logic)
- For `--exclude-label`, a PR is excluded if it has *any* of the specified labels

## Acceptance criteria
- `--label` and `--exclude-label` filter correctly
- Case-insensitive matching
- Works with both table and `--json` output
EOF
)"

create_issue "Add retry logic to GraphQL API requests" "$(cat <<'EOF'
## Summary
The GraphQL request path (`make_github_graphql_request`) lacks the retry logic that the REST path already has.

## Problem
`make_github_api_request` retries on transient 502/503/504 errors and connection resets with exponential backoff + jitter. However, `make_github_graphql_request` has no retry logic at all. A transient failure during the initial organization/repository fetch will crash the tool with no recovery.

## Proposed fix
- Apply the same retry pattern (bounded exponential backoff + jitter) to `make_github_graphql_request`
- Retry on `_RETRY_STATUSES` (502, 503, 504) and `ConnectionError`/`Timeout`
- Consider extracting shared retry logic into a decorator or helper to avoid duplication

## Additional cleanup
- `make_paginated_github_graphql_request()` is a `pass` stub (dead code) — remove it
- `make_paginated_github_api_requst` has a typo ("requst") — fix to "request"

## Acceptance criteria
- GraphQL requests retry on transient failures with backoff
- Existing REST retry behavior unchanged
- Dead code and typo cleaned up
- Tests cover GraphQL retry paths
EOF
)"

create_issue "Add --review-requested filter to show PRs awaiting your review" "$(cat <<'EOF'
## Summary
Add a flag to show only PRs where the authenticated user has been requested as a reviewer.

## Problem
A common workflow question is "what PRs do I need to review?" Currently users must scan the full table or use GitHub's web UI. `--mine-only` shows PRs *authored by* the user, but there is no equivalent for PRs *assigned to* the user for review.

## Proposed behavior
- `--review-requested` — show only PRs where the authenticated user is in the `requested_reviewers` list
- Can be combined with other filters (`--repo-filter`, `--ignore-author`, etc.)

## Implementation notes
- The `requested_reviewers` field is already returned in PR detail responses
- Reuse `get_authenticated_user_login()` (same as `--mine-only`)
- Add filtering in `filter_pr_details`

## Acceptance criteria
- `--review-requested` filters to PRs where the user is a requested reviewer
- Works with both table and `--json` output
- Combinable with existing filters
EOF
)"

create_issue "Support glob/regex patterns for --repo-filter" "$(cat <<'EOF'
## Summary
Improve repo filtering to support glob or regex patterns instead of simple substring matching.

## Problem
The current `--repo-filter` uses Python's `in` operator for substring matching (`if repo_filter in repo["name"]`). This leads to false positives — e.g. `-r app` matches "app-one", "happyapp", "mapper", "snapper". Users cannot precisely target repos.

## Proposed behavior
- Support glob-style patterns: `-r "app-*"` matches "app-one", "app-two" but not "happyapp"
- Support exact match: `-r "app"` matches only "app"
- Optionally support regex with a flag or prefix: `-r "regex:app-\d+"`
- Backwards compatibility: bare strings could default to glob with implicit `*` wildcards, or keep substring behavior with a deprecation warning

## Implementation notes
- Use `fnmatch.fnmatch` for glob matching
- Consider whether multiple `-r` flags should be supported (OR logic)

## Acceptance criteria
- Glob patterns work for repo filtering
- No false positive matches with common patterns
- Existing simple filters produce reasonable results (no silent breakage)
EOF
)"

create_issue "Add a config file for default CLI options" "$(cat <<'EOF'
## Summary
Add support for a TOML config file so users can set persistent defaults for CLI options.

## Problem
Users who always run with the same org/filter/ignore-author flags must repeat long command lines every time. Teams cannot share common defaults easily.

## Proposed behavior
- Load defaults from `~/.config/breakfast/config.toml` (user-level) and `.breakfast.toml` (project-level)
- Project-level config overrides user-level config
- CLI flags always override config file values
- New `--config <path>` flag for explicit config file
- New `--show-config` flag to display resolved configuration

## Example config
```toml
organization = "my-org"
repo-filter = "my-app"
ignore-author = ["dependabot[bot]", "renovate[bot]"]
age = true
mine-only = false
format = "table"
```

## Implementation notes
- Use `tomllib` (stdlib in Python 3.11+) — zero new dependencies
- Use Click's `default_map` context setting for clean integration
- Add `--no-*` counterparts for boolean flags so users can override config
- List values (ignore-author) merge between config and CLI; add `--no-ignore-author` to clear

## Detailed design
See `config-file-design.md` in the repo for full design document covering:
- File location precedence
- CLI vs config precedence rules
- Merge strategy by type
- Testing strategy

## Acceptance criteria
- Config loaded from standard paths
- CLI flags override config values
- `--config` and `--show-config` work correctly
- Missing/invalid config handled gracefully (warning, not crash)
- No new dependencies (uses stdlib tomllib)
EOF
)"

create_issue "Show CI/check status in the PR table" "$(cat <<'EOF'
## Summary
Add a column showing the CI/checks status for each PR.

## Problem
Whether CI is passing is one of the first things people check on a PR. Currently users must click through to GitHub to see this. Showing it in the table would make the output much more actionable.

## Proposed behavior
- Add a "Checks" column showing a summary: pass, fail, pending, none
- Optionally color-coded like other columns

## Implementation notes
- CI status is available via the GitHub REST API: `GET /repos/{owner}/{repo}/commits/{ref}/check-runs` or the combined status endpoint
- The PR detail response includes `statuses_url` which can be used to fetch status
- This adds an extra API call per PR — consider making it opt-in with `--checks` flag to avoid slowing down default runs
- Could also be fetched via GraphQL in the initial query to reduce API calls

## Acceptance criteria
- Check status displayed in table output
- Available in JSON output
- Opt-in flag to avoid extra API overhead by default
- Handles repos with no checks configured
EOF
)"

create_issue "Add --stale flag to highlight or filter old PRs" "$(cat <<'EOF'
## Summary
Add a `--stale N` option to highlight or filter PRs older than N days.

## Problem
Stale PRs that sit open for weeks or months are a common source of tech debt and review fatigue. Teams need a quick way to identify and triage them.

## Proposed behavior
- `--stale 30` — only show PRs older than 30 days
- Could also work as a highlight mode: show all PRs but visually mark stale ones
- Pairs naturally with the existing `--age` flag

## Implementation notes
- Reuse `get_pr_age_days()` which already calculates PR age
- Simple filter: `if get_pr_age_days(pr) >= stale_threshold`
- Consider whether `--stale` should imply `--age` (auto-enable the age column)

## Acceptance criteria
- `--stale N` filters to PRs older than N days
- Works with both table and `--json` output
- Combinable with other filters
EOF
)"

echo "All issues created!"
