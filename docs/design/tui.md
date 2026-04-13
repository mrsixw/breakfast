# Design: Text User Interface (TUI)

## Overview

This document outlines the architecture for adding a Text User Interface (TUI) to the `breakfast` CLI. The goal is to provide an interactive way to view and manage GitHub PRs without losing the ability to run the tool in its original, static table mode.

## Architecture

### Framework

We will use the **Textual** framework (`textual` package on PyPI). Textual is the modern standard for Python TUIs, built on top of `rich`. It provides a robust, event-driven, asynchronous architecture for building terminal applications.

### Integration Approach: Threading

The current `breakfast` architecture relies on synchronous API calls via the `requests` library (located in `api.py` / `src/breakfast/api.py`).

To integrate this synchronous API with the asynchronous Textual framework without blocking the event loop (which would freeze the UI), we will adopt the **Threading** approach:

1. **Async Wrapper:** We will use `asyncio.to_thread` within the Textual application to execute the existing, unmodified synchronous functions from `api.py`.
2. **Preservation of CLI:** The existing `cli.py` (or `breakfast.py`) logic will remain synchronous. The TUI will be gated behind a new `--tui` flag.
3. **Execution Flow:**
   - If `breakfast` is run without `--tui`, it executes the traditional static table rendering.
   - If `breakfast --tui` is executed, it parses configuration and launches the `Textual` app. The app's `on_mount` lifecycle event will trigger a background thread to fetch data via `api.get_github_prs()`.

### Why Threading?

Rewriting the API layer to use asynchronous I/O (e.g., `httpx`) would require either maintaining two parallel API modules or heavily refactoring the existing synchronous CLI to use `asyncio.run()`, adding unnecessary complexity and risk. The threading approach isolates the TUI complexity while leaving the proven CLI core untouched.

## TUI Layout

The TUI will consist of:

- **Header:** Displaying the tool name and current context.
- **Main Content:** A `DataTable` or custom list view to present PRs, reusing existing formatting logic (e.g., check status colors).
- **Footer:** Displaying interactive keybindings (e.g., `q` to quit, `r` to refresh, `o` to open PR in browser, `enter` to view details).

## Future Considerations

- Adding a detail pane to view PR descriptions and comments.
- Adding action buttons to approve or merge PRs directly from the TUI.
