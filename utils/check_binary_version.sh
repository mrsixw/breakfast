#!/usr/bin/env bash
set -euo pipefail

expected_version="$(python utils/read_version.py)"
actual_version="$(./breakfast --version | awk '{print $NF}')"

if [[ "${actual_version}" != "${expected_version}" ]]; then
  echo "Version mismatch: expected ${expected_version}, got ${actual_version}" >&2
  exit 1
fi
