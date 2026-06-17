# 🥐 breakfast

[![CI](https://github.com/mrsixw/breakfast/actions/workflows/ci.yml/badge.svg)](https://github.com/mrsixw/breakfast/actions/workflows/ci.yml)

![breakfast demo](docs/demo.gif)

The most important meal of your workday.

Breakfast is the first thing you should consume each morning — and open PRs are the first thing you should consume at the start of your workday. **breakfast** serves them up in a tasty terminal table so you can start your day right.

## Installation

```bash
curl -sSL https://raw.githubusercontent.com/mrsixw/breakfast/main/install.sh | bash
```

## Quick start

```bash
export GITHUB_TOKEN="ghp_your_token_here"
breakfast -o my-org -r my-app
```

## Usage

```bash
breakfast -o my-org -r my-app
breakfast -o my-org -o another-org -r platform
breakfast -o my-org:api -o another-org:platform
breakfast -o my-org -r my-app --ignore-author dependabot[bot] --ignore-author renovate[bot]
breakfast -o my-org -r my-app --mine-only
breakfast -o my-org -r my-app --age
breakfast -o my-org -r my-app --checks
breakfast -o my-org -r my-app --approvals
breakfast -o my-org -r my-app --checks --status-style ascii
breakfast -o my-org -r my-app --fetch-state all
breakfast -o my-org -r my-app --filter-state open
breakfast -o my-org -r my-app --filter-check fail --filter-check pending
breakfast -o my-org -r my-app --filter-approval approved
breakfast -o my-org -r my-app --label bug --label enhancement
breakfast -o my-org -r my-app --exclude-label wip
breakfast -o my-org -r my-app --filter-reviewer alice
breakfast -o my-org -r my-app --filter-stale 30
breakfast -o my-org -r my-app --filter-inactive 7
breakfast -o my-org -r my-app --search "hotfix"
breakfast -o my-org -r my-app --sort age
breakfast -o my-org -r my-app --sort comments --reverse
breakfast -o my-org -r my-app --format json
breakfast -o my-org -r my-app --format markdown
breakfast -o my-org -r my-app --format template --template "{repo}: {title} ({url})"
breakfast -o my-org -r my-app --summarise-user-prs
breakfast -o my-org -r my-app --summarise-repo-prs
breakfast -o my-org -r my-app --cache
breakfast -o my-org -r my-app --cache --refresh
breakfast -o my-org -r my-app --cache --refresh-prs
breakfast -o my-org -r my-app --legendary
breakfast -o my-org -r my-app --legendary-only
breakfast -o my-org -r my-app --filter-mergeable clean
breakfast -o my-org -r my-app --filter-mergeable clean --filter-approval approved
breakfast --completion bash
```

## Options

### Display

- `--organization`, `-o`: One or multiple organizations to query for PRs (repeatable). Supports scoped filters like `org:repo`.
- `--repo-filter`, `-r`: Filter repos by name substring or glob pattern. Repeatable.
- `--age`: Add an age column (days since creation).
- `--checks`: Add a checks column showing CI status (✅ pass / ❌ fail / ⚠️ pending).
- `--approvals`: Add an approvals column showing review status (✅ approved / ✅ 1/2 approvals / ❌ changes / ⏳ pending).
- `--head-branch`: Add a head branch column.
- `--base-branch`: Add a base branch column.
- `--status-style`: Render status cells with `emoji` (default) or `ascii` labels.
- `--limit`: Cap the number of PRs shown.
- `--max-title-length`: Truncate PR titles to this many characters.

### Output format

- `--format`: Output format: `table` (default), `json`, `markdown`, `csv`, `template`.
- `--template`: Format string for `--format template`. Available fields: `{repo}`, `{title}`, `{author}`, `{url}`, `{state}`, `{number}`, `{created_at}`, `{updated_at}`, `{additions}`, `{deletions}`, `{changed_files}`, `{commits}`, `{review_comments}`, `{labels}`, `{requested_reviewers}`.

### Filtering

- `--ignore-author`: Exclude PRs by author (case-insensitive, repeatable).
- `--no-ignore-author`: Clear `ignore-author` config defaults for this run.
- `--mine-only`: Show only your own PRs.
- `--no-drafts`: Hide draft PRs.
- `--drafts-only`: Show only draft PRs.
- `--fetch-state`: Which PR states to fetch from GitHub: `open` (default), `closed`, `merged`, `all`.
- `--filter-state`: Only show PRs with this state (`open`, `closed`, `draft`). Repeatable.
- `--filter-check`: Only show PRs with this CI result (`pass`, `fail`, `pending`, `none`). Repeatable. Implies `--checks`.
- `--filter-approval`: Only show PRs with this review status (`approved`, `pending`, `changes`). Repeatable.
- `--filter-mergeable`: Only show PRs with this mergeable status (`clean`, `conflict`, `unknown`). Repeatable — OR logic.
- `--label`: Only show PRs that have this label (case-insensitive, repeatable — OR logic).
- `--exclude-label`: Hide PRs that have this label (case-insensitive, repeatable).
- `--filter-reviewer`: Only show PRs with this user as a requested reviewer (case-insensitive, repeatable — OR logic).
- `--filter-stale`: Only show PRs older than N days.
- `--filter-inactive`: Only show PRs not updated in the last N days.
- `--search`, `-s`: Filter PRs by title (plain string or regex, case-insensitive).

### Sorting

- `--sort`: Sort by field: `repo` (default), `age`, `updated`, `author`, `comments`, `reviews`.
- `--reverse`: Reverse the sort order.

### Summary views

- `--summarise-user-prs`: Print a per-author PR count summary instead of the full table.
- `--summarise-repo-prs`: Print a per-repo PR count summary instead of the full table.

### Caching

- `--cache` / `--no-cache`: Enable disk cache (off by default). Set `cache = true` in config to make it permanent.
- `--cache-ttl`: How long to cache results (`300`, `5m`, `2h` etc). Default: 300s.
- `--refresh`: Bypass cache read, fetch fresh, write back. Requires `--cache`.
- `--refresh-prs`: Re-fetch PR details using cached repo list. Requires `--cache`.

### Legendary PRs ⚔️

- `--legendary` / `--no-legendary`: Append ⚔️ to the state of PRs with 100+ comments and open 30+ days.
- `--legendary-only`: Show only legendary PRs. Implies `--legendary`.

### Other

- `--completion`: Print shell completion script for `bash`, `zsh`, or `fish` and exit. Eval in your shell config (e.g. `eval "$(breakfast --completion bash)"`).
- `--config`: Path to a config file.
- `--show-config`: Print resolved config and exit.
- `--init-config`: Generate a default config file.
- `--no-update-check`: Disable the automatic update check.
- `--version`: Show version.

## Documentation

- [User Manual](docs/manual/) - Installation, usage, options reference, output formats, and troubleshooting
- [Design Documents](docs/design/) - Technical designs for planned features
- [Contributing](CONTRIBUTING.md) - How to contribute to the project
