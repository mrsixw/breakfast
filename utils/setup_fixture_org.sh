#!/usr/bin/env bash
#
# 🥐 setup_fixture_org.sh — provision breakfast's frozen end-to-end fixtures
#    inside a dedicated GitHub organisation.
#
# The end-to-end suite asserts *exact* pull request counts, so the fixtures it
# queries must be reproducible byte for byte. This script is that reproduction:
# it builds the eight-pull-request inventory documented in
# docs/design/testing.md, in an org of your choosing.
#
# 🔗 Issue:      https://github.com/mrsixw/breakfast/issues/456
# 🔗 Doctrine:   docs/design/testing.md
# 🔗 Machine account follow-up: https://github.com/mrsixw/breakfast/issues/452
#
# Usage:
#   ./utils/setup_fixture_org.sh <org> [--repo NAME] [--dry-run] [--archive]
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

usage() {
  cat <<'USAGE'
🍳 Provision the breakfast end-to-end fixture organisation.

  ./utils/setup_fixture_org.sh <org> [options]

  <org>            The GitHub organisation login to provision into. Required —
                   there is no default, because getting this wrong writes eight
                   pull requests into somebody's real account. 😬

Options:
  --repo NAME      Fixture repository name (default: breakfast-fixtures).
  --dry-run        Print every mutating command instead of running it. 🌀
  --archive        Freeze the repo at the end (read-only). Do NOT pass this
                   until `make e2e` has gone green against the new fixtures —
                   archived repos reject changes, so a mistaken inventory needs
                   unarchiving to fix. 🧊
  -h, --help       Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)    REPO="${2:?--repo needs a value}"; shift 2 ;;
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

# 🛡️  The existing fixtures are frozen and asserted by exact count. Refuse to
#     point this script at them, whatever else the arguments say.
#     Compared lowercased because GitHub logins are case-insensitive, and via
#     tr rather than ${SLUG,,} because macOS still ships bash 3.2. 🍎
SLUG_LOWER="$(printf '%s' "${SLUG}" | tr '[:upper:]' '[:lower:]')"
if [[ "${SLUG_LOWER}" == "mrsixw/breakfast-fixtures" ]]; then
  die "Refusing to touch mrsixw/breakfast-fixtures — it is frozen. 🧊
   See docs/design/testing.md. Provision a new org instead."
fi

printf '\n🥞 \033[1mbreakfast fixture provisioner\033[0m\n'
info "target:  ${SLUG}"
info "dry-run: ${DRY_RUN}   archive-at-end: ${ARCHIVE}"

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
if ! gh api "orgs/${ORG}" >/dev/null 2>&1; then
  die "Organisation '${ORG}' not found, or your token cannot see it. 🏢
   Organisations cannot be created from the API — make it by hand first:
   🔗 https://github.com/organizations/plan  (the Free plan is plenty)
   Then re-run this script."
fi
ok "organisation ${ORG} exists"

# ---------------------------------------------------------------------------
# 📦 Repository
# ---------------------------------------------------------------------------

step "📦" "Fixture repository"

if gh repo view "${SLUG}" >/dev/null 2>&1; then
  skip "${SLUG} already exists"
  EXISTING_PRS="$(gh pr list --repo "${SLUG}" --state all --limit 100 --json number --jq 'length')"
  if [[ "${EXISTING_PRS}" != "0" ]]; then
    die "${SLUG} already holds ${EXISTING_PRS} pull requests. 🛑
   This script seeds a *fresh* repo; re-seeding would duplicate the inventory
   and break the exact-count assertions. Delete the repo, or pass --repo NAME
   to seed a different one."
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
else
  run gh repo create "${SLUG}" --public \
    --description "Frozen PR fixtures for breakfast's end-to-end suite. Do not modify."
  did "created ${SLUG}"
fi

# ---------------------------------------------------------------------------
# 📝 README
# ---------------------------------------------------------------------------

step "📝" "Seeding the warning README"

WORKTREE="$(mktemp -d)"
trap 'cd / && rm -rf "${WORKTREE}"' EXIT
info "scratch clone: ${WORKTREE}"

if [[ "${DRY_RUN}" == "true" ]]; then
  printf '   🌀 \033[2mwould clone, commit README.md and push\033[0m\n'
else
  git clone --quiet "https://github.com/${SLUG}.git" "${WORKTREE}/repo"
  cd "${WORKTREE}/repo"

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

# ---------------------------------------------------------------------------
# 🏷️ Labels
# ---------------------------------------------------------------------------

step "🏷️" "Labels"

run gh label create wip --repo "${SLUG}" --color ededed --force
for label in bug enhancement; do
  run gh label create "${label}" --repo "${SLUG}" --force
done
did "wip, bug, enhancement ready"

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

step "🍳" "Cooking eight pull requests"

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

# 🥚 Fixture number -> the PR number GitHub actually minted. Never assume 1..8;
#    a stray pull request would shift every later edit onto the wrong target.
declare -a PR_NUMBER

for index in "${!TITLES[@]}"; do
  n=$((index + 1))
  title="${TITLES[${index}]}"
  branch="fixture-${n}"

  printf '   🍽️  %d/8  %s\n' "${n}" "${title}"

  if [[ "${DRY_RUN}" == "true" ]]; then
    printf '      🌀 \033[2mwould branch %s, commit, push and open a PR\033[0m\n' "${branch}"
    PR_NUMBER[${n}]="${n}"
    continue
  fi

  git checkout --quiet main
  git checkout --quiet -b "${branch}"
  echo "${title}" > "fixture-${n}.txt"
  git add .
  git commit --quiet -m "${title}"
  git push --quiet -u origin "${branch}"

  # 🥸 The expansion below looks like a typo but is not: under `set -u`,
  #    bash 3.2 treats "${arr[@]}" on an empty array as an unbound variable.
  #    "${arr[@]+"${arr[@]}"}" expands to nothing instead of exploding.
  draft_flag=()
  [[ ${n} -eq 5 || ${n} -eq 6 ]] && draft_flag=(--draft)

  url="$(gh pr create --repo "${SLUG}" "${draft_flag[@]+"${draft_flag[@]}"}" \
    --base main --head "${branch}" \
    --title "${title}" --body "🧊 Frozen fixture. Do not modify.")"

  PR_NUMBER[${n}]="${url##*/}"
  info "→ ${url}"
done

did "eight pull requests opened"

# ---------------------------------------------------------------------------
# 🎨 Labels, closure and the merge
# ---------------------------------------------------------------------------

step "🎨" "Applying labels"

run gh pr edit "${PR_NUMBER[2]}" --repo "${SLUG}" --add-label bug
run gh pr edit "${PR_NUMBER[3]}" --repo "${SLUG}" --add-label enhancement
run gh pr edit "${PR_NUMBER[4]}" --repo "${SLUG}" --add-label bug --add-label wip
run gh pr edit "${PR_NUMBER[6]}" --repo "${SLUG}" --add-label enhancement
did "labels applied to fixtures 2, 3, 4 and 6"

step "🚪" "Closing fixture 7 and merging fixture 8"

run gh pr close "${PR_NUMBER[7]}" --repo "${SLUG}"
run gh pr merge "${PR_NUMBER[8]}" --repo "${SLUG}" --merge
did "one closed, one merged"

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

if [[ "${ARCHIVE}" != "true" ]]; then
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
info "Point the suite at it:"
printf '   🔗 breakfast -o %s --format json --no-colour\n' "${ORG}"
info "Then update tests/e2e/ and docs/design/testing.md to the new owner."
printf '\n'
