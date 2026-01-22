#!/usr/bin/env bash
set -euo pipefail

version="$1"

if git rev-parse -q --verify "refs/tags/v${version}"; then
  git config user.name "github-actions[bot]"
  git config user.email "github-actions[bot]@users.noreply.github.com"
  git mkver patch >/dev/null
  version=$(python utils/read_version.py)
  git add pyproject.toml
  git commit -m "chore: bump version to ${version}"
  git push
fi

echo "${version}"
