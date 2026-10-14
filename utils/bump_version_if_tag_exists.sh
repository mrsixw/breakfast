#!/usr/bin/env bash
set -euo pipefail

version="$1"

# Exit status when main has already moved past the commit this run was asked to
# release. Not a failure: see superseded below.
readonly SUPERSEDED=3

# superseded <sha> <branch> — whether <branch> on origin has moved past <sha>
# while still containing it.
#
# Each merge to main starts a run that ends here, pushing a version bump. Merge
# twice within a few minutes and the older run arrives after main has moved, so
# its push is rejected as a non-fast-forward. The newer run was started by a
# commit made on top of this one, so it releases both, and the older run has
# nothing left to do. Issue #495.
#
# Both halves matter. Moved alone could be a rewritten main that no longer has
# this commit, and then nobody is going to release it.
#
# This trusts that whatever moved main will lead to a release. Everything that
# lands on main is either a merge, which starts a run, or a bump this script
# pushed, whose run goes straight on to release. A hand-pushed [skip ci] commit
# would break that, and is not something this project does.
superseded() {
  local sha="$1" branch="$2" remote
  git fetch --quiet origin "${branch}" || return 1
  remote="$(git rev-parse FETCH_HEAD)" || return 1
  [[ -n "${remote}" && "${remote}" != "${sha}" ]] || return 1
  git merge-base --is-ancestor "${sha}" "${remote}"
}

if git rev-parse -q --verify "refs/tags/v${version}" >/dev/null; then
  branch_name="$(git symbolic-ref --quiet --short HEAD || true)"
  branch_name="${branch_name:-${GITHUB_HEAD_REF:-${GITHUB_REF_NAME:-}}}"

  if [[ -z "${branch_name}" ]]; then
    echo "Unable to determine branch name for release version bump" >&2
    exit 1
  fi

  run_sha="$(git rev-parse HEAD)"

  git config user.name "github-actions[bot]"
  git config user.email "github-actions[bot]@users.noreply.github.com"
  git mkver patch >/dev/null
  version=$(python utils/read_version.py)
  uv lock
  git add VERSION uv.lock
  # [skip ci]: the run pushing this has already tested the tree, and goes on to
  # build, release and install-check it. Another run would re-verify an
  # identical tree, live end-to-end suite and all.
  git commit -m "chore: bump version to ${version} [skip ci]" >/dev/null
  if ! git push origin "HEAD:${branch_name}"; then
    if superseded "${run_sha}" "${branch_name}"; then
      echo "${branch_name} has moved past ${run_sha}; leaving the release to the newer run" >&2
      exit "${SUPERSEDED}"
    fi
    echo "git push failed; version bump commit not pushed" >&2
    exit 1
  fi
fi

printf '%s\n' "$version"
