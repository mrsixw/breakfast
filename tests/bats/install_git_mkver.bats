#!/usr/bin/env bats
#
# 🔧 utils/install_git_mkver.sh — fetches the git-mkver release binary in CI.
#
# It writes to /usr/local/bin, so every collaborator is stubbed: nothing here
# downloads, unpacks or installs anything for real.

setup() {
  load 'helpers/common'
  common_setup

  # The embedded Python picks the asset URL out of the GitHub API response.
  # Stubbing `python` keeps the test offline; the URL is the contract between
  # that step and the rest of the script.
  stub python <<'STUB'
if [[ -n "${PYTHON_FAILS:-}" ]]; then
  echo "No suitable git-mkver asset found" >&2
  exit 1
fi
printf '%s\n' "https://example.invalid/git-mkver-linux-x86_64.tar.gz"
STUB
  stub curl <<'STUB'
[[ -n "${CURL_FAILS:-}" ]] && exit 22
exit 0
STUB
  stub tar <<'STUB'
[[ -n "${TAR_FAILS:-}" ]] && exit 2
exit 0
STUB
  stub_silent install
}

@test "downloads the asset URL the API step resolved" {
  run "${REPO_ROOT}/utils/install_git_mkver.sh"

  [ "$status" -eq 0 ]
  assert_called curl "https://example.invalid/git-mkver-linux-x86_64.tar.gz"
}

@test "downloads to the very path it later unpacks" {
  # Two hardcoded copies of /tmp/git-mkver.tar.gz that can drift apart: if the
  # download lands somewhere else, tar unpacks a stale file or nothing at all.
  run "${REPO_ROOT}/utils/install_git_mkver.sh"

  [ "$status" -eq 0 ]
  assert_called curl "-o /tmp/git-mkver.tar.gz"
  assert_called tar "-xzf /tmp/git-mkver.tar.gz"
}

@test "unpacks and installs the binary executable" {
  run "${REPO_ROOT}/utils/install_git_mkver.sh"

  [ "$status" -eq 0 ]
  assert_called tar "-xzf /tmp/git-mkver.tar.gz -C /tmp"
  assert_called install "-m 0755 /tmp/git-mkver /usr/local/bin/git-mkver"
}

@test "stops before downloading when no suitable asset is found" {
  export PYTHON_FAILS=1

  run "${REPO_ROOT}/utils/install_git_mkver.sh"

  [ "$status" -ne 0 ]
  refute_called curl
  refute_called install
}

@test "stops before unpacking when the download fails" {
  # Without set -e this would tar an absent file and install whatever was left
  # in /tmp from a previous run.
  export CURL_FAILS=1

  run "${REPO_ROOT}/utils/install_git_mkver.sh"

  [ "$status" -ne 0 ]
  refute_called tar
  refute_called install
}

@test "stops before installing when the tarball will not unpack" {
  export TAR_FAILS=1

  run "${REPO_ROOT}/utils/install_git_mkver.sh"

  [ "$status" -ne 0 ]
  refute_called install
}
