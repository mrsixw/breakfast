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
LATEST_RELEASE_JSON=$(curl -s "https://api.github.com/repos/${REPO}/releases/latest")
LATEST_RELEASE_URL=$(echo "${LATEST_RELEASE_JSON}" | grep -o "https://github.com/${REPO}/releases/download/[^/ ]*/${BINARY_NAME}" | head -n 1)
LATEST_TAG=$(echo "${LATEST_RELEASE_JSON}" | grep -o '"tag_name": *"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"')
RELEASE_BASE_URL="https://github.com/${REPO}/releases/download/${LATEST_TAG}"

if [ -z "${LATEST_RELEASE_URL}" ]; then
    echo -e "${BOLD}\033[31m❌ Failed to find the latest release for ${REPO}.${RESET}"
    exit 1
fi

echo -e "${GREEN}Found latest release! Downloading...${RESET}"

# Create install directory if it doesn't exist
mkdir -p "${INSTALL_DIR}"

# Download the binary
curl -sL "${LATEST_RELEASE_URL}" -o "${EXECUTABLE_PATH}"
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

# Check if INSTALL_DIR is in PATH
if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    echo -e "\n${BOLD}${YELLOW}⚠️  Warning: ${INSTALL_DIR} is not in your PATH.${RESET}"
    echo -e "To use ${BINARY_NAME} globally, add this to your ~/.bashrc or ~/.zshrc:"
    echo -e "  ${BOLD}export PATH=\"${INSTALL_DIR}:\$PATH\"${RESET}"
fi

echo -e "\n${BOLD}Try running it now:${RESET}"
echo -e "  ${BINARY_NAME} --help"
