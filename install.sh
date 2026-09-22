#!/usr/bin/env bash

set -e

REPO="mrsixw/breakfast"
BINARY_NAME="breakfast"
INSTALL_DIR="${HOME}/.local/bin"
EXECUTABLE_PATH="${INSTALL_DIR}/${BINARY_NAME}"
MAN_DIR="${HOME}/.local/share/man/man1"
BASH_COMPLETION_DIR="${HOME}/.local/share/bash-completion/completions"
ZSH_COMPLETION_DIR="${HOME}/.local/share/zsh/site-functions"
FISH_COMPLETION_DIR="${HOME}/.config/fish/completions"

# Setup colors
BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[34m"
RESET="\033[0m"

echo -e "${BOLD}${BLUE}🍳 Serving up breakfast...${RESET}"

# Find the latest release
echo -e "${YELLOW}Finding the latest version...${RESET}"
LATEST_RELEASE_JSON=$(curl -sf "https://api.github.com/repos/${REPO}/releases/latest") || {
    echo -e "${BOLD}\033[31m❌ Failed to fetch release info for ${REPO}.${RESET}"
    exit 1
}
LATEST_TAG=$(printf '%s' "${LATEST_RELEASE_JSON}" | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])") || {
    echo -e "${BOLD}\033[31m❌ Failed to parse release tag for ${REPO}.${RESET}"
    exit 1
}
RELEASE_BASE_URL="https://github.com/${REPO}/releases/download/${LATEST_TAG}"
LATEST_RELEASE_URL=$(printf '%s' "${LATEST_RELEASE_JSON}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
urls = [a['browser_download_url'] for a in data.get('assets', []) if a['name'] == '${BINARY_NAME}']
print(urls[0] if urls else '')
")

if [ -z "${LATEST_RELEASE_URL}" ]; then
    echo -e "${BOLD}\033[31m❌ Failed to find the latest release for ${REPO}.${RESET}"
    exit 1
fi

echo -e "${GREEN}Found latest release! Downloading...${RESET}"

# Create install directory if it doesn't exist
mkdir -p "${INSTALL_DIR}"

# Download the binary
if ! curl -sfL "${LATEST_RELEASE_URL}" -o "${EXECUTABLE_PATH}"; then
    echo -e "${BOLD}\033[31m❌ Failed to download binary from ${LATEST_RELEASE_URL}.${RESET}"
    exit 1
fi
chmod +x "${EXECUTABLE_PATH}"

echo -e "${BOLD}${GREEN}✅ Successfully installed ${BINARY_NAME} to ${EXECUTABLE_PATH}!${RESET}"

# Run version check
echo -ne "${BLUE}Installed version: ${RESET}"
"${EXECUTABLE_PATH}" --version

# Initialize default config
echo -e "${YELLOW}Initializing default configuration...${RESET}"
"${EXECUTABLE_PATH}" --init-config

# Install man page
echo -e "${YELLOW}Installing man page...${RESET}"
mkdir -p "${MAN_DIR}"
if curl -sfL "${RELEASE_BASE_URL}/breakfast.1.gz" -o "${MAN_DIR}/breakfast.1.gz"; then
    echo -e "${GREEN}📖 Man page installed. Run: ${BOLD}man breakfast${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install man page (non-fatal).${RESET}"
fi

# Install shell completions
echo -e "${YELLOW}Installing shell completions...${RESET}"

mkdir -p "${BASH_COMPLETION_DIR}"
if curl -sfL "${RELEASE_BASE_URL}/breakfast.bash" -o "${BASH_COMPLETION_DIR}/breakfast"; then
    echo -e "${GREEN}✅ Bash completion installed.${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install bash completion (non-fatal).${RESET}"
fi

mkdir -p "${ZSH_COMPLETION_DIR}"
if curl -sfL "${RELEASE_BASE_URL}/_breakfast" -o "${ZSH_COMPLETION_DIR}/_breakfast"; then
    echo -e "${GREEN}✅ Zsh completion installed.${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install zsh completion (non-fatal).${RESET}"
fi

mkdir -p "${FISH_COMPLETION_DIR}"
if curl -sfL "${RELEASE_BASE_URL}/breakfast.fish" -o "${FISH_COMPLETION_DIR}/breakfast.fish"; then
    echo -e "${GREEN}✅ Fish completion installed.${RESET}"
else
    echo -e "${YELLOW}⚠️  Could not install fish completion (non-fatal).${RESET}"
fi

# Dropping the completion files into place is only half the job — bash and zsh
# both need a line in the user's rc file before they will load them. Print the
# snippet for the shell they are actually using rather than all three.
# Print only: this script is normally run piped through curl, where prompting is
# unreliable, so it never edits rc files on the user's behalf.
echo -e "\n${BOLD}To finish enabling completions:${RESET}"
case "${SHELL##*/}" in
    *bash*)
        echo -e "Add this to your ${BOLD}~/.bashrc${RESET}:"
        echo -e "  ${BOLD}source \"${BASH_COMPLETION_DIR}/${BINARY_NAME}\"${RESET}"
        echo -e "(If you already have the ${BOLD}bash-completion${RESET} package installed, it will be picked up automatically and you can skip this.)"
        echo -e "Then restart your shell."
        ;;
    *zsh*)
        echo -e "Add this to your ${BOLD}~/.zshrc${RESET}, above any existing ${BOLD}compinit${RESET} call:"
        echo -e "  ${BOLD}fpath=(\"${ZSH_COMPLETION_DIR}\" \$fpath)${RESET}"
        echo -e "If you don't already initialise completions (Oh My Zsh and friends do), add this too:"
        echo -e "  ${BOLD}autoload -Uz compinit && compinit${RESET}"
        echo -e "Then restart your shell."
        ;;
    *fish*)
        echo -e "${GREEN}Nothing to do — fish loads completions from ${FISH_COMPLETION_DIR} automatically.${RESET}"
        echo -e "New shells will pick them up."
        ;;
    *)
        echo -e "bash — add to ${BOLD}~/.bashrc${RESET}:"
        echo -e "  ${BOLD}source \"${BASH_COMPLETION_DIR}/${BINARY_NAME}\"${RESET}"
        echo -e "zsh  — add to ${BOLD}~/.zshrc${RESET}, above any existing ${BOLD}compinit${RESET} call:"
        echo -e "  ${BOLD}fpath=(\"${ZSH_COMPLETION_DIR}\" \$fpath)${RESET}"
        echo -e "  ${BOLD}autoload -Uz compinit && compinit${RESET}  ${RESET}# only if you don't already initialise completions"
        echo -e "fish — nothing to do, they load automatically."
        echo -e "Then restart your shell."
        ;;
