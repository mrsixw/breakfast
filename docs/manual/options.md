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

### `--filter-state`

Only show PRs with a specific state. Accepted values: `open`, `closed`. Repeat the flag to match multiple states.

```bash
breakfast -o my-org -r my-app --filter-state open                          # open PRs only
breakfast -o my-org -r my-app --filter-state open --filter-state closed    # both states
```

### `--filter-check`

Only show PRs whose CI check result matches the given value. Accepted values: `pass`, `fail`, `pending`, `none`. Repeat the flag to match multiple results. Automatically enables the `--checks` column.

```bash
breakfast -o my-org -r my-app --filter-check fail                        # failing checks only
breakfast -o my-org -r my-app --filter-check fail --filter-check pending  # failing or in-progress
```

### `--filter-approval`

Only show PRs with a specific review approval status. Accepted values: `approved`, `pending`, `changes`. Repeat the flag to match multiple statuses.

```bash
breakfast -o my-org -r my-app --filter-approval approved                           # fully approved PRs
breakfast -o my-org -r my-app --filter-approval changes                            # PRs with changes requested
breakfast -o my-org -r my-app --filter-approval pending --filter-approval changes  # needs attention
```

> **Note:** Review and check statuses are cached alongside PR details, so repeated runs with these flags skip redundant API calls.

### `--search`, `-s`

Filter PRs by title. Accepts a plain string or a regular expression pattern; matching is always **case-insensitive**.

```bash
breakfast -o my-org -r platform --search hotfix         # plain string
breakfast -o my-org -r platform -s "^feat"              # regex: titles starting with "feat"
breakfast -o my-org -r platform -s "fix|chore"          # regex: either word
```

If no PRs match the pattern, a friendly message is shown:

```
🔍 No PRs matched 'hotfix'
```

If the pattern is not valid regex, breakfast exits immediately with an error:

```
Error: --search pattern is not valid regex: unterminated character set at position 0
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

### `--no-drafts`

Exclude draft PRs from results. Useful when you only want to review PRs that are ready for review.

```bash
breakfast -o my-org -r platform --no-drafts
```

Can also be set in the config file:

```toml
no-drafts = true
```

### `--drafts-only`

Show only draft PRs. Useful for checking what's still in progress across your org.

```bash
breakfast -o my-org -r platform --drafts-only
```

`--no-drafts` and `--drafts-only` are mutually exclusive — using both together is an error.

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
|       2 | platform-ui    | Update nav bar  | carol  | open    |  12   |    4    |  +280/-95  |    1     | ⏳ review required | ❌ (dirty)   | PR-87  |
+---------+----------------+-----------------+--------+---------+-------+---------+------------+----------+--------------+--------------+--------+
```

Approval values:
- **✅ approved** (green) — GitHub reports the PR as approved for merge
- **❌ changes** (red) — at least one reviewer has requested changes
- **⏳ review required** (yellow) — GitHub still requires more review before merge

GitHub's review decision is used when available so repos that require multiple
approvals do not show a misleading green approval after only one review.

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

### `--legendary`

Mark legendary PRs with a ⚔️ appended to their **State** column. A PR earns legendary status if it meets **both** of these criteria:

- **100 or more total comments** (PR-level comments + inline review comments combined)
- **Open for 30 or more days**

Off by default. Enable with `--legendary`:

```bash
breakfast -o my-org -r platform --legendary
```

Example output with a legendary PR:

```
+---------+----------------+---------------------------+--------+-----------+-------+---------+----------+----------+--------------+--------+
|         | Repo           | PR Title                  | Author | State     | Files | Commits |   +/-    | Comments | Mergeable?   | Link   |
+---------+----------------+---------------------------+--------+-----------+-------+---------+----------+----------+--------------+--------+
|       0 | platform-api   | Add user search           | alice  | open      |   3   |    1    | +42/-10  |    0     | ✅ (clean)   | PR-142 |
|       1 | platform-api   | The PR that time forgot   | bob    | open ⚔️   |  28   |   17    | +980/-40 |   134    | ✅ (clean)   | PR-41  |
+---------+----------------+---------------------------+--------+-----------+-------+---------+----------+----------+--------------+--------+
```

Can also be set in the config file to always highlight legends:

```toml
legendary = true
```

### `--legendary-only`

Show **only** legendary PRs — those with 100+ comments **and** open 30+ days. Non-legendary PRs are filtered out entirely. Implies `--legendary` (the ⚔️ marker is always shown when this filter is active).

```bash
breakfast -o my-org -r platform --legendary-only
```

Can also be set in the config file:

```toml
legendary-only = true
```

### Auto-fit to terminal width

When writing to an interactive terminal, breakfast automatically fits the table to the available width. No flags required — it just works.

The table is compressed progressively, in order of least impact:

1. **PR Title** is truncated first (or respects `--max-title-length` if set)
2. **Repo** name is trimmed
3. **Author** name is trimmed
4. **Mergeable?** reason is dropped (`"✅ (clean)"` → `"✅"`)
4b. **Mergeable?** header is shortened to `"Mrg"`
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

