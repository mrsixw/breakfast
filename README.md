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
breakfast -o my-org -r my-app --ignore-author dependabot[bot] --ignore-author renovate[bot]
breakfast -o my-org -r my-app --mine-only
breakfast -o my-org -r my-app --age
breakfast -o my-org -r my-app --checks
breakfast -o my-org -r my-app --approvals
breakfast -o my-org -r my-app --checks --status-style ascii
breakfast -o my-org -r my-app --filter-state open
breakfast -o my-org -r my-app --filter-check fail --filter-check pending
breakfast -o my-org -r my-app --filter-approval approved
breakfast -o my-org -r my-app --json
breakfast -o my-org -r my-app --cache
breakfast -o my-org -r my-app --cache --refresh
breakfast -o my-org -r my-app --cache --refresh-prs
```

## Options

### Display
- `--organization`, `-o`: Organization to query for PRs.
- `--repo-filter`, `-r`: Filter repos by name substring.
- `--age`: Add an age column (days since creation).
- `--checks`: Add a checks column showing CI status (✅ pass / ❌ fail / ⚠️ pending).
- `--approvals`: Add an approvals column showing review status (✅ approved / ❌ changes / ⏳ pending).
- `--status-style`: Render status cells with `emoji` (default) or `ascii` labels.
- `--json`: Output as JSON instead of a table.
- `--limit`: Cap the number of PRs shown.
- `--max-title-length`: Truncate PR titles to this many characters.

### Filtering
- `--ignore-author`: Exclude PRs by author (case-insensitive, repeatable).
- `--no-ignore-author`: Clear `ignore-author` config defaults for this run.
- `--mine-only`: Show only your own PRs.
- `--filter-state`: Only show PRs with this state (`open`, `closed`). Repeatable.
- `--filter-check`: Only show PRs with this CI result (`pass`, `fail`, `pending`, `none`). Repeatable. Implies `--checks`.
- `--filter-approval`: Only show PRs with this review status (`approved`, `pending`, `changes`). Repeatable.

### Caching
- `--cache` / `--no-cache`: Enable disk cache (off by default). Set `cache = true` in config to make it permanent.
- `--cache-ttl`: How long to cache results (`300`, `5m`, `2h` etc). Default: 300s.
- `--refresh`: Bypass cache read, fetch fresh, write back. Requires `--cache`.
- `--refresh-prs`: Re-fetch PR details using cached repo list. Requires `--cache`.

### Other
- `--config`: Path to a config file.
- `--show-config`: Print resolved config and exit.
- `--init-config`: Generate a default config file.
- `--no-update-check`: Disable the automatic update check.
- `--version`: Show version.

## Documentation

- [User Manual](docs/manual/) - Installation, usage, options reference, output formats, and troubleshooting
- [Design Documents](docs/design/) - Technical designs for planned features
- [Contributing](CONTRIBUTING.md) - How to contribute to the project
