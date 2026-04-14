import datetime

import click

SEASONAL_PALETTES = {
    "green": ["\033[38;5;22m", "\033[38;5;34m", "\033[38;5;40m", "\033[38;5;46m"],
    "purple": ["\033[38;5;54m", "\033[38;5;90m", "\033[38;5;129m", "\033[38;5;165m"],
    "yellow": ["\033[38;5;136m", "\033[38;5;178m", "\033[38;5;220m", "\033[38;5;226m"],
    "orange": ["\033[38;5;130m", "\033[38;5;166m", "\033[38;5;202m", "\033[38;5;208m"],
    "red": ["\033[38;5;88m", "\033[38;5;124m", "\033[38;5;160m", "\033[38;5;196m"],
}

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


def _easter_month(year: int) -> int:
    """Return 3 (March) or 4 (April): the month Easter falls in for *year*.

    Uses the Anonymous Gregorian algorithm (Meeus/Jones/Butcher).
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    return (h + ll - 7 * m + 114) // 31


def _seasonal_palette() -> list[str]:
    """Return the 4-shade ANSI palette for the current calendar month."""
    today = datetime.date.today()
    month = today.month
    if month == 1:
        return SEASONAL_PALETTES["purple"]
    if month == _easter_month(today.year):
        return SEASONAL_PALETTES["yellow"]
    if month == 10:
        return SEASONAL_PALETTES["orange"]
    if month == 12:
        return SEASONAL_PALETTES["red"]
    return SEASONAL_PALETTES["green"]


def apply_seasonal_colour(text: str, pr_number: int) -> str:
    """Wrap *text* in a seasonal ANSI 256-colour based on the current month.

    December 🎄 alternates rows between red and green (candy-cane style).
    All other months use a 4-shade gradient keyed by ``pr_number % 4``.
    Returns the original text unchanged if called when no colour is needed —
    callers are expected to guard with the ``no-colour`` setting.
    """
    today = datetime.date.today()
    if today.month == 12:
        colour = (
            SEASONAL_PALETTES["red"][2]
            if pr_number % 2 == 0
            else SEASONAL_PALETTES["green"][2]
        )
    else:
        palette = _seasonal_palette()
        colour = palette[pr_number % 4]
    return f"{colour}{text}\033[0m"


def format_pr_state(state, is_draft=False):
    """Return a colour-coded state string for display in the PR table.

    open   → green  'open'
    draft  → grey   'draft'
    closed → red    'closed'
    """
    state_lower = state.lower()
    if state_lower == "open":
        if is_draft:
            return click.style("draft", fg=246, bold=False)
        return click.style("open", fg="green", bold=True)
    if state_lower == "closed":
        return click.style("closed", fg="red", bold=True)
    return state


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


def format_approval_status(
    status,
    style="emoji",
    current_reviews=None,
    required_reviews=None,
):
    """Return a colour-coded approval status label for table output.

    Args:
        status: Canonical approval status — ``approved``, ``changes``, or ``pending``.
        style: Rendering style, either ``emoji`` or ``ascii``.
        current_reviews: Number of effective approvals currently present.
        required_reviews: Number of approvals required by branch protection.

    Returns:
        A styled label in the requested style.
    """
    if (
        required_reviews is not None
        and required_reviews > 1
        and current_reviews is not None
        and status != "changes"
    ):
        colour = "green" if current_reviews > 0 else "yellow"
        if style == "ascii":
            text = f"{current_reviews}/{required_reviews} approvals"
        else:
            prefix = "✅" if current_reviews > 0 else "⏳"
            text = f"{prefix} {current_reviews}/{required_reviews} approvals"
        return click.style(text, fg=colour, bold=True)

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
    """Return a colour-coded mergeability label for table output.

    Args:
        is_mergeable: Whether GitHub reports the PR as mergeable.
        mergeable_state: GitHub's mergeable-state detail such as ``clean``.
        style: Rendering style, either ``emoji`` or ``ascii``.

    Returns:
        A styled label such as ``✅ (clean)`` or ``yes (clean)``.
    """
    colour = "green" if is_mergeable else "red"
    if style == "ascii":
        prefix = "yes" if is_mergeable else "no"
    else:
        prefix = "✅" if is_mergeable else "❌"
    if mergeable_state:
        text = f"{prefix} ({mergeable_state})"
    else:
        text = prefix
    return click.style(text, fg=colour, bold=True)


def generate_terminal_url_anchor(url, url_text="Link"):
    return f"\033]8;;{url}\033\\{url_text}\033]8;;\033\\"
