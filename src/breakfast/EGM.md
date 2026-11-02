# breakfast package

## Overview

The `breakfast` Python package is the whole CLI: a Click entry point that
lists open GitHub pull requests across one or more owners (orgs or users). It
merges command-line flags with TOML config, discovers PRs through GitHub
GraphQL search, fetches details, checks and approvals over REST and GraphQL
(optionally through a layered disk cache), filters and sorts them, and renders
them as a table, Markdown, CSV, JSON, a format template, or a per-author /
per-repo summary.

Intra-package imports (each arrow points from the importing module to the module
it imports; `constants.py`, `logger.py` and `xdg.py` are imported by most
modules and omitted for brevity):

```text
cli.py ──► api, cache, config, renderers, ui, updater
renderers.py ──► api, ui
config.py ──► api
updater.py ──► api (SECRET_GITHUB_TOKEN)
cache.py ──► (constants, logger, xdg only)
api.py ──► ui (emit_progress)
ui.py ──► (constants, logger, xdg only)
```

Every module except the empty `__init__.py` declares `__all__`; a leading `_`
means module-private. `tests/test_public_api.py` enforces `__all__` presence and
forbids cross-module private imports.

## Interface

### `cli.py` — entry point and orchestration

- `cli.py:breakfast` — `@click.group(invoke_without_command=True)` callback
  and the console-script entry point. Declares about 60 options (owner, repo,
  author, label, state, check, approval, mergeable, staleness filters; output
  format; optional columns; cache controls; sort; summaries) plus `--version`.
  The full list is in [the options manual](../../docs/manual/options.md).
- `cli.py:completions` — subcommand; prints a bash, zsh or fish completion
  script (`click.Choice(_SHELL_CHOICES)`).
- `cli.py:update` — subcommand; self-updates the running binary via
  `updater.perform_update(_current_executable_path())`.
- `cli.py:env_flag_is_set` — True when an env var is set to any non-empty
  value (no-color.org presence rule).
- `cli.py:finish_run` — end-of-run hook: update banner, holiday easter eggs,
  `--api-stats` debug summary.
- Not underscored but not in `__all__` (module-local helpers):
  `cli.py:Shell`, `cli.py:format_cache_age`, `cli.py:consolidate_org_specs`.

### `api.py` — GitHub transport and queries

- Requests: `make_github_api_request` (REST GET), `make_paginated_github_api_request`,
  `make_github_graphql_request` (GraphQL POST).
- PR discovery and detail: `get_github_prs`, `fetch_pr_detail`,
  `match_exclude_repos`.
- Status: `get_check_status`, `get_approval_status`, `get_approval_summary`,
  `get_review_data_batch`, `get_required_approving_review_count`.
- Identity and telemetry: `get_authenticated_user_login`, `get_api_stats`,
  `get_graphql_rate_limit`.
- Time helpers: `get_pr_age_days`, `get_pr_inactive_days`.
- Exceptions: `GitHubAuthenticationError`, `GitHubForbiddenError`,
  `GitHubGraphQLError`, `GitHubGraphQLResourceLimitError`,
  `GitHubRateLimitError`, `GitHubSecondaryRateLimitError`, `OwnerNotFoundError`.
- `api.py:SECRET_GITHUB_TOKEN` — resolved token, imported by `cli.py` and
  `updater.py`; `api.py:SECRET_GITHUB_TOKEN_VAR` — the env var it came from.
  Neither is in `__all__`.

### `cache.py` — JSON disk cache

- `RepositoryNamesCache` — per-owner repository-name list (`read`, `write`, `path`).
- Read and write pairs, one per layer: `read_pr_cache` / `write_pr_cache` (full PR
  details), `read_graphql_cache` / `write_graphql_cache` (PR URL list),
  `read_repo_pr_cache` / `write_repo_pr_cache` (per-repo details),
  `read_cached_user_login` / `write_cached_user_login`.
- Paths and keys: `cache_path`, `graphql_cache_path`, `repo_pr_cache_path`,
  `make_cache_key`.
- `parse_ttl` — `300`, `"30s"`, `"5m"`, `"2h"` to seconds.

### `config.py` — TOML configuration and filtering

- `load_config`, `generate_default_config`, `update_config`, `KNOWN_KEYS`.
- `parse_columns_config` — `columns` setting to `{name, header, align}` specs.
- `filter_pr_details` — applies every PR filter.
- `normalize_author_logins`.

