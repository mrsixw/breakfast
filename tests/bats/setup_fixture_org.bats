#!/usr/bin/env bats
#
# 🥐 utils/setup_fixture_org.sh — provisions and repairs the frozen end-to-end
#    fixtures.
#
# Two failure modes make this the script most worth testing in the repository:
# it can leave the fixture repository **writeable**, and it can drift an
# inventory the live suite asserts by exact count. Both are covered below.
#
# `gh` is a stateful fake (tests/bats/helpers/fake_gh) that applies the
# mutations it is asked for, so verification at the end of a run means
# something. `git` never reaches a remote.

SCRIPT=""

setup() {
  load 'helpers/common'
  common_setup
  install_fake_gh
  install_fake_git
  SCRIPT="${REPO_ROOT}/utils/setup_fixture_org.sh"
}

# ---------------------------------------------------------------------------
# 🧾 Arguments
# ---------------------------------------------------------------------------

@test "refuses to run without an organisation" {
  run "${SCRIPT}"

  [ "$status" -eq 1 ]
  assert_output_contains "No organisation given"
}

@test "rejects an unknown option rather than ignoring it" {
  run "${SCRIPT}" someorg --bogus

  [ "$status" -eq 1 ]
  assert_output_contains "Unknown option: --bogus"
}

@test "rejects a stray second positional argument" {
  run "${SCRIPT}" someorg extra

  [ "$status" -eq 1 ]
  assert_output_contains "Unexpected extra argument"
}

@test "--help explains itself and exits clean" {
  run "${SCRIPT}" --help

  [ "$status" -eq 0 ]
  assert_output_contains "Provision the breakfast end-to-end fixture organisation"
  assert_output_contains "--update"
}

# ---------------------------------------------------------------------------
# 🛡️ The frozen-repo guard
# ---------------------------------------------------------------------------

@test "refuses to seed the frozen fixture repository" {
  run "${SCRIPT}" "${FIXTURE_ARGS[@]}"

  [ "$status" -eq 1 ]
  assert_output_contains "Refusing to seed mrsixw/breakfast-fixtures"
  refute_called gh "repo create"
}

@test "the frozen-repo guard is case-insensitive" {
  # GitHub logins are case-insensitive, so the guard must be too.
  run "${SCRIPT}" MrSixW --repo Breakfast-Fixtures

  [ "$status" -eq 1 ]
  assert_output_contains "Refusing to seed"
}

@test "the guard points at --update rather than just saying no" {
  run "${SCRIPT}" "${FIXTURE_ARGS[@]}"

  assert_output_contains "--update"
}

@test "--update is the way past the frozen-repo guard" {
  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  [ "$status" -eq 0 ]
  refute_output_contains "Refusing to seed"
}

# ---------------------------------------------------------------------------
# 🔎 Preflight
# ---------------------------------------------------------------------------

@test "seeding stops when the organisation does not exist" {
  export FAKE_GH_ORG_MISSING=1

  run "${SCRIPT}" someorg --dry-run

  [ "$status" -eq 1 ]
  assert_output_contains "not found, or your token cannot see it"
  assert_output_contains "organizations/plan"
}

@test "updating does not require an organisation, because the fixtures are under a user" {
  # mrsixw/breakfast-fixtures is owned by a user account, not an org. Refusing
  # to repair it on that ground would be perverse.
  export FAKE_GH_ORG_MISSING=1

  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  [ "$status" -eq 0 ]
}

@test "seeding refuses a repository that already holds pull requests" {
  run "${SCRIPT}" someorg --repo scratch

  [ "$status" -eq 1 ]
  assert_output_contains "already holds 8 pull requests"
}

@test "seeding refuses a repository littered with orphaned fixture branches" {
  printf '' > "${FAKE_GH_FIXTURES}"       # no pull requests...
  export FAKE_GH_STALE_BRANCHES=3         # ...but branches from a dead run

  run "${SCRIPT}" someorg --repo scratch

  [ "$status" -eq 1 ]
  assert_output_contains "fixture-* branches but no pull requests"
  assert_output_contains "force push"
}

# ---------------------------------------------------------------------------
# 🧊 The unfreeze/refreeze envelope
# ---------------------------------------------------------------------------

@test "updating asserts the repository is archived before doing anything" {
  printf 'false\n' > "${FAKE_GH_ARCHIVED}"

  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  [ "$status" -eq 1 ]
  assert_output_contains "is NOT archived"
  refute_called gh "repo unarchive"
}

