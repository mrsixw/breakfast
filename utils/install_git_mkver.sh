#!/usr/bin/env bash
set -euo pipefail

api_url="https://api.github.com/repos/idc101/git-mkver/releases/latest"
auth_token="${GH_TOKEN:-${GITHUB_TOKEN:-}}"

asset_url=$(AUTH_TOKEN="${auth_token}" python - <<'PY'
import json
import sys
import os
from urllib.request import Request, urlopen

api_url = "https://api.github.com/repos/idc101/git-mkver/releases/latest"
auth_token = os.getenv("AUTH_TOKEN", "")

request = Request(api_url)
if auth_token:
    request.add_header("Authorization", f"Bearer {auth_token}")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("Accept", "application/vnd.github+json")

with urlopen(request) as response:
    data = json.load(response)

assets = data.get("assets", [])
for asset in assets:
    name = asset.get("name", "")
    url = asset.get("browser_download_url", "")
    if name.endswith(".tar.gz") and "linux-x86_64" in name and url:
        print(url)
        break
else:
    raise SystemExit("No suitable git-mkver asset found")
PY
)

curl -fsSL -o /tmp/git-mkver.tar.gz "$asset_url"
tar -xzf /tmp/git-mkver.tar.gz -C /tmp
install -m 0755 /tmp/git-mkver /usr/local/bin/git-mkver
