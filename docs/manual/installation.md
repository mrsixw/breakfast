# Installation

## Primary Method: One-liner

Install the latest pre-compiled binary instantly:

```bash
curl -sSL https://raw.githubusercontent.com/mrsixw/breakfast/main/install.sh | bash
```

This script will:
1. Download the latest `breakfast` binary from GitHub Releases.
2. Install it to `~/.local/bin/breakfast`.
3. Initialize a default configuration file at `~/.config/breakfast/config.toml`.

## Advanced: Install from source

If you want to contribute or build manually, follow these steps.

### Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) package manager
- A [GitHub personal access token](https://github.com/settings/tokens) with `repo` scope

### Build the binary

```bash
git clone https://github.com/mrsixw/breakfast.git
cd breakfast
make build
```

This produces a `./breakfast` standalone executable using [shiv](https://github.com/linkedin/shiv).

## Set up your GitHub token

breakfast requires a `GITHUB_TOKEN` environment variable:

```bash
export GITHUB_TOKEN="ghp_your_token_here"
```

Add this to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.) to make it persistent.

## Verify installation

```bash
# If installed via uv
uv run breakfast --version

# If using the built binary
./breakfast --version
```
