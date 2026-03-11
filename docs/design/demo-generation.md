# Demo GIF Generation

This document explains how to regenerate the `docs/demo.gif` file used in the README.

## Requirements

1.  **VHS**: You must have [VHS](https://github.com/charmbracelet/vhs) installed.
    ```bash
    brew install vhs
    ```
2.  **GITHUB_TOKEN**: A valid token must be in your environment if you want the demo to show real data.
3.  **Python 3.11+**: The project must be buildable via `make build`.

## Regeneration Process

The easiest way to regenerate the GIF is using the included `Makefile` target:

```bash
make demo
```

### Manual Method

If you want to run it manually:

1.  **Build the binary**:
    ```bash
    make build
    ```
2.  **Run VHS**:
    Set the `SHIV_INTERPRETER` to the absolute path of your project's virtual environment python to ensure compatibility:
    ```bash
    export SHIV_INTERPRETER=$(pwd)/.venv/bin/python3
    vhs < utils/vhs/demo.tape
    ```

## Customizing the Demo

The script controlling the recording is located at `utils/vhs/demo.tape`. You can edit this file to:
- Change the terminal theme (`Set Theme`).
- Adjust the typing speed and wait times (`Sleep`).
- Change the repositories being queried.

**Note**: If the GitHub API is slow, you may need to increase the `Sleep` values in the `.tape` file to ensure the table has enough time to render before the recording ends.
