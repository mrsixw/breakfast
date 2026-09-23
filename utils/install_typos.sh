#!/usr/bin/env bash
#
# Install the pinned `typos` binary into a directory.
#
# The crate-ci/typos action fetches its binary with a single unretried wget, so
# one transient TLS failure fails the job — and because `spell` gates `man`,
# `release` and `verify-release`, that blocks a release. See issue #458.
#
# Usage: utils/install_typos.sh [dest-dir]   (default: /usr/local/bin)

set -euo pipefail

# Keep in step with .typos.toml's expectations; bump deliberately.
TYPOS_VERSION="1.48.0"

dest="${1:-/usr/local/bin}"

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)   target="x86_64-unknown-linux-musl" ;;
  Linux-aarch64)  target="aarch64-unknown-linux-musl" ;;
  Darwin-x86_64)  target="x86_64-apple-darwin" ;;
  Darwin-arm64)   target="aarch64-apple-darwin" ;;
  *) echo "Unsupported platform: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

archive="typos-v${TYPOS_VERSION}-${target}.tar.gz"
url="https://github.com/crate-ci/typos/releases/download/v${TYPOS_VERSION}/${archive}"

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

echo "Fetching typos v${TYPOS_VERSION} for ${target}"

# The retry flags are the entire point of this script. --retry-all-errors is
# what covers the TLS handshake failure that broke the build; --retry alone
# does not treat that as retryable.
curl --fail --silent --show-error --location \
  --retry 5 --retry-delay 2 --retry-all-errors \
  --connect-timeout 20 --max-time 180 \
  -o "${tmp}/${archive}" "${url}"

tar -xzf "${tmp}/${archive}" -C "${tmp}" ./typos

mkdir -p "${dest}"
install -m 755 "${tmp}/typos" "${dest}/typos"

echo "Installed $("${dest}/typos" --version) to ${dest}/typos"
