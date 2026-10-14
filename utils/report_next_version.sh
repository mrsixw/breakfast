#!/usr/bin/env bash
#
# Report the version the next release would carry, before anything is merged.
#
# The release job only runs on pushes to main, so until this existed the first
# anyone knew of the next version was after it had been tagged and published.
# #417 was committed as `feat!:` — correct Conventional Commits, and also an
# instruction to git-mkver to bump the major version. 0.107.1 became 1.0.0 and
# nobody saw it coming. Run on every pull request, this makes that visible.
#
# It also means an unparsable mkver.conf reddens the pull request rather than
# main, because git mkver has to succeed here for the script to.

set -euo pipefail

# Overridable so the bats suite can point at a temporary file.
VERSION_FILE="${VERSION_FILE:-VERSION}"

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RESET="\033[0m"

if [[ ! -f "${VERSION_FILE}" ]]; then
  printf '%bNo version file at %s.%b\n' "${BOLD}" "${VERSION_FILE}" "${RESET}" >&2
  exit 1
fi

current="$(tr -d '[:space:]' < "${VERSION_FILE}")"

if ! raw_next="$(git mkver next)"; then
  printf '%bgit mkver could not compute the next version.%b\n' \
    "${BOLD}" "${RESET}" >&2
  printf 'Usually a malformed mkver.conf, or a history with no tags.\n' >&2
  exit 1
fi

# Off a release branch mkver appends +branch.hash, and a pre-release adds
# -RC1, so take the X.Y.Z core rather than the whole string.
next="$(printf '%s' "${raw_next}" \
  | tr -d '[:space:]' \
  | sed -E 's/^([0-9]+\.[0-9]+\.[0-9]+).*$/\1/')"

if [[ ! "${next}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf '%bCould not read a version out of git mkver: %s%b\n' \
    "${BOLD}" "${raw_next}" "${RESET}" >&2
  exit 1
fi

printf '%bCurrent VERSION%b : %s\n' "${BOLD}" "${RESET}" "${current}"
printf '%bNext release%b    : %s\n' "${BOLD}" "${RESET}" "${next}"

report="Current VERSION: \`${current}\`"$'\n'"Next release: \`${next}\`"

if [[ "${current%%.*}" != "${next%%.*}" ]]; then
  warning=$(
    printf '⚠️  MAJOR version bump: %s → %s.\n' "${current}" "${next}"
    printf "A commit since the last tag used '!' after its type (e.g. feat!:),\n"
    printf 'or carried BREAKING CHANGE in its body. Either one tells\n'
    printf 'git-mkver to bump the major version.\n'
    printf 'Quoting either marker counts: mkver matches it anywhere on a\n'
    printf 'line, so a body explaining one reads as declaring one.\n'
    printf 'Reword the commit if that was not intended.\n'
  )
  printf '%b%s%b' "${YELLOW}${BOLD}" "${warning}" "${RESET}"
  report="${report}"$'\n\n'"${warning}"
else
  printf '%bNo major version change.%b\n' "${GREEN}" "${RESET}"
fi

# Actions shows this on the run's summary page, where it is read without
# opening a log.
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    printf '### Next release version\n\n'
    printf '%s\n' "${report}"
  } >> "${GITHUB_STEP_SUMMARY}"
fi
