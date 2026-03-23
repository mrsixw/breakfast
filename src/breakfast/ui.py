import click

BREAKFAST_ITEMS = [
    "☕️",
    "🥐",
    "🥞",
    "🍳",
    "🥓",
    "🥯",
    "🍩",
    "🍪",
    "🥛",
    "🍵",
    "🍎",
    "🍌",
    "🍉",
    "🍇",
    "🍓",
    "🍒",
    "🍑",
    "🍍",
    "🥖",
    "🥨",
    "🥯",
    "🥞",
    "🧇",
    "🧀",
    "🍗",
    "🥩",
    "🥓",
    "🍔",
    "🍟",
    "🍕",
    "🌭",
    "🥪",
    "🌮",
    "🌯",
    "🥙",
]


def click_colour_grade_number(num):
    colour = "red"
    if num < 10:
        colour = "green"
    elif num < 20:
        colour = "yellow"
    elif num < 50:
        colour = 208  # orange (256-colour)
    return click.style(str(num), fg=colour, bold=True)


def format_check_status(status, style="emoji"):
    """Return a colour-coded check status label for table output.

    Args:
        status: Canonical CI status value such as ``pass`` or ``pending``.
        style: Rendering style, either ``emoji`` or ``ascii``.

    Returns:
        A styled label in the requested style.
    """
    styles = {
        "emoji": {
            "pass": ("green", "✅ pass"),
            "fail": ("red", "❌ fail"),
            "pending": ("yellow", "⚠️ pending"),
            "none": ("white", "➖ none"),
        },
        "ascii": {
            "pass": ("green", "pass"),
            "fail": ("red", "fail"),
            "pending": ("yellow", "pending"),
            "none": ("white", "none"),
        },
    }
    style_map = styles.get(style, styles["emoji"])
    colour, text = style_map.get(status, ("white", status))
    return click.style(text, fg=colour, bold=True)


def format_approval_status(status, style="emoji"):
    """Return a colour-coded approval status label for table output.

    Args:
        status: Canonical approval status — ``approved``, ``changes``, or ``pending``.
        style: Rendering style, either ``emoji`` or ``ascii``.

    Returns:
        A styled label in the requested style.
    """
    styles = {
        "emoji": {
            "approved": ("green", "✅ approved"),
            "changes": ("red", "❌ changes"),
            "pending": ("yellow", "⏳ pending"),
        },
        "ascii": {
            "approved": ("green", "approved"),
            "changes": ("red", "changes"),
            "pending": ("yellow", "pending"),
        },
    }
    style_map = styles.get(style, styles["emoji"])
    colour, text = style_map.get(status, ("white", status))
    return click.style(text, fg=colour, bold=True)


def format_mergeable_status(is_mergeable, mergeable_state, style="emoji"):
    """Return a mergeability label for table output.

    Args:
        is_mergeable: Whether GitHub reports the PR as mergeable.
        mergeable_state: GitHub's mergeable-state detail such as ``clean``.
        style: Rendering style, either ``emoji`` or ``ascii``.

    Returns:
        A label such as ``✅ (clean)`` or ``yes (clean)``.
    """
    if style == "ascii":
        prefix = "yes" if is_mergeable else "no"
    else:
        prefix = "✅" if is_mergeable else "❌"
    if mergeable_state:
        return f"{prefix} ({mergeable_state})"
    return prefix


def generate_terminal_url_anchor(url, url_text="Link"):
    return f"\033]8;;{url}\033\\{url_text}\033]8;;\033\\"
