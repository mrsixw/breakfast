#!/usr/bin/env bash
#
# 🥐 setup_fixture_org.sh — provision (or repair) breakfast's frozen end-to-end
#    fixtures inside a dedicated GitHub organisation.
#
# The end-to-end suite asserts *exact* pull request counts, so the fixtures it
# queries must be reproducible byte for byte. This script is that reproduction:
# it builds the eight-pull-request inventory documented in
# docs/design/testing.md, in an org of your choosing.
#
# Two modes:
#   (default)  seed a fresh repository with the eight fixtures.
#   --update   reconcile an existing, archived fixture repository back to the
#              documented inventory. This is the only way to touch the frozen
#              mrsixw/breakfast-fixtures, and it unfreezes and refreezes it
#              around the work. 🧊
#
# 🔗 Issue:      https://github.com/mrsixw/breakfast/issues/456
# 🔗 Doctrine:   docs/design/testing.md
# 🔗 Machine account follow-up: https://github.com/mrsixw/breakfast/issues/452
#
# Usage:
#   ./utils/setup_fixture_org.sh <org> [--repo NAME] [--update] [--dry-run] [--archive]
#
# Safe to re-run: every step checks for what it is about to create.

set -euo pipefail

# ---------------------------------------------------------------------------
# 🎨 Chatter
# ---------------------------------------------------------------------------

step() { printf '\n\033[1;35m%s\033[0m %s\n' "$1" "$2"; }
info() { printf '   \033[2m%s\033[0m\n' "$1"; }
ok()   { printf '   ✅ %s\n' "$1"; }
# Like ok(), but for messages that claim a mutation happened — under --dry-run
# nothing happened, and saying otherwise would be a lie. 🤥
did()  {
  if [[ "${DRY_RUN}" == "true" ]]; then
    printf '   🌀 \033[2mdry run — did not actually: %s\033[0m\n' "$1"
  else
    printf '   ✅ %s\n' "$1"
  fi
}
skip() { printf '   ⏭️  %s\n' "$1"; }
warn() { printf '   ⚠️  %s\n' "$1" >&2; }
die()  { printf '\n💥 \033[1;31m%s\033[0m\n' "$1" >&2; exit 1; }

# In --dry-run, echo the command instead of running it.
run() {
  if [[ "${DRY_RUN}" == "true" ]]; then
    printf '   🌀 \033[2mwould run:\033[0m %s\n' "$*"
  else
    "$@"
  fi
}

# ---------------------------------------------------------------------------
# 🧾 Arguments
# ---------------------------------------------------------------------------

ORG=""
REPO="breakfast-fixtures"
DRY_RUN="false"
ARCHIVE="false"
UPDATE="false"

usage() {
  cat <<'USAGE'
🍳 Provision the breakfast end-to-end fixture organisation.

  ./utils/setup_fixture_org.sh <org> [options]

  <org>            The GitHub organisation login to provision into. Required —
                   there is no default, because getting this wrong writes eight
                   pull requests into somebody's real account. 😬

Options:
  --repo NAME      Fixture repository name (default: breakfast-fixtures).
  --update         Repair an existing, *archived* fixture repo instead of
                   seeding a fresh one. Reconciles the live inventory back to
                   the eight fixtures documented in docs/design/testing.md.
                   The repo must be archived when the script starts; it is
                   unarchived (after you type a confirmation) and re-archived
                   on the way out, including on failure. 🧊➡️🔥➡️🧊
  --dry-run        Print every mutating command instead of running it. 🌀
  --archive        Freeze the repo at the end (read-only). Do NOT pass this
                   until `make e2e` has gone green against the new fixtures —
                   archived repos reject changes, so a mistaken inventory needs
                   unarchiving to fix. Implied by --update. 🧊
  -h, --help       Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)    REPO="${2:?--repo needs a value}"; shift 2 ;;
    --update)  UPDATE="true"; shift ;;
    --dry-run) DRY_RUN="true"; shift ;;
    --archive) ARCHIVE="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    -*)        die "Unknown option: $1 — try --help 🤔" ;;
    *)
      [[ -n "${ORG}" ]] && die "Unexpected extra argument: $1"
      ORG="$1"; shift ;;
  esac
