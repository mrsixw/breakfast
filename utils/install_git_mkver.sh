#!/usr/bin/env bash
set -euo pipefail

api_url="https://api.github.com/repos/idc101/git-mkver/releases/latest"

asset_url=$(python - <<'PY'
import json
import sys
from urllib.request import urlopen

api_url = "https://api.github.com/repos/idc101/git-mkver/releases/latest"

with urlopen(api_url) as response:
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
