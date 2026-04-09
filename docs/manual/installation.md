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

## Shell completions

The installer (`install.sh`) automatically installs tab-completion scripts for bash, zsh, and fish. After installation, you may need to activate them for your shell:

**Bash** — source the script in your `~/.bashrc`:
```bash
source ~/.local/share/bash-completion/completions/breakfast
```
Or, if your system loads all files from `~/.local/share/bash-completion/completions/` automatically (common with `bash-completion` ≥ 2.x), no action is needed.

**Zsh** — add the install directory to your `fpath` in `~/.zshrc` before calling `compinit`:
```zsh
fpath=(~/.local/share/zsh/site-functions $fpath)
autoload -Uz compinit && compinit
```

**Fish** — completions in `~/.config/fish/completions/` are loaded automatically. No further action needed.

To regenerate completions manually from source:
```bash
make completions   # writes to completions/
```

## Man page

The installer places the man page at `~/.local/share/man/man1/breakfast.1.gz`. To use it:

```bash
man breakfast
```

If `man` can't find it, ensure your `MANPATH` includes `~/.local/share/man`:
```bash
export MANPATH="${HOME}/.local/share/man:${MANPATH}"
```

Add this line to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.) to make it permanent.

To regenerate the man page from source:
```bash
make man   # writes to man1/breakfast.1.gz
```
