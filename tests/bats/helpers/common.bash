#!/usr/bin/env bash
# shellcheck shell=bash
#
# shellcheck disable=SC2154  # $output and $status are set by bats, not here.
#
# 🍽️  Shared setup for the shell test suite.
#
# Every test in tests/bats/ runs the real script as a subprocess, with its
# collaborators — gh, git, curl — replaced by stubs on PATH. Nothing here
# reaches the network, and HOME is redirected into the per-test temporary
# directory so an installer test cannot scribble on the developer running it.

# Absolute path to the repository root, so tests can invoke scripts by their
# real paths regardless of where bats was started from.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
export REPO_ROOT

common_setup() {
  STUB_BIN="${BATS_TEST_TMPDIR}/bin"
  STUB_LOG="${BATS_TEST_TMPDIR}/calls"
  FAKE_HOME="${BATS_TEST_TMPDIR}/home"
  mkdir -p "${STUB_BIN}" "${STUB_LOG}" "${FAKE_HOME}"

  # Stubs shadow the real tools; the rest of PATH stays, because the scripts
  # legitimately use printf, sed, python3 and friends.
  PATH="${STUB_BIN}:${PATH}"
  HOME="${FAKE_HOME}"

  export PATH HOME STUB_BIN STUB_LOG FAKE_HOME
}

# stub <name> — body read from stdin.
#
# Every stub records its arguments in ${STUB_LOG}/<name>.log before running the
# body, so a test can assert *what the script asked for* and not merely what it
# printed. `$*` is one line per invocation.
stub() {
  local name="$1"
  {
    printf '#!/usr/bin/env bash\n'
    # shellcheck disable=SC2016  # Deliberate: this is the generated stub's own
    # source. "$*" and ${STUB_LOG} must expand when the stub runs, not now.
    printf 'printf "%%s\\n" "$*" >> "${STUB_LOG}/%s.log"\n' "${name}"
    cat
  } > "${STUB_BIN}/${name}"
  chmod +x "${STUB_BIN}/${name}"
}

# stub_silent <name> [exit_code] — a stub that records the call and does nothing
# else. The default exit code is 0.
stub_silent() {
  local name="$1" code="${2:-0}"
  stub "${name}" <<STUB
exit ${code}
STUB
}

# calls <name> — every recorded invocation of a stub, one per line.
calls() {
  cat "${STUB_LOG}/$1.log" 2>/dev/null || true
}

# call_count <name> — how many times a stub ran.
call_count() {
  calls "$1" | grep -c . || true
}

# assert_called <name> <substring> — fail unless the stub was invoked with a
# matching argument string.
assert_called() {
  if ! calls "$1" | grep -qF -- "$2"; then
    printf 'expected %s to be called with: %s\n' "$1" "$2" >&2
    printf 'actual calls:\n%s\n' "$(calls "$1")" >&2
    return 1
  fi
}

