# Config File Design for breakfast

> **Tracking issue:** [#42 — Add config file support](https://github.com/mrsixw/breakfast/issues/42)

## Overview

Add a config file so users can set persistent defaults for CLI options, avoiding
repetitive long command lines like:

```bash
breakfast -o my-org -r my-app --ignore-author dependabot[bot] --ignore-author renovate[bot] --age --mine-only
```

With a config file, the above becomes just:

```bash
breakfast
```

## File Location and Format

### Location (in priority order)
1. `--config <path>` CLI flag (explicit override)
2. `.breakfast.toml` in the current directory (project-level config)
3. `~/.config/breakfast/config.toml` (user-level config, XDG-compliant)

Project-level config takes precedence over user-level config. Both are
merged, with project-level values overriding user-level on a per-key basis.

### Why TOML?
- Already standard in the Python ecosystem (`pyproject.toml`)
- Human-readable and easy to edit
- Python 3.11+ includes `tomllib` in stdlib — zero additional dependencies
- Familiar to the target audience (developers)

## Config File Schema

```toml
# ~/.config/breakfast/config.toml

# Default organization(s) to query
# String for single org, array for multiple
organization = "my-org"
# organization = ["org1", "org2"]  # when multi-org support lands

# Default repo filter (substring match, or glob when #7 lands)
repo-filter = "my-app"

# Authors to always ignore (case-insensitive)
ignore-author = ["dependabot[bot]", "renovate[bot]"]

# Always show the age column
age = true

# Always show only my PRs
mine-only = false

# Default output format: "table" or "json"
format = "table"

# Default sort column (when --sort lands)
# sort = "age"
# reverse = false

# Stale threshold in days (when --stale lands)
# stale = 30

# Draft filter (when --draft lands): true = drafts only, false = no drafts, omit = all
# draft = false

# CI checks column (when --checks lands)
# checks = false
```

## CLI vs Config Precedence Rules

The principle: **CLI flags always win over config file values.**

| Scenario | Behavior |
|----------|----------|
| Config sets `organization = "org-a"`, CLI passes `-o org-b` | Uses `org-b` |
| Config sets `age = true`, CLI passes nothing | Age column shown |
| Config sets `age = true`, CLI passes `--no-age` | Age column hidden |
| Config sets `ignore-author = ["bot"]`, CLI passes `--ignore-author alice` | Ignores both `bot` AND `alice` (merged) |
| Config sets `mine-only = true`, CLI passes `--no-mine-only` | Shows all PRs |
| No config, no CLI flags for a field | Uses Click's built-in default |

### Merge strategy by type

- **Scalar values** (organization, repo-filter, format, sort): CLI replaces config
- **List values** (ignore-author, label, exclude-label): CLI *appends* to config values. To clear config defaults, use `--no-ignore-author` (new flag) or `--config /dev/null`
- **Boolean flags** (age, mine-only, draft, checks): CLI replaces config. Add `--no-<flag>` counterparts so users can explicitly disable config defaults

## Implementation Plan

### 1. Config loading (new function)

```python
import tomllib  # stdlib in Python 3.11+
from pathlib import Path

DEFAULT_CONFIG_PATHS = [
    Path(".breakfast.toml"),                              # project-level
    Path.home() / ".config" / "breakfast" / "config.toml",  # user-level
]

def load_config(config_path=None):
    """Load and merge config from file(s). Returns a dict."""
    if config_path:
        # Explicit --config flag: use only that file
        paths = [Path(config_path)]
    else:
        paths = DEFAULT_CONFIG_PATHS

    merged = {}
    # Load in reverse priority order so higher-priority overwrites
    for path in reversed(paths):
        if path.exists():
            with open(path, "rb") as f:
                data = tomllib.load(f)
            for key, value in data.items():
                if isinstance(value, list) and isinstance(merged.get(key), list):
                    # Lists merge (config + config)
                    merged[key] = value + merged[key]
                else:
                    merged[key] = value
    return merged
```

### 2. CLI integration with Click

Click supports a `default_map` context setting that provides defaults from a dict.
This is the cleanest integration point:

```python
@click.command(context_settings=dict(default_map={}))
@click.option("--config", "config_path", default=None, help="Path to config file.")
@click.pass_context
def breakfast(ctx, config_path, organization, repo_filter, ignore_author, ...):
    # Load config and apply as defaults for unset options
    config = load_config(config_path)

    # Map config keys to Click parameter names
    key_map = {
        "organization": "organization",
        "repo-filter": "repo_filter",
        "ignore-author": "ignore_author",
        "age": "age",
        "mine-only": "mine_only",
        "format": "json_output",  # mapped: format=json -> json_output=True
    }
    # ... apply config values where CLI didn't provide them
```

Alternatively, use a Click callback or a custom `click.Command` subclass that
loads the config before parameter resolution. This keeps the main function clean.

### 3. New CLI flags needed

- `--config <path>` — explicit config file path
- `--no-age` — disable age column (to override `age = true` in config)
- `--no-mine-only` — disable mine-only filter (to override config)
- `--no-ignore-author` — clear all ignore-author entries from config
- `--show-config` — print the resolved config (merged config + CLI) and exit (useful for debugging)
- `--init-config` — generate a default configuration file at the XDG-compliant user path (`~/.config/breakfast/config.toml`) and exit.

### Config File Generation

The `--init-config` flag provides a quick start for users:
1. Checks if `~/.config/breakfast/config.toml` already exists (to avoid overwriting).
2. Creates the directory structure if missing.
3. Writes a commented-out template with common defaults.
4. Provides feedback to the user on where the file was created and how to edit it.

The XDG Base Directory path is prioritized for initialization to keep the user's home directory clean, following modern Linux/macOS conventions.

### 4. Config file discovery feedback

When running with verbose output or `--show-config`, show which config file(s) were loaded:

```
Using config: ~/.config/breakfast/config.toml
Using config: .breakfast.toml (project override)
```

## Behavioral Changes Summary

| Without config file | With config file |
|---------------------|-----------------|
| All options must be passed on every invocation | Defaults loaded from file |
| No way to set org-wide defaults | `.breakfast.toml` in project root sets team defaults |
| Users repeat `--ignore-author bot` everywhere | Set once in config, applies everywhere |
| `breakfast` with no args is an error (no org) | `breakfast` with no args works if org is in config |

## What Goes in Config vs What Doesn't

**Belongs in config:**
- organization, repo-filter, ignore-author (stable, per-user/project preferences)
- age, mine-only, format (display preferences)
- sort, stale, draft, checks (when those features land)

**Does NOT belong in config:**
- `GITHUB_TOKEN` — this is a secret; keep it in environment variables only
- One-off flags that change per invocation (e.g., a hypothetical `--since` date filter)

## Example User Workflows

### Personal defaults
```toml
# ~/.config/breakfast/config.toml
organization = "my-company"
ignore-author = ["dependabot[bot]", "renovate[bot]", "snyk-bot"]
age = true
```

```bash
breakfast -r my-app           # uses org + ignore-author + age from config
breakfast -r other-app        # same defaults, different repo filter
breakfast -r my-app --json    # override format for piping
```

### Team/project defaults
```toml
# .breakfast.toml (committed to repo)
organization = "my-team-org"
repo-filter = "team-platform"
ignore-author = ["dependabot[bot]"]
```

```bash
breakfast                     # just works for the whole team
breakfast --mine-only         # my PRs in this project
```

### Override everything
```bash
breakfast --config /dev/null -o other-org -r other-app  # ignore all config
```

## Testing Strategy

- Unit tests for `load_config()` with various file combinations
- Test precedence: CLI > project config > user config
- Test list merging behavior (ignore-author from multiple sources)
- Test `--no-*` flags correctly disable config defaults
- Test missing/invalid config files handled gracefully (warning, not crash)
- Test `--show-config` output matches expectations
- CLI integration tests with `CliRunner` using temp config files
