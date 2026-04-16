# Output Formats

## stdout and stderr

All data output — tables, JSON, and summary views — goes to **stdout**.
All progress messages, spinner emoji, warnings, and errors go to **stderr**.

This means every output format is safe to pipe or redirect independently:

```bash
breakfast -o my-org -r platform > prs.txt          # capture table only
breakfast -o my-org -r platform --json | jq '...'  # pipe JSON cleanly
```

The `format` config key accepts `"table"` (default) or `"json"`. Any other value
triggers a warning on stderr and falls back to `"table"`.

## Table output (default)

```text
$ breakfast -o my-org -r platform
Fetching my-org PRs...🥐🍳...Done
Processing platform PRs...🥞🧇🍩...Done
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------+
|         | Repo           | PR Title        | Author | State   | Files | Commits |    +/-     | Comments | Mergeable?   | Link   |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------+
|       0 | platform-api   | Add user search | alice  | open    |   3   |    1    |  +42/-10   |    0     | ✅ (clean)   | PR-142 |
|       1 | platform-api   | Fix login bug   | bob    | open    |   1   |    1    |  +5/-2     |    3     | ✅ (clean)   | PR-138 |
|       2 | platform-ui    | Update nav bar  | carol  | open    |  12   |    4    |  +280/-95  |    1     | ❌ (dirty)   | PR-87  |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------+
```

The default output is a colour-coded terminal table with the following columns:

| Column | Description |
| --- | --- |
| Repo | Repository name — clickable link to the repo on GitHub |
| PR Title | Pull request title |
| Author | GitHub login of the PR author — clickable link to their profile |
| State | PR state (typically "open") |
| Files | Number of changed files |
| Commits | Number of commits in the PR |
| +/- | Lines added (green) and deleted (red) |
| Comments | Number of review comments |
| Age | Days since PR creation (only with `--age`) |
| Checks | CI/check run status: pass, fail, pending, none (only with `--checks`) — clickable link to the PR's checks tab |
| Head Branch | Source branch the PR was raised from (only with `--head-branch`) — clickable link to the branch on GitHub |
| Base Branch | Target branch the PR merges into (only with `--base-branch`) — clickable link to the branch on GitHub |
| Mergeable? | Whether the PR can be merged cleanly |
| Link | Clickable link to the PR |

Use `--status-style ascii` if your terminal font renders the status emoji with uneven column widths.

### Colour coding

Numeric columns (Files, Commits, Comments, Age) are colour-graded:

- **Green**: < 10
- **Yellow**: 10-19
- **Orange**: 20-49
- **Red**: 50+

### Terminal hyperlinks

The "Link" column uses [OSC 8 terminal hyperlinks](https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda), supported by most modern terminals (iTerm2, GNOME Terminal, Windows Terminal, etc.). Click the link to open the PR in your browser.

## JSON output (`--json`)

With `--json`, output is a JSON array of objects.

### Schema

Each PR object contains:

```json
{
  "repo": "repository-name",
  "pr_number": 123,
  "title": "PR title",
  "author": "github-login",
  "url": "https://github.com/org/repo/pull/123",
  "state": "open",
  "draft": false,
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-20T14:00:00Z",
  "additions": 42,
  "deletions": 10,
  "changed_files": 3,
  "commits": 2,
  "review_comments": 1,
  "labels": ["bug", "priority-high"],
  "requested_reviewers": ["reviewer-login"]
}
```

### Full example

```text
$ breakfast -o my-org -r platform --json 2>/dev/null
[
  {
    "repo": "platform-api",
    "pr_number": 142,
    "title": "Add user search",
    "author": "alice",
    "url": "https://github.com/my-org/platform-api/pull/142",
    "state": "open",
    "draft": false,
    "created_at": "2026-03-05T10:30:00Z",
    "updated_at": "2026-03-06T14:00:00Z",
    "additions": 42,
    "deletions": 10,
    "changed_files": 3,
    "commits": 1,
    "review_comments": 0,
    "labels": [],
    "requested_reviewers": ["bob"]
  },
  {
    "repo": "platform-api",
    "pr_number": 138,
    "title": "Fix login bug",
    "author": "bob",
    "url": "https://github.com/my-org/platform-api/pull/138",
    "state": "open",
    "draft": false,
    "created_at": "2026-02-21T09:15:00Z",
    "updated_at": "2026-03-04T16:30:00Z",
    "additions": 5,
    "deletions": 2,
    "changed_files": 1,
    "commits": 1,
    "review_comments": 3,
    "labels": ["bug"],
    "requested_reviewers": []
  }
]
```

## Summary views (`--summarise-user-prs` / `--summarise-repo-prs`)

Summary views replace the PR table with a compact at-a-glance breakdown.
See the [Summary views](options.md#summary-views) section of the options
reference for full details, including colour coding and config keys.

### Piping and scripting

```bash
# List all PR titles
$ breakfast -o my-org -r platform --json 2>/dev/null | jq '.[].title'
"Add user search"
"Fix login bug"

# Count PRs per author
$ breakfast -o my-org -r platform --json 2>/dev/null | jq 'group_by(.author) | map({author: .[0].author, count: length})'
[
  { "author": "alice", "count": 1 },
  { "author": "bob", "count": 1 }
]

# Find PRs with no reviewers
$ breakfast -o my-org -r platform --json 2>/dev/null | jq '[.[] | select(.requested_reviewers | length == 0)]'
[
  {
    "repo": "platform-api",
    "pr_number": 138,
    "title": "Fix login bug",
    ...
  }
]
```