esac
echo -e "You can also load them ad hoc with ${BOLD}eval \"\$(${BINARY_NAME} completions <shell>)\"${RESET}."

# Check if INSTALL_DIR is in PATH
if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    echo -e "\n${BOLD}${YELLOW}⚠️  Warning: ${INSTALL_DIR} is not in your PATH.${RESET}"
    echo -e "To use ${BINARY_NAME} globally, add this to your ~/.bashrc or ~/.zshrc:"
    echo -e "  ${BOLD}export PATH=\"${INSTALL_DIR}:\$PATH\"${RESET}"
fi

# Check if MAN_DIR is findable by man
if ! man --path 2>/dev/null | tr ':' '\n' | grep -qx "${MAN_DIR%/man1}"; then
    echo -e "\n${BOLD}${YELLOW}⚠️  Warning: ${MAN_DIR} is not in your MANPATH.${RESET}"
    echo -e "To use ${BOLD}man breakfast${RESET}, add this to your ~/.bashrc or ~/.zshrc:"
    echo -e "  ${BOLD}export MANPATH=\"${MAN_DIR%/man1}:\${MANPATH}\"${RESET}"
fi

# Resolve a path to its real location, following symlinked directories, so a
# ~/.local/bin that is itself a symlink does not read as a different install.
# Only the directory is resolved: the binary we install may legitimately be a
# symlink, and replacing the link is what an install is supposed to do.
resolve_path() {
    local target="${1}" dir base
    dir="$(dirname "${target}")"
    base="$(basename "${target}")"
    if [ -d "${dir}" ]; then
        dir="$(cd -P "${dir}" 2>/dev/null && pwd)" || dir="$(dirname "${target}")"
    fi
    printf '%s/%s' "${dir}" "${base}"
}

# Having ${INSTALL_DIR} on PATH is not the same as winning on PATH. A stale copy
# earlier in the search order silently takes every invocation, and the installer
# above has just reported complete success — so the user runs an old binary and
# blames the features that appear to be missing: `completions` reports "No such
# command", `update` rewrites a copy they never invoke. Check what the shell
# would actually resolve, not merely where we put the file.
SHADOW_STATUS=0
RESOLVED_PATH="$(command -v "${BINARY_NAME}" 2>/dev/null || true)"
if [ -n "${RESOLVED_PATH}" ] \
    && [ "$(resolve_path "${RESOLVED_PATH}")" != "$(resolve_path "${EXECUTABLE_PATH}")" ]; then
    echo -e "\n${BOLD}\033[31m❌ Another ${BINARY_NAME} shadows this install.${RESET}"
    echo -e "   ${BOLD}Installed:${RESET} ${EXECUTABLE_PATH}"
    echo -e "   ${BOLD}Shadowed by:${RESET} ${RESOLVED_PATH}  ${YELLOW}← this is what runs${RESET}"
    echo -e "\nThe rogue copy wins because it comes first in your PATH. Until it is"
    echo -e "removed or your PATH is reordered, ${BINARY_NAME} will keep running the"
    echo -e "old binary — which is how a missing ${BOLD}completions${RESET} command, or"
    echo -e "an ${BOLD}update${RESET} that never seems to take effect usually shows up."
    echo -e "\nRemove it with:"
    echo -e "  ${BOLD}rm \"${RESOLVED_PATH}\"${RESET}"
    echo -e "then re-run this installer to confirm."
    SHADOW_STATUS=1
fi

# Suppressed when shadowed: pointing the user at `${BINARY_NAME} --help` directly
# below a warning that `${BINARY_NAME}` runs something else would be telling them
# to invoke the very binary we just said is the wrong one.
if [ "${SHADOW_STATUS}" -eq 0 ]; then
    echo -e "\n${BOLD}Try running it now:${RESET}"
    echo -e "  ${BINARY_NAME} --help"
fi

# Non-zero when shadowed: the install did put the binary in place, but the
# command the user is about to type still is not it. Reporting success there is
# the bug this exits for.
exit ${SHADOW_STATUS}
