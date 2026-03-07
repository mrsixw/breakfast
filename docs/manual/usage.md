# Usage

## Basic usage

Fetch and display open PRs for an organization, filtered by repo name:

```bash
breakfast -o my-org -r my-app
```

This queries all repositories in `my-org` whose name contains `my-app`, fetches open PR details, and displays them in a terminal table.

## Common workflows

### View PRs for a specific repo filter

```bash
breakfast -o my-org -r platform
```

### Ignore bot authors

```bash
breakfast -o my-org -r my-app \
  --ignore-author dependabot[bot] \
  --ignore-author renovate[bot]
```

### Show only your own PRs

```bash
breakfast -o my-org -r my-app --mine-only
```

### Show PR age

```bash
breakfast -o my-org -r my-app --age
```

### Get machine-readable output

```bash
breakfast -o my-org -r my-app --json
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