done

[[ -n "${ORG}" ]] || { usage >&2; die "No organisation given. 🏢"; }

SLUG="${ORG}/${REPO}"

# 🛡️  The existing fixtures are frozen and asserted by exact count. Seeding on
#     top of them would double the inventory, so the seed path refuses them
#     outright. --update is the deliberate, guarded way in.
#     Compared lowercased because GitHub logins are case-insensitive, and via
#     tr rather than ${SLUG,,} because macOS still ships bash 3.2. 🍎
SLUG_LOWER="$(printf '%s' "${SLUG}" | tr '[:upper:]' '[:lower:]')"
if [[ "${SLUG_LOWER}" == "mrsixw/breakfast-fixtures" && "${UPDATE}" != "true" ]]; then
  die "Refusing to seed mrsixw/breakfast-fixtures — it is frozen. 🧊
   See docs/design/testing.md.
   To *repair* it, re-run with --update. To build a new one, pick another org."
fi

# --update always refreezes; the flag is redundant but harmless.
[[ "${UPDATE}" == "true" ]] && ARCHIVE="true"

printf '\n🥞 \033[1mbreakfast fixture provisioner\033[0m\n'
info "target:  ${SLUG}"
info "mode:    $([[ "${UPDATE}" == "true" ]] && echo 'update (reconcile)' || echo 'seed (fresh)')"
info "dry-run: ${DRY_RUN}   archive-at-end: ${ARCHIVE}"

# ---------------------------------------------------------------------------
# 🍳 The eight fixtures
# ---------------------------------------------------------------------------
#
# The inventory below is asserted verbatim by tests/e2e/features/pr_listing.feature.
# 🔗 Keep it in lockstep with the table in docs/design/testing.md.
#
#   #  Title                          State   Draft  Labels
#   1  Open PR with no labels         open    no     —
#   2  Open PR labelled bug           open    no     bug
#   3  Open PR labelled enhancement   open    no     enhancement
#   4  Open PR with two labels        open    no     bug, wip
#   5  Draft PR awaiting work         open    yes    —
#   6  Second draft PR                open    yes    enhancement
#   7  Closed without merging         closed  no     —
#   8  Merged fixture PR              merged  no     —

TITLES=(
  "Open PR with no labels"
  "Open PR labelled bug"
  "Open PR labelled enhancement"
  "Open PR with two labels"
  "Draft PR awaiting work"
  "Second draft PR"
  "Closed without merging"
  "Merged fixture PR"
)
# Parallel arrays, not an associative one: bash 3.2 has no `declare -A`. 🍎
STATES=( OPEN OPEN OPEN OPEN OPEN OPEN CLOSED MERGED )
DRAFTS=( false false false false true true false false )
LABELS=( "" "bug" "enhancement" "bug wip" "" "enhancement" "" "" )

# Sorted, comma-joined label list — the shape `gh` hands back, so the two can
# be compared as plain strings.
csv_of() {
  local out="" item
  for item in $(printf '%s' "$1" | tr ' ' '\n' | sort); do
    [[ -z "${item}" ]] && continue
    out="${out:+${out},}${item}"
  done
  printf '%s' "${out}"
}

# One line per matching pull request: "number state isDraft labelcsv".
# Titles are fixed strings with no quotes, so interpolating one into the jq
# filter is safe — `gh --jq` has no --arg to do it properly.
lookup_pr() {
  # 🙅 No `|| true`: an auth or API failure here would otherwise read as "that
  #    fixture is missing", and the caller would cheerfully create a duplicate.
  #    A failure must abort the run instead.
  gh pr list --repo "${SLUG}" --state all --limit 100 \
    --json number,title,state,isDraft,labels \
    --jq "[.[] | select(.title == \"$1\")] | .[0] // empty
          | \"\(.number) \(.state) \(.isDraft) \((.labels | map(.name) | sort | join(\",\")))\"" \
    || die "Could not list pull requests on ${SLUG}. 🛰️
   gh failed, so the inventory cannot be trusted. Nothing further was changed."
}

