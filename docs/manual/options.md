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
|       0 | platform-api   | Add user search | alice  | open    |   3   |    1    |  +42/-10   |    0     | pass     | ✅ (clean)   | PR-142 |
|       1 | platform-api   | Fix login bug   | bob    | open    |   1   |    1    |  +5/-2     |    3     | fail     | ✅ (clean)   | PR-138 |
|       2 | platform-ui    | Update nav bar  | carol  | open    |  12   |    4    |  +280/-95  |    1     | pending  | ❌ (dirty)   | PR-87  |
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

## Configuration options

### `--config`

Specify an explicit path to a configuration file, bypassing the default locations (`.breakfast.toml` and `~/.config/breakfast/config.toml`).

```bash
breakfast --config /path/to/my-custom-config.toml
```

### `--show-config`

Print the fully resolved configuration (merged from config files and CLI flags) and exit. Useful for debugging precedence.

```bash
breakfast --show-config
```

### `--no-*` overrides

For boolean flags and list options, you can explicitly negate a configuration file default using the `--no-` prefix:
- `--no-age`: Disable the age column.
- `--no-mine-only`: Disable the mine-only filter.
- `--no-checks`: Disable the checks column.
- `--no-json`: Output as a table instead of JSON.
- `--no-ignore-author`: Clear all ignored authors loaded from the config.

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
  -o, --organization TEXT  One or multiple organizations to report on
  -r, --repo-filter TEXT   Filter for specific repp(s)
  --ignore-author TEXT     Ignore PRs raised by one or more authors
                           (case-insensitive). Repeat for multiple authors,
                           e.g. --ignore-author dependabot[bot].
  --mine-only              Only include PRs authored by the currently
                           authenticated GitHub user.
  --age                    Include an age column showing PR age in days.
  --json                   Output results as JSON instead of a table. Progress
                           messages go to stderr.
  --version                Show the version and exit.
  --help                   Show this message and exit.
```
