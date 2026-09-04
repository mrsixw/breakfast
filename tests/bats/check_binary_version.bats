#!/usr/bin/env bats
#
# 🔢 utils/check_binary_version.sh — the release gate that refuses to ship a
#    binary whose --version disagrees with the VERSION file.

setup() {
  load 'helpers/common'
  common_setup

  WORK="${BATS_TEST_TMPDIR}/work"
  mkdir -p "${WORK}"
  cd "${WORK}" || return 1
}

# The script reads the expected version through `python utils/read_version.py`
# and the actual one from `./breakfast --version`, so both are stubbed.
given_versions() { # <expected> <actual-version-line>
  stub python <<STUB
printf '%s\n' "$1"
STUB
  cat > "${WORK}/breakfast" <<BINARY
#!/usr/bin/env bash
printf '%s\n' "$2"
BINARY
  chmod +x "${WORK}/breakfast"
}

@test "passes silently when the binary matches VERSION" {
  given_versions "1.2.3" "breakfast, version 1.2.3"

  run "${REPO_ROOT}/utils/check_binary_version.sh"

  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "fails with both versions named when they disagree" {
  given_versions "1.2.3" "breakfast, version 1.2.2"

  run "${REPO_ROOT}/utils/check_binary_version.sh"

  [ "$status" -eq 1 ]
  assert_output_contains "expected 1.2.3, got 1.2.2"
}

@test "reads the version from the last field, not the whole line" {
  # `breakfast --version` prints "breakfast, version X" — a naive comparison
  # against the whole line would fail even when the versions agree.
  given_versions "9.9.9" "breakfast, version 9.9.9"

  run "${REPO_ROOT}/utils/check_binary_version.sh"

  [ "$status" -eq 0 ]
}

@test "asks the VERSION file, not a hardcoded guess" {
  given_versions "4.5.6" "breakfast, version 4.5.6"

  run "${REPO_ROOT}/utils/check_binary_version.sh"

  [ "$status" -eq 0 ]
  assert_called python "utils/read_version.py"
}
