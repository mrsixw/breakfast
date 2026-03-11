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
        colour = (255, 165, 0)  # orange
    return click.style(str(num), fg=colour, bold=True)


def format_check_status(status):
    styles = {
        "pass": ("green", "✅ pass"),
        "fail": ("red", "❌ fail"),
        "pending": ("yellow", "⚠️ pending"),
        "none": ("white", "➖ none"),
    }
    colour, text = styles.get(status, ("white", status))
    return click.style(text, fg=colour, bold=True)


def generate_terminal_url_anchor(url, url_text="Link"):
    return f"\033]8;;{url}\033\\{url_text}\033]8;;\033\\"
