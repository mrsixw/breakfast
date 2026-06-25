# Output Formats

## stdout and stderr

All data output — tables, JSON, Markdown, CSV, and summary views — goes to **stdout**.
All progress messages, spinner emoji, warnings, and errors go to **stderr**.

This means every output format is safe to pipe or redirect independently:

```bash
breakfast -o my-org -r platform > prs.txt                    # capture table only
breakfast -o my-org -r platform --json | jq '...'            # pipe JSON cleanly
breakfast -o my-org -r platform --format markdown > prs.md   # capture Markdown
breakfast -o my-org -r platform --format csv > prs.csv       # capture CSV
```

The `format` config key accepts `"table"` (default), `"json"`, `"markdown"`, or `"csv"`.
Any other value triggers a warning on stderr and falls back to `"table"`.

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
| Reviewers | Requested reviewers for the PR (only with `--reviewers`) |
| Labels | Labels applied to the PR (only with `--show-labels`) |
| Mergeable? | Whether the PR can be merged cleanly. `✅` means truly ready (`clean`); `⚠️` means no conflicts but not ready (`behind`, `unstable`, or `blocked`); `❌` means conflicts exist. Also shows `🏁 merged`, `🚫 closed`, or `⏳ computing` as appropriate |
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

## Markdown output (`--format markdown`)

With `--format markdown`, output is a GitHub-flavoured Markdown table — ready to paste into PR descriptions, issue comments, Confluence pages, or any Markdown renderer.

```text
$ breakfast -o my-org -r platform --format markdown 2>/dev/null
| Repo         | PR Title        | Author | State | Files | Commits | +/-       | Comments | Mergeable?  | Link                                                |
|---|---|---|---|---|---|---|---|---|---|
| [platform-api](https://github.com/my-org/platform-api) | Add user search | [alice](https://github.com/alice) | open  | 3     | 1       | +42/-10   | 0        | ✅ (clean)  | [PR-142](https://github.com/my-org/platform-api/pull/142) |
| [platform-api](https://github.com/my-org/platform-api) | Fix login bug   | [bob](https://github.com/bob)   | open  | 1     | 1       | +5/-2     | 3        | ✅ (clean)  | [PR-138](https://github.com/my-org/platform-api/pull/138) |
```

- ANSI colour codes are stripped — Markdown renderers don't support them.
- OSC 8 terminal hyperlinks are converted to `[text](url)` Markdown links.
- Optional columns (`--age`, `--checks`, `--approvals`, `--head-branch`, `--base-branch`, `--reviewers`, `--show-labels`) are included when their flags are set.
- Progress messages still go to stderr, so the output can be redirected cleanly.

## CSV output (`--format csv`)

With `--format csv`, output is RFC 4180-compliant CSV — ready to import into Excel, Google Sheets, or any tool that accepts CSV.

```text
$ breakfast -o my-org -r platform --format csv 2>/dev/null
repo,pr_number,title,author,url,state,draft,created_at,updated_at,additions,deletions,changed_files,commits,review_comments,labels,requested_reviewers
platform-api,142,Add user search,alice,https://github.com/my-org/platform-api/pull/142,open,False,2026-03-05T10:30:00Z,2026-03-06T14:00:00Z,42,10,3,1,0,,bob
platform-api,138,Fix login bug,bob,https://github.com/my-org/platform-api/pull/138,open,False,2026-02-21T09:15:00Z,2026-03-04T16:30:00Z,5,2,1,1,3,bug,
```

- Header row is always present.
- ANSI colour codes are stripped — all values are plain text.
- Multi-value fields (`labels`, `requested_reviewers`) are joined with `|` within the cell.
- Optional columns (`--age`, `--checks`, `--approvals`) are appended when their flags are set.
- Progress messages still go to stderr, so the output can be redirected cleanly.
- `format = "csv"` in `config.toml` sets CSV as the persistent default.

### Optional columns in CSV

| Flag | Added column(s) |
| --- | --- |
| `--age` | `age_days` |
| `--checks` | `checks` |
| `--approvals` | `approval`, `approval_current`, `approval_required` |

### Shell examples

```bash
# Import to Google Sheets or Excel
breakfast -o my-org -r platform --format csv 2>/dev/null > prs.csv

# Count PRs per author with awk
breakfast -o my-org -r platform --format csv 2>/dev/null | awk -F, 'NR>1 {print $4}' | sort | uniq -c

# Filter with csvkit
breakfast -o my-org -r platform --format csv 2>/dev/null | csvgrep -c author -m alice
```

## JSON output (`--json` / `--format json`)

With `--format json` (or the `--json` alias), output is a JSON array of objects.

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
