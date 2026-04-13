# Usage

## Basic usage

Fetch and display open PRs for an organization, filtered by repo name:

```bash
breakfast -o my-org -r my-app
```

This queries all repositories in `my-org` whose name contains `my-app`, fetches open PR details, and displays them in a terminal table.

## Example output

```text
$ breakfast -o my-org -r platform
Fetching my-org PRs...🥐🍳...Done
Processing platform PRs...🥞🧇🍩...Done
+---------+----------------------------------+-----------------+--------+---------+-----------+-----------+------------+-----------------------+--------+
|         | Repo                             | PR Title        | Author | State   |   Files   |  Commits  |    +/-      |  Comments  | Mergeable?            | Link   |
+---------+----------------------------------+-----------------+--------+---------+-----------+-----------+------------+-----------------------+--------+
|       0 | platform-api                     | Add user search | alice  | open    |     3     |     1     |  +42/-10   |     0      | ✅ (clean)            | PR-142 |
|       1 | platform-api                     | Fix login bug   | bob    | open    |     1     |     1     |  +5/-2     |     3      | ✅ (clean)            | PR-138 |
|       2 | platform-ui                      | Update nav bar  | carol  | open    |    12     |     4     |  +280/-95  |     1      | ❌ (dirty)            | PR-87  |
+---------+----------------------------------+-----------------+--------+---------+-----------+-----------+------------+-----------------------+--------+
```

## Common workflows

### View PRs for a specific repo filter

```bash
breakfast -o my-org -r platform
```

### Ignore bot authors

Filter out automated PRs from bots:

```bash
breakfast -o my-org -r my-app \
  --ignore-author dependabot[bot] \
  --ignore-author renovate[bot]
```

### Show only your own PRs

```text
$ breakfast -o my-org -r platform --mine-only
Fetching my-org PRs...🥓...Done
Processing platform PRs...🍳...Done
+---------+----------------------------------+------------------------+--------+---------+-----------+-----------+------------+-----------------------+--------+
|         | Repo                             | PR Title               | Author | State   |   Files   |  Commits  |    +/-      |  Comments  | Mergeable?            | Link   |
+---------+----------------------------------+------------------------+--------+---------+-----------+-----------+------------+-----------------------+--------+
|       0 | platform-api                     | Add user search        | alice  | open    |     3     |     1     |  +42/-10   |     0      | ✅ (clean)            | PR-142 |
+---------+----------------------------------+------------------------+--------+---------+-----------+-----------+------------+-----------------------+--------+
```

### Show PR age

The `--age` column shows days since PR creation, colour-coded like other numeric columns:

```text
$ breakfast -o my-org -r platform --age
Fetching my-org PRs...🥐...Done
Processing platform PRs...🍩🧇...Done
+---------+----------------------------------+-----------------+--------+---------+-----------+-----------+------------+-----------+------+-----------------------+--------+
|         | Repo                             | PR Title        | Author | State   |   Files   |  Commits  |    +/-      |  Comments | Age  | Mergeable?            | Link   |
+---------+----------------------------------+-----------------+--------+---------+-----------+-----------+------------+-----------+------+-----------------------+--------+
|       0 | platform-api                     | Add user search | alice  | open    |     3     |     1     |  +42/-10   |     0     |   2  | ✅ (clean)            | PR-142 |
|       1 | platform-api                     | Fix login bug   | bob    | open    |     1     |     1     |  +5/-2     |     3     |  14  | ✅ (clean)            | PR-138 |
|       2 | platform-ui                      | Update nav bar  | carol  | open    |    12     |     4     |  +280/-95  |     1     |  31  | ❌ (dirty)            | PR-87  |
+---------+----------------------------------+-----------------+--------+---------+-----------+-----------+------------+-----------+------+-----------------------+--------+
```

### Get machine-readable output

Progress messages go to stderr, so JSON can be piped cleanly:

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
  ...
]
```

### Combine options

```bash
breakfast -o my-org -r my-app \
  --ignore-author dependabot[bot] \
  --age \
  --mine-only
```

### Use ASCII status labels for terminal compatibility

```bash
breakfast -o my-org -r platform --checks --status-style ascii
```

### Search PR titles

Find PRs whose title contains a keyword (case-insensitive):

```bash
breakfast -o my-org -r platform --search hotfix
breakfast -o my-org -r platform -s login
```

Or narrow down with a regex pattern:

```bash
breakfast -o my-org -r platform -s "^feat"         # starts with "feat"
breakfast -o my-org -r platform -s "fix|chore"     # either word
```

### Spot legendary PRs at a glance

Highlight PRs that have been open for 30+ days or have 100+ comments with a ⚔️:

```bash
breakfast -o my-org -r platform --legendary
```

Filter to show only legendary PRs:

```bash
breakfast -o my-org -r platform --legendary-only
```

### Speed up repeated runs with caching

PR results are cached to disk for 5 minutes by default. The second run is near-instant:

```bash
breakfast -o my-org -r platform          # fetches from API, writes cache
breakfast -o my-org -r platform          # served from cache (~instant)
breakfast -o my-org -r platform --no-cache   # always fetches fresh
```

Adjust the TTL with `--cache-ttl`:

```bash
breakfast -o my-org -r platform --cache-ttl 10m   # cache for 10 minutes
```

## How it works

1. **Check cache** - Looks for a recent on-disk cache for the `(organization, repo-filter)` pair; if found and within the TTL, skips steps 2–3 entirely
2. **Fetch repositories** - Uses the GitHub GraphQL API to paginate through all repositories in the organization
3. **Filter repos** - Keeps only repos whose name contains the `--repo-filter` substring
4. **Fetch PR details** - Uses the GitHub REST API to fetch full details for each open PR (parallelized for speed); writes results to disk cache
5. **Filter PRs** - Applies author filters (`--ignore-author`, `--mine-only`), title search (`--search`), and other filters
6. **Display** - Renders results as a terminal table or JSON