# 🔬 Is the live repository one this script can reconcile at all? Extra or
#    duplicated pull requests cannot be deleted through the API, so discovering
#    them *after* mutating half the inventory would be the worst of both
#    worlds. This runs before the thaw, and reads only.
survey_inventory() {
  local live total documented=0 count title

  live="$(gh pr list --repo "${SLUG}" --state all --limit 200 --json title --jq '.[].title')" \
    || die "Could not list pull requests on ${SLUG}. 🛰️ Nothing was changed."
  total="$(printf '%s\n' "${live}" | grep -c . || true)"

  for title in "${TITLES[@]}"; do
    count="$(printf '%s\n' "${live}" | grep -Fxc -- "${title}" || true)"
    if [[ "${count}" -gt 1 ]]; then
      die "${SLUG} holds ${count} pull requests titled '${title}'. 👯
   Reconciling by title cannot tell them apart, and a duplicate cannot be
   deleted through the API. Sort this out by hand — nothing was changed."
    fi
    documented=$((documented + count))
  done

  if [[ "${total}" -ne "${documented}" ]]; then
    die "${SLUG} holds $((total - documented)) pull request(s) the inventory does
   not describe. 👽 They cannot be deleted through the API, and they would
   break the exact-count assertions. Sort this out by hand — nothing was
   changed."
  fi

  ok "live inventory is reconcilable: ${total} pull request(s), no strays, no duplicates"
}

# ---------------------------------------------------------------------------
# 🧹 Cleanup — the single exit path
# ---------------------------------------------------------------------------
#
# 🧊 If we thawed the repo, refreezing is not optional and not conditional on
#    success. An abandoned run that leaves the fixtures writeable is the one
#    outcome worse than a failed update, so this hangs off EXIT and catches
#    `die`, an unexpected `set -e` abort, and Ctrl-C alike.

UNARCHIVED="false"
WORKTREE=""

