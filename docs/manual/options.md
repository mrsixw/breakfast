# Options Reference

## Required options

### `--organization`, `-o`

The GitHub organization to query for pull requests.

```bash
breakfast -o my-org -r my-app
```

### `--repo-filter`, `-r`

Filter repositories by name substring. Only repos whose name contains this string are included.

```bash
breakfast -o my-org -r platform    # matches "platform-api", "my-platform", etc.
```

## Filtering options

### `--ignore-author`

Exclude PRs by author login (case-insensitive). Can be repeated for multiple authors.

```bash
breakfast -o my-org -r my-app \
  --ignore-author dependabot[bot] \
  --ignore-author renovate[bot]
```

Without `--ignore-author`, bot PRs appear in the output:

```
+---------+----------------+-------------------------------+------------------+---------+-------+---------+-------------+----------+--------------+--------+
|         | Repo           | PR Title                      | Author           | State   | Files | Commits |    +/-      | Comments | Mergeable?   | Link   |
+---------+----------------+-------------------------------+------------------+---------+-------+---------+-------------+----------+--------------+--------+
|       0 | platform-api   | Add user search               | alice            | open    |   3   |    1    |  +42/-10    |    0     | ✅ (clean)   | PR-142 |
|       1 | platform-api   | Bump lodash from 4.17 to 4.18 | dependabot[bot]  | open    |   1   |    1    |  +3/-3      |    0     | ✅ (clean)   | PR-141 |
|       2 | platform-api   | Fix login bug                 | bob              | open    |   1   |    1    |  +5/-2      |    3     | ✅ (clean)   | PR-138 |
+---------+----------------+-------------------------------+------------------+---------+-------+---------+-------------+----------+--------------+--------+
```

With `--ignore-author dependabot[bot]`, the bot PR is excluded:

```
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------+
|         | Repo           | PR Title        | Author | State   | Files | Commits |    +/-     | Comments | Mergeable?   | Link   |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------+
|       0 | platform-api   | Add user search | alice  | open    |   3   |    1    |  +42/-10   |    0     | ✅ (clean)   | PR-142 |
|       1 | platform-api   | Fix login bug   | bob    | open    |   1   |    1    |  +5/-2     |    3     | ✅ (clean)   | PR-138 |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------+
```

### `--mine-only`

Show only PRs authored by the currently authenticated GitHub user (determined from `GITHUB_TOKEN`).

```
$ breakfast -o my-org -r platform --mine-only
Fetching my-org PRs...🥐...Done
Processing platform PRs...🍳...Done
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------+
|         | Repo           | PR Title        | Author | State   | Files | Commits |    +/-     | Comments | Mergeable?   | Link   |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------+
|       0 | platform-api   | Add user search | alice  | open    |   3   |    1    |  +42/-10   |    0     | ✅ (clean)   | PR-142 |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------+
```

## Display options

### `--age`

Add an "Age" column showing the number of days since each PR was created. Displayed between "Comments" and "Mergeable?" columns.

```
$ breakfast -o my-org -r platform --age
Fetching my-org PRs...🥐...Done
Processing platform PRs...🍩🧇...Done
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+------+--------------+--------+
|         | Repo           | PR Title        | Author | State   | Files | Commits |    +/-     | Comments | Age  | Mergeable?   | Link   |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+------+--------------+--------+
|       0 | platform-api   | Add user search | alice  | open    |   3   |    1    |  +42/-10   |    0     |   2  | ✅ (clean)   | PR-142 |
|       1 | platform-api   | Fix login bug   | bob    | open    |   1   |    1    |  +5/-2     |    3     |  14  | ✅ (clean)   | PR-138 |
|       2 | platform-ui    | Update nav bar  | carol  | open    |  12   |    4    |  +280/-95  |    1     |  31  | ❌ (dirty)   | PR-87  |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+------+--------------+--------+
```

### `--json`

Output results as JSON instead of a terminal table. Progress messages are sent to stderr so JSON output can be piped cleanly.

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

See [Output Formats](output-formats.md) for full schema details and scripting examples.

### `--checks`

Show CI/check status for each PR. This is opt-in because it requires an additional API call per PR.

```
$ breakfast -o my-org -r platform --checks
Fetching my-org PRs...🥐...Done
Processing platform PRs...🍩🧇...Done
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+----------+--------------+--------+
|         | Repo           | PR Title        | Author | State   | Files | Commits |    +/-     | Comments | Checks   | Mergeable?   | Link   |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+----------+--------------+--------+
|       0 | platform-api   | Add user search | alice  | open    |   3   |    1    |  +42/-10   |    0     | ✅ pass  | ✅ (clean)   | PR-142 |
|       1 | platform-api   | Fix login bug   | bob    | open    |   1   |    1    |  +5/-2     |    3     | ❌ fail  | ✅ (clean)   | PR-138 |
|       2 | platform-ui    | Update nav bar  | carol  | open    |  12   |    4    |  +280/-95  |    1     | ⚠️ pending | ❌ (dirty)   | PR-87  |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+----------+--------------+--------+
```

