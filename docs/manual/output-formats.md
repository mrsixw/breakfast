# Output Formats

## Table output (default)

The default output is a colour-coded terminal table with the following columns:

| Column | Description |
|--------|-------------|
| Repo | Repository name |
| PR Title | Pull request title |
| Author | GitHub login of the PR author |
| State | PR state (typically "open") |
| Files | Number of changed files |
| Commits | Number of commits in the PR |
| +/- | Lines added (green) and deleted (red) |
| Comments | Number of review comments |
| Age | Days since PR creation (only with `--age`) |
| Mergeable? | Whether the PR can be merged cleanly |
| Link | Clickable terminal hyperlink to the PR |

### Colour coding

Numeric columns (Files, Commits, Comments, Age) are colour-graded:
- **Green**: < 10
- **Yellow**: 10-19
- **Orange**: 20-49
- **Red**: 50+

### Terminal hyperlinks

The "Link" column uses [OSC 8 terminal hyperlinks](https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda), supported by most modern terminals (iTerm2, GNOME Terminal, Windows Terminal, etc.). Click the link to open the PR in your browser.

## JSON output (`--json`)

With `--json`, output is a JSON array of objects. Progress messages go to stderr.

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

### Piping and scripting

```bash
# List all PR titles
breakfast -o my-org -r my-app --json | jq '.[].title'

# Count PRs per author
breakfast -o my-org -r my-app --json | jq 'group_by(.author) | map({author: .[0].author, count: length})'

# Find PRs with no reviewers
breakfast -o my-org -r my-app --json | jq '[.[] | select(.requested_reviewers | length == 0)]'
```
