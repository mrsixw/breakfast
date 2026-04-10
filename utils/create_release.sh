#!/usr/bin/env bash
set -euo pipefail

version="$1"
tag="v${version}"

gh release create "${tag}" ./breakfast \
  man1/breakfast.1.gz \
  completions/breakfast.bash \
  completions/_breakfast \
  completions/breakfast.fish \
  --title "${tag}" \
  --generate-notes \
  --target "$(git rev-parse HEAD)"