# refute_called <name> [substring] — fail if the stub ran at all, or (with a
# substring) if it ran with matching arguments.
refute_called() {
  if [[ $# -eq 1 ]]; then
    if [[ "$(call_count "$1")" != "0" ]]; then
      printf 'expected %s never to be called, but it was:\n%s\n' "$1" "$(calls "$1")" >&2
      return 1
    fi
  elif calls "$1" | grep -qF -- "$2"; then
    printf 'expected %s NOT to be called with: %s\n' "$1" "$2" >&2
    return 1
  fi
}

# assert_output_contains <substring> — bats' $output with the ANSI escapes
# stripped, because every one of these scripts is colourful. 🎨
assert_output_contains() {
  local plain
  plain="$(printf '%s' "${output}" | sed $'s/\033\\[[0-9;]*m//g')"
  if [[ "${plain}" != *"$1"* ]]; then
    printf 'expected output to contain: %s\n' "$1" >&2
    printf 'actual output:\n%s\n' "${plain}" >&2
    return 1
  fi
}

refute_output_contains() {
  local plain
  plain="$(printf '%s' "${output}" | sed $'s/\033\\[[0-9;]*m//g')"
  if [[ "${plain}" == *"$1"* ]]; then
    printf 'expected output NOT to contain: %s\n' "$1" >&2
    printf 'actual output:\n%s\n' "${plain}" >&2
    return 1
  fi
}

# run_with_tty <input> <command...> — run a command on a real pseudo-terminal,
# feeding it <input>. Scripts that gate on `[[ -t 0 ]]` and prompt with `read`
# cannot be driven any other way, and `script(1)` takes incompatible arguments
# on macOS and Linux. Python's pty module behaves the same on both.
run_with_tty() {
  local input="$1"; shift
  run python3 "${REPO_ROOT}/tests/bats/helpers/run_pty.py" "${input}" "$@"
}

# --- setup_fixture_org.sh support -------------------------------------------

# The documented inventory, as tests/e2e asserts it and as
# docs/design/testing.md tabulates it: number|title|state|draft|labels
FIXTURE_INVENTORY='1|Open PR with no labels|OPEN|false|
2|Open PR labelled bug|OPEN|false|bug
3|Open PR labelled enhancement|OPEN|false|enhancement
4|Open PR with two labels|OPEN|false|bug,wip
5|Draft PR awaiting work|OPEN|true|
6|Second draft PR|OPEN|true|enhancement
7|Closed without merging|CLOSED|false|
8|Merged fixture PR|MERGED|false|'

# install_fake_gh — put the stateful fake gh on PATH, seeded with an archived
# repository holding the documented inventory. Tests mutate the state files to
# describe drift, then assert on what the script did about it.
install_fake_gh() {
  cp "${REPO_ROOT}/tests/bats/helpers/fake_gh" "${STUB_BIN}/gh"
  chmod +x "${STUB_BIN}/gh"

  FAKE_GH_FIXTURES="${BATS_TEST_TMPDIR}/fixtures.txt"
  FAKE_GH_ARCHIVED="${BATS_TEST_TMPDIR}/archived.txt"
  printf '%s\n' "${FIXTURE_INVENTORY}" > "${FAKE_GH_FIXTURES}"
  printf 'true\n' > "${FAKE_GH_ARCHIVED}"
  export FAKE_GH_FIXTURES FAKE_GH_ARCHIVED
}

# A git stub for the scratch clone. It never talks to a remote; the clone just
# creates the directory the script cd's into.
install_fake_git() {
  stub git <<'STUB'
case "$1" in
  clone)
    for arg in "$@"; do target="${arg}"; done
    mkdir -p "${target}"
    exit 0 ;;
  ls-remote)
    # `--exit-code --heads origin fixture-N`: absent unless the test says so.
    [[ -n "${FAKE_GIT_BRANCH_EXISTS:-}" ]] && exit 0
    exit 2 ;;
  *) exit 0 ;;
esac
STUB
}

# archived_state — what the fake repository's archived flag is right now.
archived_state() { cat "${FAKE_GH_ARCHIVED}"; }

# fixture_row <number> — the fake inventory's row for one pull request.
fixture_row() { grep "^$1|" "${FAKE_GH_FIXTURES}"; }

# set_fixture <number> <field> <value> — describe drift. Fields: 3 state,
# 4 draft, 5 labels.
set_fixture() {
  local tmp="${FAKE_GH_FIXTURES}.tmp"
  awk -F'|' -v OFS='|' -v n="$1" -v f="$2" -v v="$3" \
    '$1 == n { $f = v } { print }' "${FAKE_GH_FIXTURES}" > "${tmp}"
  mv "${tmp}" "${FAKE_GH_FIXTURES}"
}

# drop_fixture <number> — delete a pull request from the fake inventory.
drop_fixture() {
  local tmp="${FAKE_GH_FIXTURES}.tmp"
  grep -v "^$1|" "${FAKE_GH_FIXTURES}" > "${tmp}"
  mv "${tmp}" "${FAKE_GH_FIXTURES}"
}

# add_fixture <number> <title> — add a pull request the inventory does not know.
add_fixture() {
  printf '%s|%s|OPEN|false|\n' "$1" "$2" >> "${FAKE_GH_FIXTURES}"
}

# The frozen repository, as the script is normally pointed at it.
# shellcheck disable=SC2034  # Read by the .bats files that load this helper.
FIXTURE_ARGS=(mrsixw --repo breakfast-fixtures)