### `--workers`

Number of parallel workers used to fetch PR details, check statuses, and approval statuses. Defaults to `64`. Lower values reduce API concurrency (useful if you're hitting rate limits); higher values may speed things up on very large organisations.

```bash
breakfast -o my-org -r my-app --workers 16
```

Can also be set in the config file:

```toml
workers = 16
```

## Caching options

The disk cache is **off by default**. Enable it with `--cache` or `cache = true` in config. Once enabled, results are stored in `~/.cache/breakfast/` (or `$XDG_CACHE_HOME/breakfast/`) and reused until the TTL expires.

### `--cache` / `--no-cache`

Enable or disable the disk cache. Off by default. Use `--cache` to turn it on for a single run, or set `cache = true` in config to make it permanent. `--no-cache` overrides `cache = true` in config for that run.

```bash
breakfast -o my-org -r my-app --cache       # enable cache for this run
breakfast -o my-org -r my-app --no-cache    # disable cache even if set in config
```

Can also be set in the config file:

```toml
cache = true
```

### `--cache-ttl`

How long cached PR results are considered fresh. Accepts a bare number of seconds or a human-friendly suffix: `30s`, `5m`, `2h`. Defaults to `300` (5 minutes). Only relevant when caching is enabled.

```bash
breakfast -o my-org -r my-app --cache --cache-ttl 10m   # cache for 10 minutes
breakfast -o my-org -r my-app --cache --cache-ttl 3600   # cache for 1 hour
```

Can also be set in the config file:

```toml
cache-ttl = "5m"
```

### `--refresh`

Fetch fresh data and write it to the cache, ignoring whatever is already cached. Requires `--cache` (or `cache = true` in config) — exits with an error if the cache is not enabled. Subsequent runs within the TTL will be served from the freshly updated cache.

```bash
breakfast -o my-org -r my-app --cache --refresh
```

### `--refresh-prs`

Re-fetch PR details (comments, CI status, merge state) using the cached repo list, then write the fresh results back to the cache. Requires `--cache` (or `cache = true` in config) — exits with an error if the cache is not enabled. Faster than `--refresh` when you know the set of open PRs hasn't changed.

```bash
breakfast -o my-org -r my-app --cache --refresh-prs
```

| Flag | Cache active? | GraphQL cache | PR detail cache |
|---|---|---|---|
| *(none)* | no | skip | skip |
| `--cache` | yes | read | read |
| `--cache --refresh-prs` | yes | read | skip, write fresh |
| `--cache --refresh` | yes | skip, write fresh | skip, write fresh |
| `--no-cache` | no (override) | skip | skip |

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
  --config TEXT                   Path to config file.
  --show-config                   Print the resolved config and exit.
  --init-config                   Generate a default config file and exit.
  -o, --organization TEXT         One or multiple organizations to report on
  -r, --repo-filter TEXT          Filter for specific repp(s)
  --ignore-author TEXT            Ignore PRs raised by one or more authors
                                  (case-insensitive). Repeat for multiple
                                  authors, e.g. --ignore-author
                                  dependabot[bot].
  --no-ignore-author              Clear config defaults for ignore-author.
  --mine-only / --no-mine-only    Only include PRs authored by the currently
                                  authenticated GitHub user.
  --no-drafts                     Exclude draft PRs from results.
  --drafts-only                   Show only draft PRs.
  --age / --no-age                Include an age column showing PR age in days.
  --json / --no-json              Output results as JSON instead of a table.
                                  Progress messages go to stderr.
  --checks / --no-checks          Include a checks column showing CI/check
                                  status for each PR.
  --approvals / --no-approvals    Include an approvals column showing review
                                  approval status for each PR.
  --status-style [emoji|ascii]    Render status cells with emoji (default) or
                                  ASCII labels.
  --limit INTEGER                 Cap the number of PRs shown. Unset means
                                  show all results.
  --max-title-length INTEGER      Truncate PR titles to this many characters.
                                  Unset means no truncation.
  --no-update-check               Disable the automatic update check.
  --cache / --no-cache            Enable disk cache for PR results. Off by
                                  default; use --cache or set cache = true in
                                  config.
  --cache-ttl TEXT                How long to cache PR results (seconds, or
                                  suffix: 5m, 2h, 30s). Default: 300.
  --refresh                       Ignore the cache for this run but write
                                  fresh results back to it. Requires --cache
                                  or cache = true in config.
  --refresh-prs                   Re-fetch PR details using the cached repo
                                  list. Faster than --refresh when only PR
                                  state has changed. Requires --cache or
                                  cache = true in config.
  --legendary / --no-legendary    Append ⚔️ to the state of PRs with 100+
                                  comments or open 30+ days. Off by default.
  --legendary-only                Show only legendary PRs (100+ comments or
                                  open 30+ days). Implies --legendary.
  --version                       Show the version and exit.
  --help                          Show this message and exit.
```