@test "the not-archived error prints the command that fixes it" {
  printf 'false\n' > "${FAKE_GH_ARCHIVED}"

  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  assert_output_contains "gh repo archive mrsixw/breakfast-fixtures --yes"
}

@test "updating refuses a repository that does not exist" {
  export FAKE_GH_REPO_MISSING=1

  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  [ "$status" -eq 1 ]
  assert_output_contains "does not exist"
}

@test "it prints the unarchive command before asking for confirmation" {
  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  assert_output_contains "gh repo unarchive mrsixw/breakfast-fixtures --yes"
  assert_output_contains "THE FIXTURES ARE ABOUT TO BECOME WRITEABLE"
}

@test "it refuses to unfreeze without an interactive terminal" {
  # No tty means nobody is watching, and an unfrozen fixture repo needs
  # watching. There is deliberately no non-interactive escape hatch.
  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 1 ]
  assert_output_contains "without a human"
  refute_called gh "repo unarchive"
  [ "$(archived_state)" = "true" ]
}

@test "it aborts when the confirmation word is not typed exactly" {
  run_with_tty "unfreeze" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 1 ]
  assert_output_contains "Not confirmed"
  refute_called gh "repo unarchive"
  [ "$(archived_state)" = "true" ]
}

@test "typing UNFREEZE unfreezes, reconciles and refreezes" {
  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  assert_called gh "repo unarchive"
  assert_called gh "repo archive"
  assert_output_contains "archived again"
  [ "$(archived_state)" = "true" ]
}

@test "a failure mid-run still refreezes" {
  # The clone dies because the fake git is told the repo cannot be cloned.
  stub git <<'STUB'
[[ "$1" == "clone" ]] && exit 128
exit 0
STUB

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -ne 0 ]
  assert_called gh "repo archive"
  [ "$(archived_state)" = "true" ]
}

@test "an unarchive that fails after landing server-side still refreezes" {
  # gh can fail at the transport layer having already applied the change. The
  # trap is armed before the request leaves for exactly this case.
  export FAKE_GH_UNARCHIVE_FAILS=1

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -ne 0 ]
  assert_called gh "repo archive"
  [ "$(archived_state)" = "true" ]
}

@test "an unconfirmed refreeze exits non-zero even when the repair succeeded" {
  # A green exit is how a tired human decides it is safe to walk away.
  export FAKE_GH_ARCHIVE_FAILS=1

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 75 ]
  assert_output_contains "COULD NOT CONFIRM"
  assert_output_contains "still be WRITEABLE"
}

@test "it does not trust a successful-looking archive that changed nothing" {
  # Archiving an already-archived repo is an error too, so the exit status
  # cannot be believed either way — the state is read back instead.
  export FAKE_GH_ARCHIVE_SILENT=1

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 75 ]
  assert_output_contains "COULD NOT CONFIRM"
}

@test "the manual recovery command is printed when the refreeze cannot be confirmed" {
  export FAKE_GH_ARCHIVE_FAILS=1

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  assert_output_contains "gh repo archive mrsixw/breakfast-fixtures --yes"
}

# ---------------------------------------------------------------------------
# 🔬 The pre-thaw survey
# ---------------------------------------------------------------------------

@test "it refuses to thaw a repository holding duplicate fixture titles" {
  add_fixture 9 "Second draft PR"

  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  [ "$status" -eq 1 ]
  assert_output_contains "pull requests titled 'Second draft PR'"
  refute_called gh "repo unarchive"
}

@test "it refuses to thaw a repository holding undocumented pull requests" {
  # An extra pull request cannot be deleted through the API and would break the
  # exact-count assertions, so this must be discovered while still read-only.
  add_fixture 9 "A pull request nobody documented"

  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  [ "$status" -eq 1 ]
  assert_output_contains "the inventory does"
  refute_called gh "repo unarchive"
}

