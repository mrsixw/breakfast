# Installation

## Prerequisites

- Python 3.11 or later
- A [GitHub personal access token](https://github.com/settings/tokens) with `repo` scope

## Install uv

If you do not already have [uv](https://docs.astral.sh/uv/), install it first:

```bash
python -m pip install --user uv
```

## Install from source

Clone the repository and install the runtime dependencies:

```bash
git clone https://github.com/mrsixw/breakfast.git
cd breakfast
uv sync
```

## Build the binary

breakfast can be built as a standalone [shiv](https://github.com/linkedin/shiv) executable:

```bash
uv sync --extra build
uv run shiv -c breakfast -o breakfast .
```

This produces a `./breakfast` binary that can be copied anywhere on your `PATH`.

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
