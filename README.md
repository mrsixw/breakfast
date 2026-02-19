# breakfast
[![CI](https://github.com/mrsixw/breakfast/actions/workflows/ci.yml/badge.svg)](https://github.com/mrsixw/breakfast/actions/workflows/ci.yml)

Simple tool for pulling PRs you might be interested in.

## Usage
```bash
./breakfast --organization cisco-sbg --repo-filter foo
./breakfast --organization cisco-sbg --repo-filter foo --ignore-author dependabot[bot] --ignore-author renovate[bot]
./breakfast --organization cisco-sbg --repo-filter foo --mine-only
./breakfast --organization cisco-sbg --repo-filter foo --age
```

## Options
- `--organization`, `-o`: One or multiple organizations to report on.
- `--repo-filter`, `-r`: Filter for specific repo(s) by name substring.
- `--ignore-author`: Ignore PRs raised by one or more authors (case-insensitive). Repeat for multiple authors.
- `--mine-only`: Only include PRs authored by the currently authenticated GitHub user.
- `--age`: Add an `Age` column (days since PR creation) between `Comments` and `Mergeable?`.