### `renderers.py` — output formats

- `render_table`, `render_markdown`, `render_csv`, `render_json`,
  `render_template`.
- Cell helpers: `format_labels`, `format_reviewers`, `label_search_url`,
  `is_legendary`, `apply_header_style`.

### `ui.py` — terminal presentation

- Status cells: `format_approval_status`, `format_check_status`,
  `format_mergeable_status`, `format_pr_state`, `click_colour_grade_number`,
  `generate_terminal_url_anchor`.
- Progress and errors: `emit_progress`, `progress_heartbeat`, `error_exit`.
- Views: `render_pr_summary`, `render_colour_diagnostics`.
- Seasonal theming: `CALENDARS`, `apply_seasonal_colour`.
- Easter eggs: `is_christmas`, `is_steves_birthday`, `has_shown_holiday_gift`,
  `mark_holiday_gift_shown`, `get_random_pizza_recipe`, `render_pizza_recipe`,
  `get_random_cake_recipe`, `render_cake_recipe`.

### `updater.py` — release checks and self-update

- `check_for_update`, `get_latest_version`, `get_release_summary`,
  `perform_update`, `UpdateStatus` (`UPDATED`, `UP_TO_DATE`, `UNKNOWN`, `ERROR`).

### Support modules

- `xdg.py:get_cache_dir`, `get_config_dir`, `get_state_dir`, `get_config_paths`.
- `logger.py:logger` (the shared `"breakfast"` logger), `logger.py:configure`.
- `constants.py` — pure data, no underscore names, grouped by theme:
  - API and retries: `GITHUB_API_URL`, `GITHUB_GRAPHQL_URL`, `REQUEST_TIMEOUT`,
    `MAX_RETRIES`, `RETRY_STATUSES`, `SECONDARY_RATE_LIMIT_DEFAULT_WAIT`,
    `MAX_GRAPHQL_ERROR_TYPES`, `MAX_GRAPHQL_ERROR_MESSAGE_LENGTH`,
    `MAX_STORED_GRAPHQL_ERRORS`.
  - Search and batching: `SEARCH_PAGE_SIZE`, `SEARCH_RESULT_LIMIT`,
    `SEARCH_SLICE_TARGET`, `SEARCH_WORKERS`, `SEARCH_REPOS_PER_QUERY`,
    `SEARCH_MAX_REPO_QUERIES`, `SEARCH_EARLIEST_CREATED`, `REVIEW_BATCH_SIZE`,
    `REVIEW_BATCH_PAGE_SIZE`.
  - Progress: `RETRY_EMOJI`, `PROGRESS_HEARTBEAT_SECONDS`, `BREAKFAST_ITEMS`.
  - Cache: `REPOSITORY_NAMES_CACHE_TTL`, `TTL_SUFFIX_MAP`. `DEFAULT_CACHE_TTL`,
    `CACHE_DIR_ENV_VAR` and `CACHE_DISABLED_ENV_VAR` are defined but no module
    reads them (see #505).
  - Table: `COLUMN_DISPLAY_NAMES`, `HEADER_STYLES`, `HEADER_STYLE_CHOICES`,
    `DROPPABLE_COLUMNS`, `LEGENDARY_COMMENT_THRESHOLD`,
    `LEGENDARY_AGE_THRESHOLD_DAYS`, `LEGENDARY_EMOJI`.
  - Colour and holidays: `SEASONAL_PALETTES`, `PRIDE_RAINBOW`, `HOLI_RAINBOW`,
    and the per-year date tables (`DIWALI`, `EID_AL_ADHA`, `EID_AL_FITR`,
    `HANUKKAH_START`, `HOLI_DATES`, `MID_AUTUMN`, `PASSOVER_START`,
    `ROSH_HASHANAH`, `SUKKOT_START`).
  - Recipes: `PIZZA_RECIPES`, `CAKE_RECIPES`.

## Invariants

### Command flow (`cli.py:breakfast`)

- The subcommand guard (`if ctx.invoked_subcommand is not None: return`) runs
  before config loading, validation, the token check or any network call, so
  `completions` and `update` work without config or a token.
- Early exits run before `load_config`, in this order: `--colour-diagnostics`
  (0), an invalid `--search` regex (1), `--init-config` (0), `--update-config`
  (0, even when `update_config()` returns False on error).
- After the merge, in order: the summarise, refresh and cache-TTL checks (each
  exits 1), then `--show-config` (prints to stdout, exits 0), then the
  `--no-drafts` with `--drafts-only` conflict (1), then the owner guard (1,
  `"Owner must be provided via CLI (-o / --owner) or config file (owner)."`),
  then the token guard (1, `"GH_TOKEN or GITHUB_TOKEN not set in environment -
  exiting..."`). All of these run before any GitHub request.
- The checks that exit 1 are: `--summarise-user-prs` with
  `--summarise-repo-prs`; `--refresh` or `--refresh-prs` without the cache
  enabled; an invalid cache TTL (`cache.py:parse_ttl` raises `ValueError`).
  Click usage errors (a bad `Choice` or `IntRange` value, or an unknown option)
  exit 2.
- Integer config values bypass Click's `IntRange`, so `workers` and
  `max-title-length` from config go through `cli.py:_require_positive_int`
  (exits 1 on a bool, a non-integer or a value below 1).
- For tri-state options (`default=None`), a CLI value wins and the config
  value fills in when the flag is absent.
  - `-r`, `--filter-author` and `--label` replace the config list.
  - `exclude-repos`, `exclude-label` and `ignore-author` add to the config
    list; `--no-ignore-author` drops the config list.
  - Plain `is_flag` options (for example `no-drafts`, `include-archived`,
    `offline`, `api-stats`, the summaries, `sort-reverse`) are CLI OR config,
    so a config `true` cannot be turned off from the command line.
  - `--limit`, `--filter-state`, `--filter-check`, `--filter-approval`,
    `--filter-mergeable`, `--filter-reviewer`, `--filter-stale`,
    `--filter-inactive` and `--search` are CLI-only. The `limit` config key is
    accepted but never read.
- Output format priority: `--format`, `--json`, `--markdown`, `--template`,
  config `format`, config `template`, `table`.
- In the CLI, `NO_COLOR` and `BREAKFAST_NO_UPDATE_CHECK` are checked with
  `env_flag_is_set` (any non-empty value), not Click `envvar=`, because Click's
  bool converter rejects unknown values. `config.py:_colour_is_suppressed`
  instead tests `NO_COLOR is not None`, so an empty value turns off colour only
  in config-time messages.
- After the data is fetched: `filter_pr_details`, then sort (`_SORT_KEYS`), then
  `--legendary-only`, then `--limit`, then render, then `finish_run`.
  `--exclude-repo` is applied earlier, to the discovered URL list.
- These errors end the run with exit 1: `OwnerNotFoundError`,
  `GitHubForbiddenError`, GraphQL errors, and auth or rate-limit errors raised
  during discovery and the live detail fetch (through `_handle_auth_error` and
  `_handle_rate_limit`).
- Per-PR status lookups are more lenient. In the cache-hit checks path, an
  auth error becomes `none` and a `GitHubRateLimitError` is not caught
  (`cli.py:1939-1950`). `_approval_details_for` logs per-PR request errors
  and leaves the PR `pending`.
- `update` raises `click.ClickException` (exit 1) for `UpdateStatus.UNKNOWN`
  and `ERROR`.

### Cache layers

- The PR caches are opt-in (`--cache` or config `cache`).
  - `--offline` turns the cache on and reads Layer 1 even when it has expired
    (`read_pr_cache(..., ignore_ttl=True)`), whatever `--refresh` says.
    Offline mode also sets `no_update_check`.
  - With no cached data, `--offline` exits 1.
  - Two files are written regardless of `--cache`: `user.json`, after any
    online `/user` lookup, and `latest_version.json`, after any update check.
- Lookup order: Layer 1 full PR cache (`read_pr_cache`), Layer 2 GraphQL URL
  list (`read_graphql_cache`), Layer 2.5 per-repo details
  (`read_repo_pr_cache`), then a live fetch of whatever is left.
  - `--refresh` skips every layer, and `--refresh-prs` skips Layers 1 and 2.5.
  - Both still write the fresh results back, except in offline mode.
- If a `ConnectionError` or `Timeout` reaches the outer handler (in practice,
  during discovery), the run falls back to the full PR cache with
  `ignore_ttl=True`. It does this even when the cache is disabled, and then
  switches to offline mode.
  - Per-PR detail errors don't fall back to the cache. The URL goes into
    `failed_urls` and the run warns about it.
  - The full PR cache is never written in offline mode
    (`needs_cache_write and not offline_mode`).
- Cache keys are the first 16 hex characters of SHA-256 over the lower-cased
  `org:repo_filter` (`cache.py:make_cache_key`). An entry is fresh while
  `now(UTC) - fetched_at <= ttl`. There is no eviction.
- Every write in `cache.py` is atomic: write `<file>.tmp`, then `os.replace`
  (`cache.py:_atomic_write_text`). `updater.py:_write_version_cache` is not
  atomic (plain `write_text`).
- Read errors are treated as a miss. `read_cached_user_login` catches only
  `OSError`, `JSONDecodeError` and `KeyError`.
- `RepositoryNamesCache` defaults to `REPOSITORY_NAMES_CACHE_TTL` (24 h). With
  `refresh=True` it never reads, but it still writes.

### GitHub API (`api.py`)

- The token comes from `GH_TOKEN`, then `GITHUB_TOKEN`, and is read once at
  import (`_resolve_github_token_info`).
- REST and GraphQL make up to `MAX_RETRIES + 1` attempts. Statuses in
  `RETRY_STATUSES` and `ChunkedEncodingError`, `ConnectionError` or `Timeout`
  back off by `2**(attempt-1)` seconds plus up to 0.5 s of jitter. HTTP 401
  raises `GitHubAuthenticationError` straight away, with no retry.
- A primary rate limit (`X-RateLimit-Remaining == "0"`) raises
  `GitHubRateLimitError`. REST detects it only on 403; a REST 429 becomes a
  plain `HTTPError`. GraphQL detects it on 403 or 429.
- On GraphQL, a secondary limit pauses every worker together
  (`_throttle_until`, which only ever extends). If the limit still applies
  after the last attempt, it raises `GitHubSecondaryRateLimitError`.
- A GraphQL response containing `errors` raises `GitHubGraphQLError`, or
  `GitHubGraphQLResourceLimitError` when every error is
  `RESOURCE_LIMITS_EXCEEDED`.
- Searches always include `is:pr` and `sort:created-asc`, plus `archived:false`
  unless `--include-archived` is set (`_build_search_string`). A search with
  more than `SEARCH_SLICE_TARGET` results is split recursively by `created:`
  date range and run on `SEARCH_WORKERS` threads (`_search_in_created_slices`).
- Repo filters (`-r`):
  - The owner's repository names are listed first and grouped into
    `repo:` searches of `SEARCH_REPOS_PER_QUERY` each.
  - When that would mean more than `SEARCH_MAX_REPO_QUERIES` searches, a probe
    query decides whether a single owner-wide search is cheaper
    (`_search_scopes`).
  - The first search also checks that the owner exists through
    `repositoryOwner`, and raises `OwnerNotFoundError` if it does not.
- Batched GraphQL queries pass owners, repos and PR numbers as variables and
  never put them in the query text (`_review_batch_query`).
- Approval works like this (`_summarize_reviews`, `get_approval_summary`):
  - `reviewDecision` takes priority when GitHub returns it.
  - Otherwise only each reviewer's latest `APPROVED`, `CHANGES_REQUESTED` or
    `DISMISSED` review counts, and any `CHANGES_REQUESTED` makes the result
    `changes`.
  - When `reviewDecision` is `None` and branch protection gives a required
    count (`get_required_approving_review_count`), any status other than
    `changes` becomes `approved` if approvals ≥ required, otherwise `pending`.

### Config (`config.py`, `xdg.py`)

- Config search order, highest priority first: `./.breakfast.toml`, then
  `$XDG_CONFIG_HOME/breakfast/config.toml`, then `~/.breakfast.toml`
  (`xdg.py:get_config_paths`). Scalars from a higher-priority file win. Lists
  are concatenated (`load_config`).
- An explicit `--config` path that does not exist exits 1. A file that fails to
  parse is skipped with a warning. Unknown keys produce a warning with a "did
  you mean" suggestion, and the key is kept.
- `generate_default_config` never overwrites an existing file.
- `update_config` takes no arguments and ignores `--config`. It edits the
  first existing file from `get_config_paths()`, after writing a new
  timestamped `.bak.<YYYYmmdd-HHMMSS>` copy.
- Both functions print their status and error messages to stdout.
- `filter_pr_details` applies filters in a fixed order. `ignore_authors` wins
  over `filter_authors`. Label patterns are case-folded globs
  (`_label_matches`).
- An `XDG_*_HOME` override is used only when it is an absolute path
  (`xdg.py:_xdg_override`).

### Rendering and output streams

- Data goes to stdout: rendered output, `--show-config` and colour
  diagnostics. Progress, warnings and errors go to stderr: `ui.py:emit_progress`
  (writes under `_progress_lock`), `ui.py:error_exit` and `click.echo(err=True)`.
  The exception is the `--init-config` and `--update-config` messages, which go
  to stdout (`config.py`).
- The automatic birthday and Christmas gifts appear only when colour is on,
  print to stderr, and are shown once per year
  (`has_shown_holiday_gift` / `mark_holiday_gift_shown`, which writes through
  `<event>_gift.tmp`).
- `render_table` auto-fits to the terminal width only when stdout is a TTY. It
  works through a fixed sequence of steps (truncate the title, then other text
  columns, abbreviate headers and status cells, then drop `DROPPABLE_COLUMNS`
  in order) and stops at the first step that makes the table fit
  (`renderers.py:_auto_fit`).
- Width is measured ignoring ANSI and OSC 8 codes and using `wcwidth`.
  Truncation keeps colour and hyperlinks intact (`_visible_width`,
  `_truncate_formatted_text`).
- `render_template` checks the template before printing any row: it rejects
  positional fields and field widths over 10,000, and dry-runs the template
  against a probe PR.
- `progress_heartbeat` runs a daemon thread that is always stopped and joined
  in `finally`.

### Self-update (`updater.py`)

- Version checks are cached for 24 hours in `latest_version.json`
  (`_CACHE_TTL_SECONDS`). Versions are compared as zero-padded numeric tuples
  (`_is_newer`).
- `perform_update` refuses `.py` paths, downloads to `<exe>.new`, sets it to
  `chmod 0o755`, swaps it in with `os.replace`, and always removes the `.new`
  file.

## Side Effects

- **Network:** `api.github.com` REST (`/repos/{o}/{r}/pulls/{n}`, `/reviews`,
  `/commits/{sha}/check-runs`, `/commits/{sha}/status`,
  `/branches/{b}/protection/required_pull_request_reviews`, `/user`) and
  GraphQL (`search`, `repositoryOwner.repositories`, `reviewDecision`, batched
  reviews, `rateLimit`) [`api.py`]. Release lookup at
  `api.github.com/repos/mrsixw/breakfast/releases/latest`
  [`updater.py:get_latest_version`]; binary download from
  `github.com/mrsixw/breakfast/releases/latest/download/breakfast`
  [`updater.py:perform_update`].
- **Cache directory** (`$XDG_CACHE_HOME/breakfast` or `~/.cache/breakfast`):
  `prs_<key>.json`, `graphql_<key>.json`, `pr_repo_<key>.json`,
  `repos_<key>.json`, `user.json` [`cache.py`]; `latest_version.json`
  [`updater.py`]. Both modules resolve the directory once, at import time.
- **State directory** (`$XDG_STATE_HOME/breakfast` or
  `~/.local/state/breakfast`): `breakfast.log`, truncated on every run
  [`logger.py:configure`]; `<event>_gift.json` [`ui.py:mark_holiday_gift_shown`].
- **Config directory:** `config.toml` created [`config.py:generate_default_config`].
  The first existing search-path config is rewritten, and a new backup is
  created beside it [`config.py:update_config`].
- **Executable:** replaced in place [`cli.py:update` → `updater.py:perform_update`].
- **Environment reads:** `GH_TOKEN`, `GITHUB_TOKEN`, `NO_COLOR`,
  `BREAKFAST_NO_UPDATE_CHECK`, `XDG_CACHE_HOME`, `XDG_CONFIG_HOME`,
  `XDG_STATE_HOME`.
- **Threads:** `ThreadPoolExecutor` for PR detail, check and approval fetches
  [`cli.py`], and for search slices and review batches [`api.py`]. The
  heartbeat daemon thread [`ui.py:progress_heartbeat`].
- **Process-wide state:** API call counters [`api.py:_api_stats`], the shared
  GraphQL pause [`api.py:_throttle_until`], and `lru_cache` on branch
  protection [`api.py:get_required_approving_review_count`].

## Verification

- Run: `make test` (every test in `tests/` except the `e2e` marker)
- Run: `make e2e` for CLI behaviour, packaging or cache changes (builds
  `./breakfast` and runs it against real GitHub)