Check status values:
- **pass** (green) - All check runs succeeded or were skipped
- **fail** (red) - One or more check runs failed, were cancelled, or timed out
- **pending** (yellow) - One or more check runs are still queued or in progress
- **none** (white) - No check runs configured for this PR

With `--json --checks`, a `"checks"` field is included in each PR object:

```json
{
  "repo": "platform-api",
  "title": "Add user search",
  "checks": "pass",
  ...
}
```

### `--approvals`

Show review approval status for each PR. This is opt-in because it requires an additional API call per PR.

```
$ breakfast -o my-org -r platform --approvals
Fetching my-org PRs...🥐...Done
Processing platform PRs...🍩🧇...Done
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------------+--------+
|         | Repo           | PR Title        | Author | State   | Files | Commits |    +/-     | Comments | Approved     | Mergeable?   | Link   |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------------+--------+
|       0 | platform-api   | Add user search | alice  | open    |   3   |    1    |  +42/-10   |    0     | ✅ approved  | ✅ (clean)   | PR-142 |
|       1 | platform-api   | Fix login bug   | bob    | open    |   1   |    1    |  +5/-2     |    3     | ❌ changes   | ✅ (clean)   | PR-138 |
|       2 | platform-ui    | Update nav bar  | carol  | open    |  12   |    4    |  +280/-95  |    1     | ⏳ pending   | ❌ (dirty)   | PR-87  |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------------+--------+
```

Approval values:
- **✅ approved** (green) — at least one reviewer has approved and no changes are requested
- **❌ changes** (red) — at least one reviewer has requested changes
- **⏳ pending** (yellow) — no qualifying reviews yet

The most recent review per reviewer is used, mirroring GitHub's own UI logic.

Can also be set in the config file:

```toml
approvals = true
```

With `--json --approvals`, an `"approval"` field is included in each PR object:

```json
{
  "repo": "platform-api",
  "title": "Add user search",
  "approval": "approved",
  ...
}
```

### `--status-style`

Choose how the `Checks`, `Approved`, and `Mergeable?` columns are rendered in table output.

```bash
breakfast -o my-org -r platform --checks --status-style ascii
```

Supported values:
- `emoji` - default whimsical output, such as `✅ pass`, `✅ approved`, and `❌ (dirty)`
- `ascii` - terminal-safe fallback, such as `pass`, `approved`, and `no (dirty)`

This is also available in config:

```toml
status-style = "ascii"
```

### Auto-fit to terminal width

When writing to an interactive terminal, breakfast automatically fits the table to the available width. No flags required — it just works.

The table is compressed progressively, in order of least impact:

1. **PR Title** is truncated first (or respects `--max-title-length` if set)
2. **Repo** name is trimmed
3. **Author** name is trimmed
4. **Mergeable?** reason is dropped (`"✅ (clean)"` → `"✅"`)
5. **Checks** label is dropped (`"✅ pass"` → `"✅"`)
5b. **Approved** label is dropped (`"✅ approved"` → `"✅"`)
6. **Comments** header is shortened to `"Cmt"`
6b. **Approved** header is shortened to `"Apr"`
7. Low-priority columns are dropped entirely: State, Commits, Files, +/-, Cmt, Age, Checks, Approved/Apr

Auto-fit is a no-op when output is piped or redirected (not a TTY), so `--json` and scripting workflows are unaffected.

### `--limit`

Cap the number of PRs displayed. Results are limited after all filtering is applied. There is no config file equivalent — this is intentionally a CLI-only flag.

```bash
breakfast -o my-org -r my-app --limit 10
```

### `--max-title-length`

Truncate PR titles to a maximum number of characters. Titles longer than the limit are cut and suffixed with `…`. When unset, titles are displayed in full.

```bash
breakfast -o my-org -r my-app --max-title-length 72
```

Example — without `--max-title-length`:

```
| Fix: #4362 - Redirect resolved even though allow_redirects is set to False causing exception for unsupported connection adapter | ...
```

With `--max-title-length 60`:

```
| Fix: #4362 - Redirect resolved even though allow_redir… | ...
```

Can also be set in the config file to apply to all runs:

```toml
max-title-length = 72
```

## Caching options

### `--cache-ttl`

