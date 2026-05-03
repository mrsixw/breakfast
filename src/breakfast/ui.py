import datetime
import unicodedata

import click

SEASONAL_PALETTES = {
    "green": "\033[32m",
    "purple": "\033[38;5;141m",
    "yellow": "\033[38;5;226m",
    "orange": "\033[38;5;208m",
    "red": "\033[31m",
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


def _seasonal_colour() -> str | None:
    """Return the ANSI colour code for the current calendar month, or None.

    Returns None for months with no seasonal theme, so callers can skip
    colouring and fall back to the default terminal colour.
    """
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
    return None


def apply_seasonal_colour(text: str, pr_number: int) -> str:
    """Wrap *text* in a seasonal ANSI colour based on the current month.

    December 🎄 alternates rows between red and green (candy-cane style).
    Non-special months return text unstyled so it renders in the default
    terminal colour. Callers are expected to guard with the ``no-colour``
    setting.
    """
    today = datetime.date.today()
    if today.month == 12:
        colour = (
            SEASONAL_PALETTES["red"]
            if pr_number % 2 == 0
            else SEASONAL_PALETTES["green"]
        )
        return f"{colour}{text}\033[0m"
    colour = _seasonal_colour()
    if colour is None:
        return text
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


def render_colour_diagnostics() -> str:
    """Render a swatch page showing every colour used in the breakfast UI.

    Returns a multi-line string ready to pass to ``click.echo()``.
    Useful for tuning palette choices in a specific terminal.
    """

    def _ansi256(code: int, text: str) -> str:
        return f"\033[38;5;{code}m{text}\033[0m"

    def _named(name: str, text: str) -> str:
        return click.style(text, fg=name, bold=True)

    def _named_dim(name, text: str) -> str:
        return click.style(text, fg=name, bold=False)

    def _vpad(text: str, width: int) -> str:
        """Pad text to visual width, accounting for double-wide emoji."""
        vlen = 0
        for ch in text:
            cat = unicodedata.category(ch)
            if cat in ("Mn", "Cf"):
                pass  # variation selectors and zero-width marks
            elif unicodedata.east_asian_width(ch) in ("W", "F") or ord(ch) > 0x1F000:
                vlen += 2
            else:
                vlen += 1
        return text + " " * max(0, width - vlen)

    BLOCK = "████"

    lines = [click.style("🎨 breakfast colour diagnostics", fg="cyan", bold=True), ""]

    # ------------------------------------------------------------------
    # Seasonal colours (author / PR title)
    # ------------------------------------------------------------------
    lines.append(click.style("Seasonal colours  (author & PR title)", bold=True))
    palette_rows = [
        ("January 🗓️", "purple"),
        ("Easter 🐣", "yellow"),
        ("October 🎃", "orange"),
        ("December 🎄 (red)", "red"),
        ("December 🎄 (green)", "green"),
    ]

    def _seasonal_swatch(code: str) -> str:
        """Render a coloured block swatch for a raw ANSI escape code."""
        parts = code.split(";")
        if len(parts) >= 3:
            n = parts[2].rstrip("m")
            return f"{_ansi256(int(n), BLOCK)} {n}"
        n = code[2:-1]
        return f"{code}{BLOCK}\033[0m {n}"

    for label, key in palette_rows:
        swatch = _seasonal_swatch(SEASONAL_PALETTES[key])
        lines.append(f"  {_vpad(label, 22)}  {swatch}")
    lines.append("")

    # ------------------------------------------------------------------
    # PR state
    # ------------------------------------------------------------------
    lines.append(click.style("PR state", bold=True))
    lines.append(
        f"  {_named('green', BLOCK)} open        "
        f"  {_named_dim(246, BLOCK)} draft (246)  "
        f"  {_named('red', BLOCK)} closed"
    )
    lines.append("")

    # ------------------------------------------------------------------
    # Check status
    # ------------------------------------------------------------------
    lines.append(click.style("Check status", bold=True))
    lines.append(
        f"  {_named('green', BLOCK)} pass    "
        f"  {_named('red', BLOCK)} fail    "
        f"  {_named('yellow', BLOCK)} pending  "
        f"  {_named('white', BLOCK)} none"
    )
    lines.append("")

    # ------------------------------------------------------------------
    # Approval status
    # ------------------------------------------------------------------
    lines.append(click.style("Approval status", bold=True))
    lines.append(
        f"  {_named('green', BLOCK)} approved  "
        f"  {_named('red', BLOCK)} changes   "
        f"  {_named('yellow', BLOCK)} pending"
    )
    lines.append("")

    # ------------------------------------------------------------------
    # Mergeable status
    # ------------------------------------------------------------------
    lines.append(click.style("Mergeable status", bold=True))
    lines.append(f"  {_named('green', BLOCK)} yes  " f"  {_named('red', BLOCK)} no")
    lines.append("")

    # ------------------------------------------------------------------
    # Number gradient (files, commits, comments, age)
    # ------------------------------------------------------------------
    lines.append(
        click.style("Number gradient  (files / commits / comments / age)", bold=True)
    )
    lines.append(
        f"  {_named('green', BLOCK)} <10      "
        f"  {_named('yellow', BLOCK)} 10–19    "
        f"  {_ansi256(208, BLOCK)} 20–49 (208)  "
        f"  {_named('red', BLOCK)} 50+"
    )
    lines.append("")

    # ------------------------------------------------------------------
    # Summary bar gradient (--summarise-user-prs / --summarise-repo-prs)
    # ------------------------------------------------------------------
    lines.append(click.style("Summary bar gradient  (--summarise-*-prs)", bold=True))
    lines.append(
        f"  {_named('green', BLOCK)} ≤25%     "
        f"  {_named('yellow', BLOCK)} ≤50%     "
        f"  {_ansi256(208, BLOCK)} ≤75% (208)   "
        f"  {_named('red', BLOCK)} >75%"
    )
    lines.append(f"  {_ansi256(245, BLOCK)} draft blocks (245)")
    lines.append("")

    # ------------------------------------------------------------------
    # UI / system colours
    # ------------------------------------------------------------------
    lines.append(click.style("UI / system colours", bold=True))
    lines.append(
        f"  {_named('cyan', BLOCK)} update notifications  "
        f"  {_named('yellow', BLOCK)} warnings  "
        f"  {_named('red', BLOCK)} errors  "
        f"  {_named('green', BLOCK)} success"
    )
    lines.append("")

    # ------------------------------------------------------------------
    # Additions / deletions (+/- column)
    # ------------------------------------------------------------------
    lines.append(click.style("+/- column", bold=True))
    lines.append(
        f"  {_named('green', BLOCK)} additions  " f"  {_named('red', BLOCK)} deletions"
    )
    lines.append("")

    # ------------------------------------------------------------------
    # 256-colour reference — all hues, full shade range
    # ------------------------------------------------------------------
    lines.append(
        click.style("256-colour reference  (all hues, dark → bright)", bold=True)
    )
    hue_rows = [
        ("Greens", [22, 28, 34, 40, 46, 82, 118, 154, 190]),
        ("Yellows", [100, 106, 136, 142, 178, 184, 190, 220, 226]),
        ("Oranges", [94, 130, 136, 166, 172, 202, 208, 214]),
        ("Reds", [52, 88, 124, 160, 196, 197, 203, 210]),
        ("Purples", [54, 55, 56, 90, 91, 92, 93, 129, 135, 141, 147]),
        ("Blues", [17, 18, 19, 20, 21, 57, 63, 69, 75, 81]),
        ("Cyans", [23, 30, 37, 44, 51, 86, 87, 122, 123]),
        ("Magentas", [53, 89, 125, 126, 161, 162, 197, 198, 199, 207]),
        ("Greys", [232, 235, 238, 240, 242, 244, 246, 248, 250, 252, 254]),
    ]
    for label, codes in hue_rows:
        swatches = "  ".join(f"{_ansi256(n, BLOCK)} {n:<3}" for n in codes)
        lines.append(f"  {label:<10}  {swatches}")

    return "\n".join(lines)


def render_pr_summary(groups, title, label_header, colour, seasonal_colours):
    """Render a compact PR summary table as a string.

    Args:
        groups: List of
            ``(name, url, count, draft_count, oldest_age_days, total_comments)``
            tuples, sorted by count descending.
        title: Heading line, e.g. ``"👤 PR Summary by Author"``.
        label_header: Column label printed above the name column,
            e.g. ``"Author"`` or ``"Repo"``.
        colour: Whether ANSI colour output is enabled.
        seasonal_colours: Whether seasonal colouring is applied to labels.

    Returns:
        A multi-line string ready to pass to ``click.echo()``.
    """
    if not groups:
        return f"{title}\n\n  (no PRs to summarise)"

    max_count = max(count for _, _, count, _, _, _ in groups)
    max_name_len = max(len(name) for name, _, _, _, _, _ in groups)
    bar_max_width = 20

    # Pre-compute variable-width column strings so we can align all rows.
    def _count_str(count, draft_count):
        s = f"{count} PR{'s' if count != 1 else ' '}"
        if draft_count:
            s += f" ({draft_count} draft)"
        return s

    def _age_str(oldest_age):
        return f"oldest: {oldest_age}d"

    col_count_strs = [_count_str(c, d) for _, _, c, d, _, _ in groups]
    col_age_strs = [_age_str(a) for _, _, _, _, a, _ in groups]
    max_count_col = max(len(s) for s in col_count_strs)
    max_age_col = max(len(s) for s in col_age_strs)

    lines = [title, ""]

    for idx, (name, url, count, draft_count, oldest_age, total_comments) in enumerate(
        groups
    ):
        # Bar width proportional to count; always at least 1 block.
        filled = max(1, int(count / max_count * bar_max_width)) if max_count else 1

        # Split filled blocks: solid █ for open PRs, medium-shade ▒ for drafts.
        if draft_count > 0 and count > 0:
            draft_blocks = max(1, round(draft_count / count * filled))
            draft_blocks = min(draft_blocks, filled)
        else:
            draft_blocks = 0
        solid_blocks = filled - draft_blocks
        bar_padding = " " * (bar_max_width - filled)

        # Bar colour: green (few) → yellow → orange → red (many),
        # proportional to the group with the highest count.
        ratio = count / max_count if max_count else 0
        if ratio <= 0.25:
            bar_fg = "green"
        elif ratio <= 0.5:
            bar_fg = "yellow"
        elif ratio <= 0.75:
            bar_fg = 208  # orange (256-colour)
        else:
            bar_fg = "red"

        if colour:
            bar_display = (
                click.style("█" * solid_blocks, fg=bar_fg, bold=True)
                + click.style("▒" * draft_blocks, fg=245, bold=False)
                + bar_padding
            )
        else:
            bar_display = "█" * solid_blocks + "▒" * draft_blocks + bar_padding

        # Seasonal colour on label names, cycling by row index.
        if colour and seasonal_colours:
            styled_name = apply_seasonal_colour(name, idx)
        else:
            styled_name = name

        # Wrap name in an OSC 8 hyperlink when colour output is on.
        if colour:
            label = generate_terminal_url_anchor(url, styled_name)
        else:
            label = name

        name_padding = " " * (max_name_len - len(name))
        count_col = _count_str(count, draft_count).ljust(max_count_col)
        age_col = _age_str(oldest_age).ljust(max_age_col)
        comments_col = f"comments: {total_comments}"

        lines.append(
            f"  {label}{name_padding}  {bar_display}  "
            f"{count_col}  {age_col}  {comments_col}"
        )

    return "\n".join(lines)
