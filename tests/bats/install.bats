#!/usr/bin/env bats
#
# 🍳 install.sh — the published `curl | bash` install path.
#
# install.sh ships mode 644 and is documented as `curl ... | bash`, so the tests
# drive it through `bash` exactly as a user would.
#
# HOME is redirected into the test's temporary directory, so every path the
# installer writes to lands there and nothing touches the developer's machine.

setup() {
  load 'helpers/common'
  common_setup

  # curl answers two different jobs: the binary download, and the man page
  # and completion downloads. There is no release API query to answer.
  stub curl <<'STUB'
url=""; out=""; prev=""
for arg in "$@"; do
  [[ "${prev}" == "-o" ]] && out="${arg}"
  [[ "${arg}" == http* ]] && url="${arg}"
  prev="${arg}"
done

case "${url}" in
  */breakfast)
    [[ -n "${BINARY_FAILS:-}" ]] && exit 22
    # A stand-in for the real zipapp: enough to answer --version and
    # --init-config, which the installer calls straight after downloading.
    printf '#!/usr/bin/env bash\nprintf "breakfast, version 1.2.3\\n"\n' > "${out}"
    exit 0 ;;
  *breakfast.1.gz)
    [[ -n "${MAN_FAILS:-}" ]] && exit 22
    printf 'man page\n' > "${out}"; exit 0 ;;
  *)
    [[ -n "${COMPLETIONS_FAIL:-}" ]] && exit 22
    printf 'completion\n' > "${out}"; exit 0 ;;
esac
STUB

  # `man --path` reads the host's real configuration; pin it instead.
  stub man <<'STUB'
printf '%s\n' "${FAKE_MANPATH:-/usr/share/man}"
STUB
}

@test "installs the binary, executable, under ~/.local/bin" {
  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  [ -x "${FAKE_HOME}/.local/bin/breakfast" ]
}

@test "reports the installed version and seeds a default config" {
  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "breakfast, version 1.2.3"
  assert_output_contains "Initializing default configuration"
}

@test "downloads the binary from the latest-release redirect" {
  # No API call resolves an asset URL any more: GitHub redirects this path to
  # the newest release's asset, so the installer asks for it by name.
  run bash "${REPO_ROOT}/install.sh"

  assert_called curl "https://github.com/mrsixw/breakfast/releases/latest/download/breakfast"
}

@test "installs the man page and all three completions" {
  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  [ -f "${FAKE_HOME}/.local/share/man/man1/breakfast.1.gz" ]
  [ -f "${FAKE_HOME}/.local/share/bash-completion/completions/breakfast" ]
  [ -f "${FAKE_HOME}/.local/share/zsh/site-functions/_breakfast" ]
  [ -f "${FAKE_HOME}/.config/fish/completions/breakfast.fish" ]
}

@test "pulls every extra from the latest-release redirect too" {
  # Each file is asked for by the same floating path as the binary, so none is
  # fetched from a tag pinned at build time. GitHub resolves each request
  # independently, so this does not promise all five come from one release —
  # a release published mid-install could split them.
  run bash "${REPO_ROOT}/install.sh"

  assert_called curl "/releases/latest/download/breakfast.1.gz"
  assert_called curl "/releases/latest/download/breakfast.bash"
  assert_called curl "/releases/latest/download/_breakfast"
  assert_called curl "/releases/latest/download/breakfast.fish"
}

@test "fails when the binary download fails" {
  export BINARY_FAILS=1

  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 1 ]
  assert_output_contains "Failed to download binary"
}

@test "treats a missing man page as non-fatal" {
  # The binary is installed by this point; refusing to finish over a man page
  # would leave the user worse off than a warning does.
  export MAN_FAILS=1

  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "Could not install man page"
  [ -x "${FAKE_HOME}/.local/bin/breakfast" ]
}

@test "treats missing completions as non-fatal" {
  export COMPLETIONS_FAIL=1

  run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "Could not install bash completion"
  assert_output_contains "Could not install zsh completion"
  assert_output_contains "Could not install fish completion"
}

@test "prints zsh instructions to a zsh user" {
  SHELL=/bin/zsh run bash "${REPO_ROOT}/install.sh"

  assert_output_contains "~/.zshrc"
  assert_output_contains "fpath="
  refute_output_contains "Add this to your ~/.bashrc"
}

@test "prints bash instructions to a bash user" {
  SHELL=/bin/bash run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  assert_output_contains "~/.bashrc"
  refute_output_contains "compinit"
}

@test "tells a fish user there is nothing to do" {
  SHELL=/usr/bin/fish run bash "${REPO_ROOT}/install.sh"

  assert_output_contains "Nothing to do"
}

@test "falls back to all three when the shell is unrecognised" {
  SHELL=/bin/ksh run bash "${REPO_ROOT}/install.sh"

  assert_output_contains "~/.bashrc"
  assert_output_contains "~/.zshrc"
  assert_output_contains "fish"
}

@test "warns when the install directory is not on PATH" {
  run bash "${REPO_ROOT}/install.sh"

  assert_output_contains "is not in your PATH"
}

@test "stays quiet about PATH when the install directory is already on it" {
  PATH="${FAKE_HOME}/.local/bin:${PATH}" run bash "${REPO_ROOT}/install.sh"

  # Assert the run succeeded first: a refute on its own also passes when the
  # script never started.
  [ "$status" -eq 0 ]
  refute_output_contains "is not in your PATH"
}

@test "warns when the man directory is not on MANPATH" {
  run bash "${REPO_ROOT}/install.sh"

  assert_output_contains "is not in your MANPATH"
}

@test "stays quiet about MANPATH when man already knows the directory" {
  FAKE_MANPATH="${FAKE_HOME}/.local/share/man" run bash "${REPO_ROOT}/install.sh"

  [ "$status" -eq 0 ]
  refute_output_contains "is not in your MANPATH"
}