cleanup() {
  local rc=$? state
  if [[ "${UNARCHIVED}" != "false" ]]; then
    UNARCHIVED="false"   # never recurse if the archive call itself fails
    printf '\n\033[1;36m🧊 Refreezing %s\033[0m\n' "${SLUG}"

    # Archiving an already-archived repo is an error, and so is a transport
    # failure — the two are indistinguishable from the exit status. Ask the
    # repository what state it is actually in instead of trusting either.
    gh repo archive "${SLUG}" --yes >/dev/null 2>&1 || true
    state="$(gh repo view "${SLUG}" --json isArchived --jq '.isArchived' 2>/dev/null || echo unknown)"

    if [[ "${state}" == "true" ]]; then
      printf '   ✅ archived again — the fixtures are read-only\n'
    else
      printf '   💥 \033[1;31mCOULD NOT CONFIRM %s IS ARCHIVED (state: %s)\033[0m\n' "${SLUG}" "${state}" >&2
      printf '   \033[1;31mThe fixtures may still be WRITEABLE. Freeze them by hand, now:\033[0m\n' >&2
      printf '\n       gh repo archive %s --yes\n\n' "${SLUG}" >&2
      # 🚨 Never exit 0 on an unconfirmed refreeze: a green exit is exactly how
      #    automation, or a tired human, decides it is safe to walk away.
      [[ "${rc}" -eq 0 ]] && rc=75
    fi
  fi
  if [[ -n "${WORKTREE}" ]]; then
    cd /
    rm -rf "${WORKTREE}"
  fi
  exit "${rc}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ---------------------------------------------------------------------------
# 🔎 Preflight
# ---------------------------------------------------------------------------

step "🔎" "Preflight"

command -v gh  >/dev/null || die "gh is not installed. 🔗 https://cli.github.com"
command -v git >/dev/null || die "git is not installed. 🤷"
gh auth status >/dev/null 2>&1 || die "gh is not authenticated — run: gh auth login 🔑"
ok "gh present and authenticated"

# gh cannot create an organisation; the API has no endpoint for it. Check that
# the human already made one rather than failing eight steps later.
#
# 🙋 Update mode skips this: it never creates a repository, so the owner only
#    has to already own one. The historical fixtures live under a user account
#    rather than an org, and refusing to repair them on that ground would be
#    perverse.
if [[ "${UPDATE}" != "true" ]]; then
  if ! gh api "orgs/${ORG}" >/dev/null 2>&1; then
    die "Organisation '${ORG}' not found, or your token cannot see it. 🏢
   Organisations cannot be created from the API — make it by hand first:
   🔗 https://github.com/organizations/plan  (the Free plan is plenty)
   Then re-run this script."
  fi
  ok "organisation ${ORG} exists"
fi

REPO_EXISTS="false"
gh repo view "${SLUG}" >/dev/null 2>&1 && REPO_EXISTS="true"

# ---------------------------------------------------------------------------
# 🧊 Thaw — update mode only
# ---------------------------------------------------------------------------

if [[ "${UPDATE}" == "true" ]]; then
  step "🧊" "Unfreezing the fixtures"

  [[ "${REPO_EXISTS}" == "true" ]] || die "${SLUG} does not exist. 🕳️
   --update repairs an existing fixture repo; it does not create one.
   Drop --update to seed a fresh repository instead."

  IS_ARCHIVED="$(gh repo view "${SLUG}" --json isArchived --jq '.isArchived')"

  # 🛡️  Archived is the fixtures' resting state, and finding them any other way
  #     means something is already wrong: a previous run died before its trap,
  #     or somebody unfroze them by hand and wandered off. Either way the repo
  #     may have drifted while it was writeable, so stop and let a human look.
  if [[ "${IS_ARCHIVED}" != "true" ]]; then
    die "${SLUG} is NOT archived. 🔥
   The fixtures are supposed to sit frozen between repairs, so finding them
   thawed means an earlier run never refroze them — and anything could have
   changed in the meantime.
   Check the inventory against docs/design/testing.md, freeze it:

       gh repo archive ${SLUG} --yes

   ...and then re-run this script."
  fi
  ok "${SLUG} is archived — the expected resting state"

  # 🔬 Survey before thawing. Everything this script can*not* fix should be
  #    discovered while the repository is still read-only.
  survey_inventory

  # printf, not a heredoc: `cat` would print the colour escapes literally. 🎨
  printf '\n'
  printf '   \033[1;33m⚠️  ⚠️  ⚠️   THE FIXTURES ARE ABOUT TO BECOME WRITEABLE   ⚠️  ⚠️  ⚠️\033[0m\n\n'
  printf '   %s backs every scenario in tests/e2e/, and those\n' "${SLUG}"
  printf '   scenarios assert exact pull request counts. While it is unfrozen, any\n'
  printf '   stray click, script or bot that touches it can break CI on mrsixw/breakfast.\n\n'
  printf '   To do its work this script must first run:\n\n'
  printf '       \033[1mgh repo unarchive %s --yes\033[0m\n\n' "${SLUG}"
  printf '   It will refreeze on the way out — on success, on failure, and on Ctrl-C:\n\n'
  printf '       \033[1mgh repo archive %s --yes\033[0m\n\n' "${SLUG}"
  printf '   If it somehow cannot, it will shout, and running that command by hand is\n'
  printf '   then YOUR job. Do not walk away from an unfrozen fixture repo. 🚶‍♀️🚫\n\n'

  if [[ "${DRY_RUN}" == "true" ]]; then
    skip "dry run — not unarchiving, and not asking you to confirm"
  else
    [[ -t 0 ]] || die "Refusing to unfreeze the fixtures without a human. 🤖
   --update needs an interactive terminal to confirm on. Run it by hand."

    printf '   Type \033[1mUNFREEZE\033[0m to continue (anything else aborts): '
    read -r CONFIRM
    [[ "${CONFIRM}" == "UNFREEZE" ]] || die "Not confirmed — nothing was touched. 🧊"

    # ⏰ Armed *before* the call, not after: if gh fails at the transport layer
    #    the unarchive may still have landed server-side, and a signal can
    #    arrive mid-request. The trap must owe us a refreeze from the moment
    #    the request leaves, not from the moment it is confirmed. Refreezing a
    #    repo that was never thawed is harmless — cleanup checks the real state.
    UNARCHIVED="pending"
    gh repo unarchive "${SLUG}" --yes >/dev/null
    UNARCHIVED="true"
    ok "${SLUG} is unfrozen — the clock is ticking ⏱️"
  fi
fi

# ---------------------------------------------------------------------------
# 📦 Repository
# ---------------------------------------------------------------------------

step "📦" "Fixture repository"

if [[ "${REPO_EXISTS}" == "true" ]]; then
  skip "${SLUG} already exists"

  # 🛡️  Seeding twice would duplicate an inventory asserted by exact count.
  #     Update mode expects to find those pull requests, so it skips both of
  #     these guards — reconciling is exactly what it is here to do.
  if [[ "${UPDATE}" != "true" ]]; then
    EXISTING_PRS="$(gh pr list --repo "${SLUG}" --state all --limit 100 --json number --jq 'length')"
    if [[ "${EXISTING_PRS}" != "0" ]]; then
      die "${SLUG} already holds ${EXISTING_PRS} pull requests. 🛑
   This script seeds a *fresh* repo; re-seeding would duplicate the inventory
   and break the exact-count assertions. Pass --update to reconcile it back to
   the documented inventory instead, delete the repo, or pass --repo NAME to
   seed a different one."
    fi

    # 🥴 Branches but no pull requests means a previous run died between the
    #    push and the `gh pr create`. Re-pushing those branches would be a
    #    non-fast-forward, and this script will not force push. Say so plainly.
    STALE="$(gh api "repos/${SLUG}/branches" --paginate \
      --jq '[.[] | select(.name | startswith("fixture-"))] | length' 2>/dev/null || echo 0)"
    if [[ "${STALE}" != "0" ]]; then
      die "${SLUG} has ${STALE} fixture-* branches but no pull requests. 🥴
   That is the wreckage of an incomplete run. Re-pushing them would need a
   force push, which this script will not do.
   Delete the repository and re-run, or pass --repo NAME to seed a fresh one."
    fi
  fi
else
  run gh repo create "${SLUG}" --public \
    --description "Frozen PR fixtures for breakfast's end-to-end suite. Do not modify."
  did "created ${SLUG}"
fi

# ---------------------------------------------------------------------------
# 📝 README
# ---------------------------------------------------------------------------

step "📝" "$([[ "${UPDATE}" == "true" ]] && echo 'Scratch clone' || echo 'Seeding the warning README')"

WORKTREE="$(mktemp -d)"
info "scratch clone: ${WORKTREE}"

if [[ "${DRY_RUN}" == "true" ]]; then
  if [[ "${UPDATE}" == "true" ]]; then
    printf '   🌀 \033[2mwould clone (needed only if a fixture branch is missing)\033[0m\n'
  else
    printf '   🌀 \033[2mwould clone, commit README.md and push\033[0m\n'
  fi
else
  git clone --quiet "https://github.com/${SLUG}.git" "${WORKTREE}/repo"
  cd "${WORKTREE}/repo"

  # ✋ Update mode leaves main alone. It is here to fix the pull request
  #    inventory, and rewriting the README of a repo it only just unfroze is a
  #    mutation nobody asked for.
  if [[ "${UPDATE}" == "true" ]]; then
    skip "leaving main untouched — update mode only reconciles pull requests"
  else
    printf '# %s\n\n> [!WARNING]\n> 🧊 Frozen fixtures for the breakfast end-to-end suite. Changing anything\n> here breaks CI on mrsixw/breakfast.\n>\n> 🔗 See docs/design/testing.md in that repo.\n' \
      "${REPO}" > README.md

    git add README.md
    # 🔁 On a re-run the README is already there and identical, so nothing gets
    #    staged and `git commit` would exit 1 — fatal under `set -e`.
    git diff --cached --quiet || git commit --quiet -m "docs: add fixture warning"
    git branch --move main 2>/dev/null || true
    git push --quiet -u origin main
    ok "README pushed, main branch established"
  fi
fi

# ---------------------------------------------------------------------------
# 🏷️ Labels
# ---------------------------------------------------------------------------

step "🏷️" "Labels"

run gh label create wip --repo "${SLUG}" --color ededed --force
for label in bug enhancement; do
  run gh label create "${label}" --repo "${SLUG}" --force
done
did "wip, bug, enhancement ready"

step "🍳" "$([[ "${UPDATE}" == "true" ]] && echo 'Reconciling the eight pull requests' || echo 'Cooking eight pull requests')"

# 🥚 Fixture number -> the PR number GitHub actually minted. Never assume 1..8;
#    a stray pull request would shift every later edit onto the wrong target.
declare -a PR_NUMBER

for index in "${!TITLES[@]}"; do
  n=$((index + 1))
  title="${TITLES[${index}]}"
  branch="fixture-${n}"
  want_state="${STATES[${index}]}"
  want_draft="${DRAFTS[${index}]}"
  want_labels="$(csv_of "${LABELS[${index}]}")"

  printf '   🍽️  %d/8  %s\n' "${n}" "${title}"

  # In a dry run against a repo that does not exist yet there is nothing to
  # look up, and `gh pr list` would fail rather than return nothing.
  found=""
  [[ "${REPO_EXISTS}" == "true" ]] && found="$(lookup_pr "${title}")"

  if [[ -z "${found}" ]]; then
    # ---- missing: create it -------------------------------------------------
    if [[ "${DRY_RUN}" == "true" ]]; then
      printf '      🌀 \033[2mwould branch %s, commit, push and open a PR\033[0m\n' "${branch}"
      PR_NUMBER[n]="${n}"
      continue
    fi

    # A leftover branch from a half-finished run is reusable as-is; pushing it
    # again would be a non-fast-forward, and this script will not force push.
    if git ls-remote --exit-code --heads origin "${branch}" >/dev/null 2>&1; then
      info "branch ${branch} already on the remote — opening a PR from it"
    else
      git checkout --quiet main
      git checkout --quiet -B "${branch}"
      echo "${title}" > "fixture-${n}.txt"
      git add .
      git commit --quiet -m "${title}"
      git push --quiet -u origin "${branch}"
    fi

    # 🥸 The expansion below looks like a typo but is not: under `set -u`,
    #    bash 3.2 treats "${arr[@]}" on an empty array as an unbound variable.
    #    "${arr[@]+"${arr[@]}"}" expands to nothing instead of exploding.
    draft_flag=()
    [[ "${want_draft}" == "true" ]] && draft_flag=(--draft)

    url="$(gh pr create --repo "${SLUG}" "${draft_flag[@]+"${draft_flag[@]}"}" \
      --base main --head "${branch}" \
      --title "${title}" --body "🧊 Frozen fixture. Do not modify.")"

    PR_NUMBER[n]="${url##*/}"
    info "→ created ${url}"
    have_state="OPEN"
    have_draft="${want_draft}"
    have_labels=""
  else
    # ---- present: reconcile it ---------------------------------------------
    read -r have_number have_state have_draft have_labels <<<"${found}"
    have_labels="${have_labels:-}"
    PR_NUMBER[n]="${have_number}"
    info "→ #${have_number} ${have_state} draft=${have_draft} labels=[${have_labels}]"
  fi

  num="${PR_NUMBER[n]}"

  # 🚫 A merge cannot be undone from the API. If a fixture that is meant to be
  #    open or closed has been merged, no amount of reconciling fixes it.
  if [[ "${have_state}" == "MERGED" && "${want_state}" != "MERGED" ]]; then
    die "Fixture ${n} (#${num}) is merged, but the inventory says ${want_state}. 💀
   A merge cannot be reversed through the API. This repository can no longer
   be reconciled — see docs/design/testing.md and rebuild the fixtures
   elsewhere."
  fi

  # Labels first, while the pull request is still open and editable.
  if [[ "${have_labels}" != "${want_labels}" ]]; then
    for label in $(printf '%s\n' "${want_labels}" | tr ',' ' '); do
      [[ -z "${label}" ]] && continue
      case ",${have_labels}," in
        *",${label},"*) ;;
        *) run gh pr edit "${num}" --repo "${SLUG}" --add-label "${label}" ;;
      esac
    done
    for label in $(printf '%s\n' "${have_labels}" | tr ',' ' '); do
      [[ -z "${label}" ]] && continue
      case ",${want_labels}," in
        *",${label},"*) ;;
        *) run gh pr edit "${num}" --repo "${SLUG}" --remove-label "${label}" ;;
      esac
    done
    did "fixture ${n}: labels now [${want_labels}]"
  fi

  # Draft is only meaningful while a pull request is open.
  if [[ "${want_state}" == "OPEN" && "${have_draft}" != "${want_draft}" ]]; then
    if [[ "${want_draft}" == "true" ]]; then
      run gh pr ready "${num}" --repo "${SLUG}" --undo
    else
      run gh pr ready "${num}" --repo "${SLUG}"
    fi
    did "fixture ${n}: draft=${want_draft}"
  fi

  if [[ "${have_state}" != "${want_state}" ]]; then
    case "${want_state}" in
      OPEN)   run gh pr reopen "${num}" --repo "${SLUG}" ;;
      CLOSED) run gh pr close  "${num}" --repo "${SLUG}" ;;
      MERGED) run gh pr merge  "${num}" --repo "${SLUG}" --merge ;;
    esac
    did "fixture ${n}: state now ${want_state}"
  fi
