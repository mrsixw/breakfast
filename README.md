# breakfast
Simple tool for pulling PRs you might be interested in.

## Usage
```bash
./breakfast --organization cisco-sbg --repo-filter foo
./breakfast --organization cisco-sbg --repo-filter foo --ignore-author dependabot[bot] --ignore-author renovate[bot]
```

## Options
- `--organization`, `-o`: One or multiple organizations to report on.
- `--repo-filter`, `-r`: Filter for specific repo(s) by name substring.
- `--ignore-author`: Ignore PRs raised by one or more authors (case-insensitive). Repeat for multiple authors.
