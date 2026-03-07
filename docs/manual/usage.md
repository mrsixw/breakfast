# Usage

## Basic usage

Fetch and display open PRs for an organization, filtered by repo name:

```bash
breakfast -o my-org -r my-app
```

This queries all repositories in `my-org` whose name contains `my-app`, fetches open PR details, and displays them in a terminal table.

## Example output

```
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

```
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

```
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

```
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

## How it works

1. **Fetch repositories** - Uses the GitHub GraphQL API to paginate through all repositories in the organization
2. **Filter repos** - Keeps only repos whose name contains the `--repo-filter` substring
3. **Fetch PR details** - Uses the GitHub REST API to fetch full details for each open PR (parallelized for speed)
4. **Filter PRs** - Applies author filters (`--ignore-author`, `--mine-only`)
5. **Display** - Renders results as a terminal table or JSON
