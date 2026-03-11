#!/usr/bin/env bash

set -e

REPO="mrsixw/breakfast"
BINARY_NAME="breakfast"
INSTALL_DIR="${HOME}/.local/bin"
EXECUTABLE_PATH="${INSTALL_DIR}/${BINARY_NAME}"

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

# Check if INSTALL_DIR is in PATH
if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    echo -e "\n${BOLD}${YELLOW}⚠️  Warning: ${INSTALL_DIR} is not in your PATH.${RESET}"
    echo -e "To use ${BINARY_NAME} globally, add this to your ~/.bashrc or ~/.zshrc:"
    echo -e "  ${BOLD}export PATH=\"${INSTALL_DIR}:\$PATH\"${RESET}"
fi

echo -e "\n${BOLD}Try running it now:${RESET}"
echo -e "  ${BINARY_NAME} --help"
