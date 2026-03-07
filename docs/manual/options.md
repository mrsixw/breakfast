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

### `--mine-only`

Show only PRs authored by the currently authenticated GitHub user (determined from `GITHUB_TOKEN`).

```bash
breakfast -o my-org -r my-app --mine-only
```

## Display options

### `--age`

Add an "Age" column showing the number of days since each PR was created. Displayed between "Comments" and "Mergeable?" columns.

```bash
breakfast -o my-org -r my-app --age
```

### `--json`

Output results as JSON instead of a terminal table. Progress messages are sent to stderr so JSON output can be piped cleanly.

```bash
breakfast -o my-org -r my-app --json | jq '.[].title'
```

See [Output Formats](output-formats.md) for details on the JSON schema.

## Other options

### `--version`

Display the installed version of breakfast.

```bash
breakfast --version
```

### `--help`

Show help text with all available options.

```bash
breakfast --help
```
