#!/usr/bin/env bats
#
# 🔭 utils/report_next_version.sh — says, before a merge, what version the
#    next release would carry.
#
# #417 was committed as `feat!:`, which is correct Conventional Commits and
# also an instruction to git-mkver to bump the major version. 0.107.1 became
# 1.0.0, and nobody saw it until the release had shipped. This script exists so
# that consequence is visible on the pull request, so the tests care most about
# whether a major jump is called out loudly enough to notice.

setup() {
  load 'helpers/common'
  common_setup

  VERSION_FILE="${BATS_TEST_TMPDIR}/VERSION"
  export VERSION_FILE
  printf '0.107.1\n' > "${VERSION_FILE}"

  # git answers one question here: what does mkver compute next? The real
  # binary is a Linux/i386-only download, so it never runs in these tests.
  stub git <<'STUB'
if [[ "$1" == "mkver" ]]; then
  [[ -n "${MKVER_FAILS:-}" ]] && { printf 'mkver: bad config\n' >&2; exit 1; }
  printf '%s\n' "${MKVER_NEXT:-0.107.2}"
  exit 0
fi
exit 0
STUB
}

@test "reports the current version and the one the next release would carry" {
  export MKVER_NEXT=0.108.0

  run "${REPO_ROOT}/utils/report_next_version.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "0.107.1"
  assert_output_contains "0.108.0"
}

@test "a major jump is called out, not just printed" {
  export MKVER_NEXT=1.0.0

  run "${REPO_ROOT}/utils/report_next_version.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "MAJOR"
}

@test "the major warning names what causes it, so the fix is obvious" {
  export MKVER_NEXT=1.0.0

  run "${REPO_ROOT}/utils/report_next_version.sh"

  assert_output_contains "BREAKING CHANGE"
  assert_output_contains "!"
}

@test "a minor bump is not announced as a major one" {
  export MKVER_NEXT=0.108.0

  run "${REPO_ROOT}/utils/report_next_version.sh"

  refute_output_contains "MAJOR"
}

@test "a patch bump is not announced as a major one" {
  export MKVER_NEXT=0.107.2

  run "${REPO_ROOT}/utils/report_next_version.sh"

  refute_output_contains "MAJOR"
}

@test "build metadata on mkver's answer is not mistaken for a version" {
  # Off a release branch, includeBuildMetaData is on and mkver appends
  # +branch.hash. The reported version must be the core, not the whole string.
  export MKVER_NEXT=1.0.0+HEAD.abc1234

  run "${REPO_ROOT}/utils/report_next_version.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "1.0.0"
  refute_output_contains "abc1234"
  assert_output_contains "MAJOR"
}

@test "a pre-release suffix is handled too" {
  export MKVER_NEXT=1.0.0-RC1

  run "${REPO_ROOT}/utils/report_next_version.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "MAJOR"
}

@test "it fails loudly when mkver cannot answer" {
  # An unparsable mkver.conf must redden the pull request, which is the whole
  # point of running this before the release job ever sees it.
  export MKVER_FAILS=1

  run "${REPO_ROOT}/utils/report_next_version.sh"

  [ "$status" -ne 0 ]
  assert_output_contains "could not"
}

@test "it fails when the version file is missing rather than inventing one" {
  rm -f "${VERSION_FILE}"

  run "${REPO_ROOT}/utils/report_next_version.sh"

  [ "$status" -ne 0 ]
}

@test "it writes the report to the step summary when Actions provides one" {
  export MKVER_NEXT=1.0.0
  summary="${BATS_TEST_TMPDIR}/summary.md"
  export GITHUB_STEP_SUMMARY="${summary}"

  run "${REPO_ROOT}/utils/report_next_version.sh"

  [ "$status" -eq 0 ]
  [ -f "${summary}" ]
  grep -q "1.0.0" "${summary}"
  grep -q "MAJOR" "${summary}"
}

@test "it does not need a step summary to work" {
  export MKVER_NEXT=0.108.0
  unset GITHUB_STEP_SUMMARY

  run "${REPO_ROOT}/utils/report_next_version.sh"

  [ "$status" -eq 0 ]
}
