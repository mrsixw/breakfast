#!/usr/bin/env bats
#
# 🔖 utils/bump_version_if_tag_exists.sh — the release sanity check that bumps
#    the version when the tag it is about to cut already exists.
#
# It pushes commits, so the interesting question is not only "does it bump?" but
# "does it stay completely still when it should?".

setup() {
  load 'helpers/common'
  common_setup

  # A git stub with knobs: whether the tag exists, what branch HEAD is on, and
  # whether the push succeeds.
  stub git <<'STUB'
case "$1" in
  rev-parse)
    [[ -n "${GIT_TAG_EXISTS:-}" ]] && exit 0
    exit 1 ;;
  symbolic-ref)
    if [[ -n "${GIT_BRANCH:-}" ]]; then printf '%s\n' "${GIT_BRANCH}"; exit 0; fi
    exit 1 ;;
  push)
    [[ -n "${GIT_PUSH_FAILS:-}" ]] && exit 1
    exit 0 ;;
  *) exit 0 ;;
esac
STUB
  stub python <<'STUB'
printf '%s\n' "${BUMPED_VERSION:-9.9.9}"
STUB
  stub_silent uv
}

@test "prints the version untouched when the tag does not yet exist" {
  run "${REPO_ROOT}/utils/bump_version_if_tag_exists.sh" 1.2.3

  [ "$status" -eq 0 ]
  [ "$output" = "1.2.3" ]
}

@test "changes nothing at all when the tag does not exist" {
  # The whole point of the guard: a normal release must not acquire a stray
  # commit or a pushed branch.
  run "${REPO_ROOT}/utils/bump_version_if_tag_exists.sh" 1.2.3

  [ "$status" -eq 0 ]
  refute_called git "commit"
  refute_called git "push"
  refute_called git "mkver"
  refute_called uv
}

@test "checks for the tag under its v prefix" {
  run "${REPO_ROOT}/utils/bump_version_if_tag_exists.sh" 1.2.3

  assert_called git "refs/tags/v1.2.3"
}

@test "bumps, commits and pushes when the tag already exists" {
  export GIT_TAG_EXISTS=1 GIT_BRANCH=main BUMPED_VERSION=1.2.4

  run "${REPO_ROOT}/utils/bump_version_if_tag_exists.sh" 1.2.3

  [ "$status" -eq 0 ]
  assert_called git "mkver patch"
  assert_called git "add VERSION uv.lock"
  assert_called git "commit -m chore: bump version to 1.2.4"
  assert_called git "push origin HEAD:main"
  assert_called uv "lock"
}

@test "prints the bumped version, not the one it was given" {
  # Everything downstream tags and names the release from this stdout.
  export GIT_TAG_EXISTS=1 GIT_BRANCH=main BUMPED_VERSION=1.2.4

  run "${REPO_ROOT}/utils/bump_version_if_tag_exists.sh" 1.2.3

  [ "$output" = "1.2.4" ]
}

@test "commits as the actions bot rather than whoever ran it" {
  export GIT_TAG_EXISTS=1 GIT_BRANCH=main

  run "${REPO_ROOT}/utils/bump_version_if_tag_exists.sh" 1.2.3

  assert_called git "config user.name github-actions[bot]"
}

@test "falls back to GITHUB_HEAD_REF on a detached CI checkout" {
  # Actions checks out a detached HEAD, so symbolic-ref finds nothing.
  export GIT_TAG_EXISTS=1 GITHUB_HEAD_REF=feature-branch

  run "${REPO_ROOT}/utils/bump_version_if_tag_exists.sh" 1.2.3

  [ "$status" -eq 0 ]
  assert_called git "push origin HEAD:feature-branch"
}

@test "falls back to GITHUB_REF_NAME when there is no head ref either" {
  export GIT_TAG_EXISTS=1 GITHUB_REF_NAME=main

  run "${REPO_ROOT}/utils/bump_version_if_tag_exists.sh" 1.2.3

  [ "$status" -eq 0 ]
  assert_called git "push origin HEAD:main"
}

@test "refuses to guess when no branch can be determined" {
  export GIT_TAG_EXISTS=1

  run "${REPO_ROOT}/utils/bump_version_if_tag_exists.sh" 1.2.3

  [ "$status" -eq 1 ]
  assert_output_contains "Unable to determine branch name"
  refute_called git "commit"
}

@test "fails loudly when the push is rejected" {
  # A silent failure here leaves the tag and the VERSION file disagreeing on
  # the remote, which is precisely the state this script exists to prevent.
  export GIT_TAG_EXISTS=1 GIT_BRANCH=main GIT_PUSH_FAILS=1

  run "${REPO_ROOT}/utils/bump_version_if_tag_exists.sh" 1.2.3

  [ "$status" -eq 1 ]
  assert_output_contains "git push failed"
}