done

did "eight pull requests match the documented inventory"

# ---------------------------------------------------------------------------
# ✅ Verify
# ---------------------------------------------------------------------------

step "✅" "Verifying the inventory"

if [[ "${DRY_RUN}" == "true" ]]; then
  skip "dry run — nothing to count"
else
  open_count="$(gh pr list --repo "${SLUG}" --state open   --limit 100 --json number --jq 'length')"
  all_count="$(gh  pr list --repo "${SLUG}" --state all    --limit 100 --json number --jq 'length')"
  draft_count="$(gh pr list --repo "${SLUG}" --state open  --limit 100 --json isDraft --jq '[.[] | select(.isDraft)] | length')"

  printf '   📊 open=%s (want 6)   all=%s (want 8)   drafts=%s (want 2)\n' \
    "${open_count}" "${all_count}" "${draft_count}"

  if [[ "${open_count}" != "6" || "${all_count}" != "8" || "${draft_count}" != "2" ]]; then
    die "Inventory does not match the documented counts. 🚨
   Fix it *before* archiving — see docs/design/testing.md."
  fi
  ok "inventory matches docs/design/testing.md"
fi

# ---------------------------------------------------------------------------
# 🧊 Freeze
# ---------------------------------------------------------------------------

step "🧊" "Freezing"

