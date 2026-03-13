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
breakfast -o my-org -r my-app --checks --status-style ascii
breakfast -o my-org -r my-app --json
```

## Options
- `--organization`, `-o`: Organization to query for PRs.
- `--repo-filter`, `-r`: Filter repos by name substring.
- `--ignore-author`: Exclude PRs by author (case-insensitive, repeatable).
- `--mine-only`: Show only your own PRs.
- `--age`: Add an age column (days since creation).
- `--checks`: Add a checks column showing CI status (pass/fail/pending/none).
- `--status-style`: Render status cells with emoji (default) or ASCII labels.
- `--json`: Output as JSON instead of a table.
- `--version`: Show version.

## Documentation

- [User Manual](docs/manual/) - Installation, usage, options reference, output formats, and troubleshooting
- [Design Documents](docs/design/) - Technical designs for planned features
- [Contributing](CONTRIBUTING.md) - How to contribute to the project