How long PR results are cached on disk before a fresh fetch is made. Accepts a bare number of seconds or a human-friendly suffix: `30s`, `5m`, `2h`. Defaults to `300` (5 minutes).

```bash
breakfast -o my-org -r my-app --cache-ttl 10m   # cache for 10 minutes
breakfast -o my-org -r my-app --cache-ttl 3600   # cache for 1 hour (in seconds)
```

Can also be set in the config file:

```toml
cache-ttl = "5m"
```

The cache is stored in `~/.cache/breakfast/` (or `$XDG_CACHE_HOME/breakfast/`). Each `(organization, repo-filter)` pair gets its own cache file, keyed by a hash of those values.

### `--no-cache`

Skip reading and writing the disk cache entirely — always fetches fresh from the GitHub API.

```bash
breakfast -o my-org -r my-app --no-cache
```

Useful when you need up-to-the-minute data and don't want to wait for the TTL to expire. Note that CI check statuses (`--checks`) are always fetched fresh regardless of cache state.

### `--refresh`

Ignore the current cache for this run, fetch fresh data, and write the results back to the cache. Subsequent runs within the TTL will be served from the freshly updated cache.

```bash
breakfast -o my-org -r my-app --refresh
```

Unlike `--no-cache`, the cache is still updated — so `--refresh` is the right choice when you know something has changed and want the next run to be fast again. Use `--no-cache` only when you want to bypass caching entirely.

### `--refresh-prs`

Re-fetch PR details (comments, CI status, merge state) using the cached repo list, then write the fresh results back to the cache.

```bash
breakfast -o my-org -r my-app --refresh-prs
```

Faster than `--refresh` when you know the set of open PRs hasn't changed — for example, no PRs have been opened or closed, but you want to see updated review comments or merge status. The GraphQL discovery call is skipped; only the per-PR REST fetches are re-run.

| Flag | GraphQL cache | PR detail cache |
|---|---|---|
| *(none)* | read | read |
| `--refresh-prs` | read | skip, write fresh |
| `--refresh` | skip, write fresh | skip, write fresh |
| `--no-cache` | skip entirely | skip entirely |

## Update notifications

breakfast automatically checks for new versions once per day (cached for 24 hours in `~/.cache/breakfast/`). If a newer version is available, you'll see a message after the main output:

```
🍳 A fresh breakfast is ready! v0.10.0 → v0.11.0 — update at https://github.com/mrsixw/breakfast/releases/latest
```

The check is non-blocking and non-fatal — network failures are silently ignored. The notification is sent to stderr so it won't interfere with `--json` output piping.

To disable the update check:

```bash
# Via CLI flag
breakfast -o my-org -r my-app --no-update-check

# Via environment variable (useful in CI or scripts)
export BREAKFAST_NO_UPDATE_CHECK=1
```

## Other options

### `--version`

```
$ breakfast --version
breakfast, version 0.10.0
```

### `--help`

```
$ breakfast --help
Usage: breakfast [OPTIONS]

Options:
  --config TEXT                 Path to config file.
  --show-config                 Print the resolved config and exit.
  --init-config                 Generate a default config file and exit.
  -o, --organization TEXT       One or multiple organizations to report on
  -r, --repo-filter TEXT        Filter for specific repp(s)
  --ignore-author TEXT          Ignore PRs raised by one or more authors
                                (case-insensitive). Repeat for multiple
                                authors, e.g. --ignore-author
                                dependabot[bot].
  --no-ignore-author            Clear config defaults for ignore-author.
  --mine-only / --no-mine-only  Only include PRs authored by the currently
                                authenticated GitHub user.
  --age / --no-age              Include an age column showing PR age in days.
  --json / --no-json            Output results as JSON instead of a table.
                                Progress messages go to stderr.
  --checks / --no-checks        Include a checks column showing CI/check
                                status for each PR.
  --status-style [emoji|ascii]  Render status cells with emoji (default) or
                                ASCII labels.
  --limit INTEGER               Cap the number of PRs shown. Unset means show
                                all results.
  --max-title-length INTEGER    Truncate PR titles to this many characters.
                                Unset means no truncation.
  --no-update-check             Disable the automatic update check.
  --cache-ttl TEXT              How long to cache PR results (seconds, or
                                suffix: 5m, 2h, 30s). Default: 300.
  --no-cache                    Skip reading and writing the PR cache; always
                                fetch fresh.
  --refresh                     Ignore the cache for this run but write fresh
                                results back to it.
  --refresh-prs                 Re-fetch PR details using the cached repo list.
                                Faster than --refresh when only PR state has
                                changed.
  --version                     Show the version and exit.
  --help                        Show this message and exit.
```
