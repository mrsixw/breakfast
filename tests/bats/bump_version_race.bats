#!/usr/bin/env bats
#
# 🏁 utils/bump_version_if_tag_exists.sh against a real git remote — the race
#    between two merges to main (issue #495).
#
# Each merge to main starts a CI run that ends by pushing a version bump. Merge
# twice within a few minutes and the older run reaches its push after main has
# moved, so the push is rejected as a non-fast-forward and main goes red, though
# the newer run goes on to release both merges.
#
# Whether main has moved *past* a commit, rather than somewhere else entirely,
# is a question about real git history, so these tests use real git: a bare
# repository stands in for GitHub, and a second clone for the other merge. Only
# git-mkver, python and uv are stubbed, since what they do is beside the point.

bats_require_minimum_version 1.5.0

setup() {
  load 'helpers/common'
  common_setup

  ORIGIN="${BATS_TEST_TMPDIR}/origin.git"
  RUN="${BATS_TEST_TMPDIR}/run"
  OTHER="${BATS_TEST_TMPDIR}/other"

  git init --quiet --bare --initial-branch=main "${ORIGIN}"
  git clone --quiet "${ORIGIN}" "${RUN}" 2>/dev/null
  identify "${RUN}"
  printf '1.2.3\n' > "${RUN}/VERSION"
  : > "${RUN}/uv.lock"
  git -C "${RUN}" add VERSION uv.lock
  git -C "${RUN}" commit --quiet -m "Merge pull request #1"
  git -C "${RUN}" tag v1.2.3
  git -C "${RUN}" push --quiet origin main --tags

  # The clone a CI run would have: the merge commit that triggered it.
  RUN_SHA="$(git -C "${RUN}" rev-parse HEAD)"

  git clone --quiet "${ORIGIN}" "${OTHER}" 2>/dev/null
  identify "${OTHER}"

  # `git mkver patch` runs git-mkver from PATH. The stub makes the bump it would.
  stub git-mkver <<'STUB'
printf '1.2.4\n' > VERSION
STUB
  stub python <<'STUB'
cat VERSION
STUB
  stub_silent uv

  export ORIGIN RUN OTHER RUN_SHA
}

# identify <clone> — a commit identity, since HOME is redirected and there is
# no global git config to fall back on.
identify() {
  git -C "$1" config user.name "Test"
  git -C "$1" config user.email "test@example.com"
}

# merge_elsewhere <message> — another merge lands on main while this run is
# still busy.
merge_elsewhere() {
  git -C "${OTHER}" pull --quiet origin main
  printf '%s\n' "$1" >> "${OTHER}/CHANGES"
  git -C "${OTHER}" add CHANGES
  git -C "${OTHER}" commit --quiet -m "$1"
  git -C "${OTHER}" push --quiet origin main
}

origin_main() { git -C "${ORIGIN}" rev-parse main; }
origin_subject() { git -C "${ORIGIN}" log -1 --format=%s main; }

bump() {
  cd "${RUN}"
  run --separate-stderr "${REPO_ROOT}/utils/bump_version_if_tag_exists.sh" 1.2.3
}

@test "pushes the bump when main is still where the run started" {
  bump

  [ "$status" -eq 0 ]
  [ "$output" = "1.2.4" ]
  [ "$(origin_subject)" = "chore: bump version to 1.2.4 [skip ci]" ]
}

@test "stands down when a newer merge has moved main past this run" {
  merge_elsewhere "Merge pull request #2"
  local newer
  newer="$(origin_main)"

  bump

  # Not 1: the newer run releases this commit along with its own, so nothing
  # is wrong and main must not go red.
  [ "$status" -eq 3 ]
  [[ "$stderr" == *"main has moved past ${RUN_SHA}"* ]]
  # And it really did stand down: main is exactly where the other merge left it.
  [ "$(origin_main)" = "${newer}" ]
}

@test "prints no version when it stands down, so nothing downstream can release" {
  merge_elsewhere "Merge pull request #2"

  bump

  [ "$status" -eq 3 ]
  [ -z "$output" ]
}

@test "stands down when a newer run has already pushed its own bump" {
  # The other order: the newer run got to its push first. Its release covers
  # this commit, because the newer merge was made on top of it.
  merge_elsewhere "Merge pull request #2"
  merge_elsewhere "chore: bump version to 1.2.4 [skip ci]"

  bump

  [ "$status" -eq 3 ]
}

@test "fails loudly when main was rewritten rather than advanced" {
  # main moved, but no longer contains this commit, so no newer run is going to
  # release it. That is a real problem and must not be mistaken for a race.
  git -C "${OTHER}" checkout --quiet --orphan rewritten
  git -C "${OTHER}" commit --quiet --allow-empty -m "Unrelated history"
  git -C "${OTHER}" push --quiet --force origin rewritten:main

  bump

  [ "$status" -eq 1 ]
  [[ "$stderr" == *"git push failed"* ]]
}
