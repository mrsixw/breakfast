# shellcheck shell=bash
# shellcheck disable=SC2034  # Constants for the scripts that source this file.
#
# Exit codes shared by the release scripts and the CI workflow that reads them.
# Source this file instead of writing a bare number: a script that exits 3 and a
# workflow that checks `-eq 3` drift apart silently the day one of them changes.
#
#   source utils/exit_codes.sh
#   exit "${EXIT_SUPERSEDED}"

# Sourcing twice would redeclare readonly variables, which is an error.
[[ -n "${EXIT_CODES_SOURCED:-}" ]] && return
readonly EXIT_CODES_SOURCED=yes

# Success.
readonly EXIT_OK=0

# A real failure: something went wrong and a person needs to look.
readonly EXIT_FAILURE=1

# bump_version_if_tag_exists.sh: main moved past the commit this run was asked
# to release, so a newer run releases it. Not a failure. Issue #495.
#
# Deliberately not 2. Under `set -e` a failing command's own status becomes the
# script's, and both `uv lock` and `python utils/read_version.py`, which the
# script runs, exit 2 on failure (so do grep errors). ci.yml turns this code
# into a green "stood down", so if it collided with a real failure, a broken
# release would pass silently.
readonly EXIT_SUPERSEDED=3
