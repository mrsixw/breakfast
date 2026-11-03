# src

## Overview

Source root for the installable package (src layout, configured in
`pyproject.toml`). `src/breakfast.egg-info/` is generated build metadata and is
not documented.

## Subdirectories & Boundaries

- breakfast: [./breakfast/EGM.md](./breakfast/EGM.md) - The whole CLI. Owns the
  Click entry point (`cli.py:breakfast` and the `completions` and `update`
  subcommands), GitHub REST and GraphQL access (`api.py`), the opt-in XDG disk
  cache (`cache.py`), TOML config and PR filtering (`config.py`), output
  formats (`renderers.py`), terminal presentation (`ui.py`), self-update
  (`updater.py`), XDG path resolution (`xdg.py`), the run log (`logger.py`)
  and shared constants (`constants.py`).
