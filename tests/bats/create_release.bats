#!/usr/bin/env bats
#
# 🚀 utils/create_release.sh — the one script that publishes something the
#    public can download, so what it hands `gh` matters.

setup() {
  load 'helpers/common'
  common_setup

  stub_silent gh
  stub git <<'STUB'
[[ "$1" == "rev-parse" ]] && printf 'cafef00d\n'
exit 0
STUB
}

@test "creates the release under a v-prefixed tag" {
  run "${REPO_ROOT}/utils/create_release.sh" 1.2.3

  [ "$status" -eq 0 ]
  assert_called gh "release create v1.2.3"
  assert_called gh "--title v1.2.3"
}

@test "targets the exact commit rather than a branch head" {
  # A branch can move between the build and the release; the tag must land on
  # the commit that was actually built.
  run "${REPO_ROOT}/utils/create_release.sh" 1.2.3

  [ "$status" -eq 0 ]
  assert_called gh "--target cafef00d"
}

@test "ships the binary, the man page and all three completions" {
  run "${REPO_ROOT}/utils/create_release.sh" 1.2.3

  [ "$status" -eq 0 ]
  assert_called gh "./breakfast"
  assert_called gh "man1/breakfast.1.gz"
  assert_called gh "completions/breakfast.bash"
  assert_called gh "completions/_breakfast"
  assert_called gh "completions/breakfast.fish"
}

@test "asks GitHub to generate the notes" {
  # docs/design/testing.md and the update-summary feature both depend on the
  # generated bullet format.
  run "${REPO_ROOT}/utils/create_release.sh" 1.2.3

  [ "$status" -eq 0 ]
  assert_called gh "--generate-notes"
}

@test "fails when gh fails, rather than reporting a release that does not exist" {
  stub_silent gh 1

  run "${REPO_ROOT}/utils/create_release.sh" 1.2.3

  [ "$status" -ne 0 ]
}

@test "refuses to run without a version argument" {
  run "${REPO_ROOT}/utils/create_release.sh"

  [ "$status" -ne 0 ]
  refute_called gh
}