if [[ "${UPDATE}" == "true" ]]; then
  # The repo was already configured and frozen before this run; the only thing
  # owed is the refreeze, and the cleanup trap owns that.
  if [[ "${DRY_RUN}" == "true" ]]; then
    skip "dry run — nothing was thawed, so nothing needs refreezing"
  else
    skip "the cleanup trap refreezes ${SLUG} on the way out"
  fi
elif [[ "${ARCHIVE}" != "true" ]]; then
  skip "not archiving (pass --archive once 'make e2e' is green)"
  info "Archiving is the strongest lock available: archived repos are read-only"
  info "and accept no new PRs, but existing ones stay queryable — the GraphQL"
  info "query has no isArchived filter. 🔗 docs/design/testing.md"
else
  # Settings changes are rejected once archived, so these must come first.
  run gh api -X DELETE "repos/${SLUG}/vulnerability-alerts"
  run gh repo edit "${SLUG}" --enable-issues=false --enable-wiki=false
  run gh repo archive "${SLUG}" --yes
  did "${SLUG} archived and read-only"
fi

# ---------------------------------------------------------------------------
# 🎉 Done
# ---------------------------------------------------------------------------

printf '\n🎉 \033[1mBreakfast is served.\033[0m\n\n'
if [[ "${UPDATE}" == "true" ]]; then
  info "Re-run the suite against the repaired fixtures:"
  printf '   🔗 make e2e\n'
  if [[ "${UNARCHIVED}" == "true" ]]; then
    info "The refreeze happens as this script exits — watch for it below. 🧊"
  fi
else
  info "Point the suite at it:"
  printf '   🔗 breakfast -o %s --format json --no-colour\n' "${ORG}"
  info "Then update tests/e2e/ and docs/design/testing.md to the new owner."
fi
printf '\n'
