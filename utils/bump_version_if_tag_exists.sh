#!/usr/bin/env bash
set -euo pipefail

version="$1"

if git rev-parse -q --verify "refs/tags/v${version}" >/dev/null; then
  branch_name="$(git symbolic-ref --quiet --short HEAD || true)"
  branch_name="${branch_name:-${GITHUB_HEAD_REF:-${GITHUB_REF_NAME:-}}}"

  if [[ -z "${branch_name}" ]]; then
    echo "Unable to determine branch name for release version bump" >&2
    exit 1
  fi

  git config user.name "github-actions[bot]"
  git config user.email "github-actions[bot]@users.noreply.github.com"
  git mkver patch >/dev/null
  version=$(python utils/read_version.py)
  git add pyproject.toml
  git commit -m "chore: bump version to ${version}" >/dev/null
  git push origin "HEAD:${branch_name}" >/dev/null
fi

printf '%s\n' "$version"
