#!/usr/bin/env bash
set -euo pipefail

version="$1"

# Named exit codes, shared with ci.yml. EXIT_SUPERSEDED means main has already
# moved past the commit this run was asked to release: not a failure, see
# superseded below.
# shellcheck source=SCRIPTDIR/exit_codes.sh
source "$(dirname "${BASH_SOURCE[0]}")/exit_codes.sh"

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
#
# <sha> is the commit this run was started for (run_sha, read before the bump
# commit was made), not the bump commit that just failed to push.
#
# Every "no" sends the caller down the EXIT_FAILURE path, so when in doubt this
# answers no: a wrong "no" is a red run someone reruns, but a wrong "yes" is a
# green run that silently released nothing.
#
# The `|| return 1` guards are load-bearing. The caller runs this as an `if`
# condition, so bash ignores `set -e` for every command in this function's
# body. Without them a failed fetch would carry on and read a stale FETCH_HEAD.
superseded() {
  local sha="$1" branch="$2" remote

  # 1. Ask origin where <branch> is now. The checkout this run started from is
  #    exactly what is out of date, so it cannot answer. Can't reach origin:
  #    no.
  git fetch --quiet origin "${branch}" || return 1
  remote="$(git rev-parse FETCH_HEAD)" || return 1

  # 2. Has it moved? If the tip is still <sha>, nobody else pushed, so the push
  #    failed for some other reason (auth, network, branch protection): no.
  [[ -n "${remote}" && "${remote}" != "${sha}" ]] || return 1

  # 3. Has it moved *forward*? <sha> must be an ancestor of the new tip, so our
  #    commit is still in its history. That is all git can prove; that a newer
  #    run will release it is the assumption stated above. Exits 0 if so, 1 if
  #    not (main was rewritten and our commit dropped), and 128 on a git error;
  #    both non-zero cases are a no.
  git merge-base --is-ancestor "${sha}" "${remote}"
}

if git rev-parse -q --verify "refs/tags/v${version}" >/dev/null; then
  branch_name="$(git symbolic-ref --quiet --short HEAD || true)"
  branch_name="${branch_name:-${GITHUB_HEAD_REF:-${GITHUB_REF_NAME:-}}}"

  if [[ -z "${branch_name}" ]]; then
    echo "Unable to determine branch name for release version bump" >&2
    exit "${EXIT_FAILURE}"
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
      exit "${EXIT_SUPERSEDED}"
    fi
    echo "git push failed; version bump commit not pushed" >&2
    exit "${EXIT_FAILURE}"
  fi
fi

printf '%s\n' "$version"
