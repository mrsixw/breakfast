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
4. Install the man page to `~/.local/share/man/man1/breakfast.1.gz`.
5. Install tab-completion scripts for bash, zsh, and fish.

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

### Install from source

To install the built executable after compiling from source:

```bash
sudo make install
```

By default, this installs the executable to `/usr/local/bin`. You can customize the installation prefix using the `PREFIX` variable:

```bash
make install PREFIX=$HOME/.local
```

> [!NOTE]
> This compiles and installs the binary from your local source tree. If you want to download and install a pre-compiled binary instantly instead, use the primary [One-liner](#primary-method-one-liner) method.

To uninstall:

```bash
sudo make uninstall
```

If installed with a custom `PREFIX`:

```bash
make uninstall PREFIX=$HOME/.local
```

## Set up your GitHub token

breakfast requires a GitHub token, read from `GH_TOKEN` (preferred, matching the [`gh` CLI](https://cli.github.com/) convention) or `GITHUB_TOKEN` as a fallback:

```bash
export GH_TOKEN="ghp_your_token_here"
```

If `GH_TOKEN` is already set in your environment (e.g. by CI or tooling built around the `gh` CLI), breakfast will use it automatically — no need to set `GITHUB_TOKEN` too.

Add this to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.) to make it persistent.

## Verify installation

```bash
# If installed via uv
uv run breakfast --version

# If using the built binary
./breakfast --version
```

## Shell completions

breakfast ships built-in tab completion for bash, zsh, and fish via the `completions` subcommand.

### Quick setup

**Zsh** — add to `~/.zshrc`:

```zsh
eval "$(breakfast completions zsh)"
```

**Bash** — add to `~/.bashrc` (requires bash ≥ 4.4):

```bash
eval "$(breakfast completions bash)"
```

**Fish** — write once to the completions directory:

```fish
breakfast completions fish > ~/.config/fish/completions/breakfast.fish
```

### How it works

`breakfast completions SHELL` prints the eval-able completion script for the named shell to stdout and exits. This means no token or `--owner` is needed — it works before any GitHub configuration.

> The older `--completion SHELL` flag still works but is deprecated and hidden
> from `--help`. It prints a notice to stderr and will be removed in a future
> release. `eval "$(breakfast --completion bash)"` stays safe in the meantime:
> the notice goes to stderr, so only the script itself reaches your shell.

For advanced users, the underlying Click completion mechanism is also available directly via the `_BREAKFAST_COMPLETE` environment variable:

```bash
_BREAKFAST_COMPLETE=zsh_source breakfast   # zsh
_BREAKFAST_COMPLETE=bash_source breakfast  # bash
_BREAKFAST_COMPLETE=fish_source breakfast  # fish
```

### Installer-managed completions

The installer (`install.sh`) automatically installs tab-completion scripts for bash, zsh, and fish. Dropping the files into place is only half the job, though — bash and zsh both need a line in your rc file before they will load them. The installer detects your shell from `$SHELL` and prints exactly the snippet you need, falling back to all three when it cannot tell. It only prints: it never edits your rc files, since it is normally run piped through curl.

The snippets it prints are reproduced here for reference:

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

## Updating

Once installed, breakfast can replace itself with the latest release:

```bash
breakfast update
```

The swap is atomic — an interrupted download leaves the working binary in place — and nothing is written unless a newer release actually exists.

The man page is not refreshed by `update`, because it can live somewhere that needs elevated privileges. Re-run `install.sh` if you want a fresh one. Completion scripts need no refresh: they call back into the binary, so they follow it automatically.

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