@test "a missing fixture is not a stray, and does not block the repair" {
  drop_fixture 3

  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------------------
# 🍳 Reconciling
# ---------------------------------------------------------------------------

@test "an undrifted inventory is a no-op" {
  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  refute_called gh "pr edit"
  refute_called gh "pr close"
  refute_called gh "pr merge"
  refute_called gh "pr ready"
  refute_called gh "pr create"
}

@test "it restores a label that was removed" {
  set_fixture 2 5 ""

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  assert_called gh "pr edit 2 --repo mrsixw/breakfast-fixtures --add-label bug"
  [ "$(fixture_row 2)" = "2|Open PR labelled bug|OPEN|false|bug" ]
}

@test "it removes a label that should not be there" {
  set_fixture 1 5 "wip"

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  assert_called gh "--remove-label wip"
  [ "$(fixture_row 1)" = "1|Open PR with no labels|OPEN|false|" ]
}

@test "it fixes a two-label fixture that lost one of them" {
  set_fixture 4 5 "bug"

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  assert_called gh "--add-label wip"
  [ "$(fixture_row 4)" = "4|Open PR with two labels|OPEN|false|bug,wip" ]
}

@test "it puts a readied draft back into draft" {
  set_fixture 5 4 false

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  assert_called gh "pr ready 5 --repo mrsixw/breakfast-fixtures --undo"
  [ "$(fixture_row 5)" = "5|Draft PR awaiting work|OPEN|true|" ]
}

@test "it takes a wrongly-drafted fixture out of draft" {
  set_fixture 1 4 true

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  assert_called gh "pr ready 1"
  [ "$(fixture_row 1)" = "1|Open PR with no labels|OPEN|false|" ]
}

@test "it recloses a fixture someone reopened" {
  set_fixture 7 3 OPEN

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  assert_called gh "pr close 7"
  [ "$(fixture_row 7)" = "7|Closed without merging|CLOSED|false|" ]
}

@test "it reopens a fixture someone closed" {
  set_fixture 2 3 CLOSED

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  assert_called gh "pr reopen 2"
}

@test "it recreates a fixture that was deleted outright" {
  drop_fixture 3

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  assert_called gh "--title Open PR labelled enhancement"
  assert_called gh "--add-label enhancement"
}

@test "a recreated draft fixture is created as a draft" {
  drop_fixture 5

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  assert_called gh "--draft"
}

@test "it reuses an orphaned branch rather than force pushing over it" {
  drop_fixture 6
  export FAKE_GIT_BRANCH_EXISTS=1

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -eq 0 ]
  assert_output_contains "already on the remote"
  refute_called git "push"
}

@test "it gives up on a fixture that has been merged when it should be open" {
  # A merge cannot be undone through the API, so the repository can no longer
  # be reconciled and the script must say so rather than limping on.
  set_fixture 2 3 MERGED

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -ne 0 ]
  assert_output_contains "cannot be reversed"
  [ "$(archived_state)" = "true" ]
}

@test "it dies rather than treating a gh failure as a missing fixture" {
  # Swallowing the error would create a duplicate pull request, which cannot
  # then be deleted.
  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  # The dry run gets far enough to survey; make the lookup fail for the real
  # thing instead.
  export FAKE_GH_PR_LIST_FAILS=1
  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  [ "$status" -ne 0 ]
  refute_called gh "pr create"
}

@test "it verifies the counts after reconciling" {
  set_fixture 6 3 CLOSED

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  # Reconciling reopens it, so the counts come back right.
  [ "$status" -eq 0 ]
  assert_output_contains "open=6 (want 6)"
  assert_output_contains "inventory matches"
}

@test "it refuses to declare success when the counts still do not add up" {
  # The repair appears to run, but nothing sticks — a reconcile loop that
  # edited the wrong pull requests would look exactly like this.
  set_fixture 6 3 CLOSED
  export FAKE_GH_IGNORE_WRITES=1

  run_with_tty "UNFREEZE" "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update

  [ "$status" -ne 0 ]
  assert_output_contains "Inventory does not match the documented counts"
  # ...and it still refreezes on the way out.
  [ "$(archived_state)" = "true" ]
}

# ---------------------------------------------------------------------------
# 🌀 Dry run
# ---------------------------------------------------------------------------

@test "a dry run mutates nothing at all" {
  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  [ "$status" -eq 0 ]
  refute_called gh "repo unarchive"
  refute_called gh "repo archive"
  refute_called gh "pr edit"
  refute_called gh "pr create"
  [ "$(archived_state)" = "true" ]
}

@test "a dry run never claims a mutation happened" {
  run "${SCRIPT}" someorg --repo scratch --dry-run

  [ "$status" -eq 1 ]   # the fake repo already holds pull requests
  refute_output_contains "✅ created"
}

@test "a seeding dry run creates no repository" {
  export FAKE_GH_REPO_MISSING=1

  run "${SCRIPT}" someorg --repo scratch --dry-run

  [ "$status" -eq 0 ]
  assert_output_contains "would run: gh repo create"
  refute_called gh "repo create"
}

@test "a dry run does not ask for confirmation" {
  run "${SCRIPT}" "${FIXTURE_ARGS[@]}" --update --dry-run

  [ "$status" -eq 0 ]
  assert_output_contains "not unarchiving, and not asking you to confirm"
}
