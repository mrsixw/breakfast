#!/usr/bin/env bash
set -euo pipefail

version="$1"
tag="v${version}"

gh release create "${tag}" ./breakfast \
  --title "${tag}" \
  --notes "Automated release." \
  --target "$(git rev-parse HEAD)"
