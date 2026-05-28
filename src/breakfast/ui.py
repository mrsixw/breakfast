import datetime
import math
import unicodedata
from datetime import date as _real_date
from datetime import timedelta as _real_timedelta

import click

SEASONAL_PALETTES = {
    "green": "\033[32m",
    "purple": "\033[38;5;141m",
    "yellow": "\033[38;5;226m",
    "orange": "\033[38;5;208m",
    "red": "\033[31m",
    "pink": "\033[38;5;218m",
    "lny": "\033[38;5;214m",
    "blue": "\033[38;5;75m",
    "spring_green": "\033[38;5;120m",
}

# Pride Month 🏳️‍🌈 rainbow: one colour per row, cycling by PR number.
PRIDE_RAINBOW = [
    "\033[31m",  # red
    "\033[38;5;208m",  # orange
    "\033[38;5;226m",  # yellow
    "\033[32m",  # green
    "\033[38;5;63m",  # blue
    "\033[38;5;141m",  # purple
]


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


def _new_moon_jde(k: float) -> float:
    """Julian Ephemeris Day of new moon k (Meeus, Astronomical Algorithms, ch. 49).

    k=0 is the new moon of 6 January 2000.
    """
    T = k / 1236.85
    jde = (
        2451550.09766
        + 29.530588861 * k
        + 0.00015437 * T**2
        - 0.000000150 * T**3
        + 0.00000000073 * T**4
    )
    M = math.radians(2.5534 + 29.10535670 * k - 0.0000014 * T**2)
    Mp = math.radians(
        201.5643 + 385.81693528 * k + 0.0107582 * T**2 + 0.00001238 * T**3
    )
    F = math.radians(160.7108 + 390.67050284 * k - 0.0016118 * T**2 - 0.00000227 * T**3)
    Om = math.radians(124.7746 - 1.56375588 * k + 0.0020672 * T**2)
    E = 1 - 0.002516 * T - 0.0000074 * T**2
    corr = (
        -0.40720 * math.sin(Mp)
        + 0.17241 * E * math.sin(M)
        + 0.01608 * math.sin(2 * Mp)
        + 0.01039 * math.sin(2 * F)
        + 0.00739 * E * math.sin(Mp - M)
        - 0.00514 * E * math.sin(Mp + M)
        + 0.00208 * E**2 * math.sin(2 * M)
        - 0.00111 * math.sin(Mp - 2 * F)
        - 0.00057 * math.sin(Mp + 2 * F)
        + 0.00056 * E * math.sin(2 * Mp + M)
        - 0.00042 * math.sin(3 * Mp)
        + 0.00042 * E * math.sin(M + 2 * F)
        + 0.00038 * E * math.sin(M - 2 * F)
        - 0.00024 * E * math.sin(2 * Mp - M)
        - 0.00017 * math.sin(Om)
    )
    return jde + corr


def _jde_to_date_cst(jde: float) -> tuple[int, int, int]:
    """Convert a Julian Ephemeris Day to Gregorian (year, month, day) in CST (UTC+8)."""
    jd = jde + 8.0 / 24.0  # shift to Chinese Standard Time
    Z = int(jd + 0.5)
    alpha = int((Z - 1867216.25) / 36524.25)
    A = Z + 1 + alpha - alpha // 4
    B = A + 1524
    C = int((B - 122.1) / 365.25)
    D = int(365.25 * C)
    E_val = int((B - D) / 30.6001)
    day = B - D - int(30.6001 * E_val)
    month = E_val - 1 if E_val < 14 else E_val - 13
    year = C - 4716 if month > 2 else C - 4715
    return year, month, day


def _lny_date(year: int) -> tuple[int, int]:
    """Return (month, day) of Lunar New Year for *year* in Chinese Standard Time.

    Chinese New Year is the new moon between Jan 21 and Feb 20.
    Uses the Meeus new-moon algorithm (Astronomical Algorithms, ch. 49).
    """
    k_approx = round((year - 2000) * 12.3685)
    for dk in range(-2, 4):
        jde = _new_moon_jde(k_approx + dk)
        y, m, d = _jde_to_date_cst(jde)
        if y == year and ((m == 1 and d >= 21) or (m == 2 and d <= 20)):
            return m, d
    raise ValueError(f"Could not calculate Lunar New Year for {year}")


# ---------------------------------------------------------------------------
# Pluggable seasonal calendar system
# ---------------------------------------------------------------------------

# Pre-computed holiday dates (year → (month, day)) for 2024–2045.
# Dates are approximate; Islamic/Hindu dates vary by location and moon-sighting.

_DIWALI: dict[int, tuple[int, int]] = {
    2024: (11, 1),
    2025: (10, 20),
    2026: (11, 8),
    2027: (10, 29),
    2028: (10, 17),
    2029: (11, 5),
    2030: (10, 26),
    2031: (11, 14),
    2032: (11, 2),
    2033: (10, 22),
    2034: (11, 11),
    2035: (11, 1),
    2036: (10, 19),
    2037: (11, 7),
    2038: (10, 28),
    2039: (10, 18),
    2040: (11, 4),
    2041: (10, 24),
    2042: (11, 13),
    2043: (11, 3),
    2044: (10, 21),
    2045: (11, 9),
}

_EID_AL_ADHA: dict[int, tuple[int, int]] = {
    2024: (6, 16),
    2025: (6, 6),
    2026: (5, 26),
    2027: (5, 16),
    2028: (5, 4),
    2029: (4, 24),
    2030: (4, 13),
    2031: (4, 2),
    2032: (3, 22),
    2033: (3, 11),
    2034: (3, 1),
    2035: (2, 18),
    2036: (2, 7),
    2037: (1, 26),
    2038: (1, 16),
    2039: (12, 26),
    2040: (12, 14),
    2041: (12, 4),
    2042: (11, 23),
    2043: (11, 13),
    2044: (11, 1),
    2045: (10, 22),
}

_EID_AL_FITR: dict[int, tuple[int, int]] = {
    2024: (4, 10),
    2025: (3, 30),
    2026: (3, 20),
    2027: (3, 9),
    2028: (2, 26),
    2029: (2, 15),
    2030: (2, 4),
    2031: (1, 24),
    2032: (1, 13),
    2033: (1, 2),
    2034: (12, 11),
    2035: (11, 30),
    2036: (11, 19),
    2037: (11, 8),
    2038: (10, 28),
    2039: (10, 17),
    2040: (10, 6),
    2041: (9, 25),
    2042: (9, 14),
    2043: (9, 4),
    2044: (8, 23),
    2045: (8, 12),
}

_HANUKKAH_START: dict[int, tuple[int, int]] = {
    2024: (12, 25),
    2025: (12, 14),
    2026: (12, 4),
    2027: (12, 24),
    2028: (12, 12),
    2029: (12, 1),
    2030: (12, 20),
    2031: (12, 9),
    2032: (11, 27),
    2033: (12, 16),
    2034: (12, 5),
    2035: (12, 25),
    2036: (12, 13),
    2037: (12, 2),
    2038: (12, 22),
    2039: (12, 11),
    2040: (11, 29),
    2041: (12, 18),
    2042: (12, 8),
    2043: (12, 27),
    2044: (12, 15),
    2045: (12, 5),
}

_HOLI: dict[int, tuple[int, int]] = {
    2024: (3, 25),
    2025: (3, 14),
    2026: (3, 3),
    2027: (3, 22),
    2028: (3, 11),
    2029: (3, 1),
    2030: (3, 20),
    2031: (3, 10),
    2032: (2, 27),
    2033: (3, 17),
    2034: (3, 7),
    2035: (3, 26),
    2036: (3, 14),
    2037: (3, 4),
    2038: (3, 23),
    2039: (3, 13),
    2040: (3, 1),
    2041: (3, 19),
    2042: (3, 8),
    2043: (3, 28),
    2044: (3, 16),
    2045: (3, 5),
}

_MID_AUTUMN: dict[int, tuple[int, int]] = {
    2024: (9, 17),
    2025: (10, 6),
    2026: (9, 25),
    2027: (9, 15),
    2028: (10, 3),
    2029: (9, 22),
    2030: (9, 12),
    2031: (10, 1),
    2032: (9, 19),
    2033: (9, 8),
    2034: (9, 27),
    2035: (9, 16),
    2036: (10, 4),
    2037: (9, 24),
    2038: (9, 13),
    2039: (10, 2),
    2040: (9, 20),
    2041: (9, 9),
    2042: (9, 28),
    2043: (9, 17),
    2044: (10, 5),
    2045: (9, 24),
}

_PASSOVER_START: dict[int, tuple[int, int]] = {
    2024: (4, 22),
    2025: (4, 12),
    2026: (4, 1),
    2027: (4, 21),
    2028: (4, 10),
    2029: (3, 29),
    2030: (4, 17),
    2031: (4, 7),
    2032: (3, 27),
    2033: (4, 14),
    2034: (4, 3),
    2035: (4, 23),
    2036: (4, 11),
    2037: (4, 1),
    2038: (4, 20),
    2039: (4, 9),
    2040: (3, 29),
    2041: (4, 16),
    2042: (4, 6),
    2043: (4, 25),
    2044: (4, 13),
    2045: (4, 3),
}

_ROSH_HASHANAH: dict[int, tuple[int, int]] = {
    2024: (10, 2),
    2025: (9, 22),
    2026: (9, 11),
    2027: (10, 1),
    2028: (9, 20),
    2029: (9, 9),
    2030: (9, 27),
    2031: (9, 18),
    2032: (9, 5),
    2033: (9, 24),
    2034: (9, 14),
    2035: (10, 3),
    2036: (9, 21),
    2037: (9, 10),
    2038: (9, 29),
    2039: (9, 19),
    2040: (9, 7),
    2041: (9, 25),
    2042: (9, 15),
    2043: (10, 4),
    2044: (9, 22),
    2045: (9, 12),
}

_SUKKOT_START: dict[int, tuple[int, int]] = {
    2024: (10, 16),
    2025: (10, 6),
    2026: (9, 25),
    2027: (10, 15),
    2028: (10, 4),
    2029: (9, 23),
    2030: (10, 12),
    2031: (10, 1),
    2032: (9, 19),
    2033: (10, 8),
    2034: (9, 28),
    2035: (10, 17),
    2036: (10, 4),
    2037: (9, 24),
    2038: (10, 13),
    2039: (10, 3),
    2040: (9, 21),
    2041: (10, 10),
    2042: (9, 30),
    2043: (10, 18),
    2044: (10, 5),
    2045: (9, 25),
}

# Holi rainbow: a burst of festival colours for the Festival of Colours 🌈
HOLI_RAINBOW = [
    "\033[38;5;218m",  # pink
    "\033[38;5;226m",  # yellow
    "\033[32m",  # green
    "\033[38;5;208m",  # orange
    "\033[38;5;141m",  # purple
    "\033[38;5;75m",  # blue
]


def _in_holiday_window(
    today: datetime.date,
    table: dict[int, tuple[int, int]],
    days: int = 1,
) -> bool:
    """Return True if *today* falls within *days* days of the holiday in *table*."""
    entry = table.get(today.year)
    if entry is None:
        return False
    try:
        start = _real_date(today.year, entry[0], entry[1])
        return start <= today < start + _real_timedelta(days=days)
    except ValueError:
        return False


def _east_asian_calendar(today: datetime.date) -> "str | list[str] | None":
    """Return seasonal colour for East/Southeast Asian holiday calendar."""
    # Songkran (Thai Water Festival / New Year): April 13-15 (fixed)
    if today.month == 4 and 13 <= today.day <= 15:
        return SEASONAL_PALETTES["blue"]

    # Hanami (Cherry Blossom Festival): April 1-7 (fixed)
    if today.month == 4 and 1 <= today.day <= 7:
        return SEASONAL_PALETTES["pink"]

    # Lunar New Year: 3-day window starting at LNY date
    try:
        lny_m, lny_d = _lny_date(today.year)
        lny_start = _real_date(today.year, lny_m, lny_d)
        if lny_start <= today < lny_start + _real_timedelta(days=3):
            return SEASONAL_PALETTES["lny"]
    except ValueError:
        pass

    # Mid-Autumn / Moon Festival (Chuseok / Tsukimi): 2-day window
    if _in_holiday_window(today, _MID_AUTUMN, days=2):
        return SEASONAL_PALETTES["yellow"]

    return None


def _hindu_calendar(today: datetime.date) -> "str | list[str] | None":
    """Return seasonal colour for Hindu holiday calendar."""
    if _in_holiday_window(today, _DIWALI, days=5):
        return SEASONAL_PALETTES["lny"]
    if _in_holiday_window(today, _HOLI, days=2):
        return HOLI_RAINBOW
    return None


def _islamic_calendar(today: datetime.date) -> "str | list[str] | None":
    """Return seasonal colour for Islamic holiday calendar."""
    if _in_holiday_window(today, _EID_AL_FITR, days=3):
        return SEASONAL_PALETTES["green"]
    if _in_holiday_window(today, _EID_AL_ADHA, days=3):
        return SEASONAL_PALETTES["green"]
    return None


def _jewish_calendar(today: datetime.date) -> "str | list[str] | None":
    """Return seasonal colour for Jewish holiday calendar."""
    if _in_holiday_window(today, _HANUKKAH_START, days=8):
        return SEASONAL_PALETTES["blue"]
    if _in_holiday_window(today, _ROSH_HASHANAH, days=2):
        return SEASONAL_PALETTES["lny"]
    if _in_holiday_window(today, _PASSOVER_START, days=7):
        return SEASONAL_PALETTES["spring_green"]
    if _in_holiday_window(today, _SUKKOT_START, days=7):
        return SEASONAL_PALETTES["orange"]
    return None


def _sikh_calendar(today: datetime.date) -> "str | list[str] | None":
    """Return seasonal colour for Sikh holiday calendar."""
    if today.month == 4 and today.day == 13:  # Vaisakhi (fixed)
        return SEASONAL_PALETTES["spring_green"]
    if _in_holiday_window(today, _DIWALI, days=5):  # Bandi Chhor Divas
        return SEASONAL_PALETTES["lny"]
    return None


def _western_calendar(today: datetime.date) -> "str | list[str] | None":
    """Return seasonal colour(s) for the western/Gregorian calendar.

    Returns a list for PR-number-cycling effects (December, Pride Month),
    a single colour string for fixed colours, or None for unthemed dates.
    """
    month = today.month
    day = today.day

    if month == 12:
        return [SEASONAL_PALETTES["red"], SEASONAL_PALETTES["green"]]

    if month == 6:
        return PRIDE_RAINBOW

    if month == 2 and day == 14:
        return SEASONAL_PALETTES["pink"]

    # LNY only when it falls in February; January purple is never overridden.
    lny = _lny_date(today.year)
    if lny == (month, day) and month == 2:
        return SEASONAL_PALETTES["lny"]

    if month == _easter_month(today.year):
        return SEASONAL_PALETTES["yellow"]

    if month == 10:
        return SEASONAL_PALETTES["orange"]

    return None


CALENDARS: dict[str, object] = {
    "east-asian": _east_asian_calendar,
    "hindu": _hindu_calendar,
    "islamic": _islamic_calendar,
    "jewish": _jewish_calendar,
    "sikh": _sikh_calendar,
    "western": _western_calendar,
}


def _seasonal_colour() -> "str | None":
    """Return the ANSI colour for the current month (western calendar, legacy API).

    Returns None for months with no theme. December and June return the first
    colour from their cycling lists rather than the full list.
    """
    today = datetime.date.today()
    if today.month == 1:
        return SEASONAL_PALETTES["purple"]
    result = _western_calendar(today)
    if isinstance(result, list):
        return result[0]
    return result


def apply_seasonal_colour(text: str, pr_number: int, calendar: str = "western") -> str:
    """Wrap *text* in a seasonal ANSI colour based on the current date.

    The *calendar* argument selects which cultural calendar's holidays drive
    the seasonal colours. Valid values: ``"western"`` (default), ``"jewish"``,
    ``"islamic"``, ``"hindu"``, ``"sikh"``, or ``"off"`` to disable entirely.

    Lists (December candy-cane, June Pride, Holi rainbow) cycle by PR number.
    """
    if calendar == "off":
        return text
    calendar_fn = CALENDARS.get(calendar)
    if calendar_fn is None:
        return text
    today = datetime.date.today()
    if today.month == 1:
        colour = SEASONAL_PALETTES["purple"]
        return f"{colour}{text}\033[0m"
    result = calendar_fn(today)
    if result is None:
        return text
    if isinstance(result, list):
        colour = result[pr_number % len(result)]
    else:
        colour = result
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


def format_mergeable_status(
    is_mergeable, mergeable_state, style="emoji", pr_state=None, merged=False
):
    """Return a colour-coded mergeability label for table output.

    Args:
        is_mergeable: Whether GitHub reports the PR as mergeable, or None if
            GitHub is still computing it (common on freshly-updated PRs).
        mergeable_state: GitHub's mergeable-state detail such as ``clean``.
        style: Rendering style, either ``emoji`` or ``ascii``.
        pr_state: GitHub PR state string (``open`` or ``closed``).
        merged: Whether the PR was merged.

    Returns:
        A styled label such as ``✅ (clean)``, ``❌ (dirty)``, or ``⏳ computing``.
    """
    if pr_state == "closed":
        if merged:
            label = "merged" if style == "ascii" else "🏁 merged"
            return click.style(label, fg="green", bold=False)
        label = "closed" if style == "ascii" else "🚫 closed"
        return click.style(label, fg=246, bold=False)
    if is_mergeable is None:
        label = "computing" if style == "ascii" else "⏳ computing"
        return click.style(label, fg=246, bold=False)
    if not is_mergeable:
        prefix = "no" if style == "ascii" else "❌"
        text = f"{prefix} ({mergeable_state})" if mergeable_state else prefix
        return click.style(text, fg="red", bold=True)
    # is_mergeable is True — but only "clean" means genuinely ready to merge.
    # "behind", "unstable", "blocked" etc. are amber warnings.
    _AMBER_STATES = {"behind", "unstable", "blocked", "unknown"}
    if mergeable_state in _AMBER_STATES:
        prefix = "~" if style == "ascii" else "⚠️"
        text = f"{prefix} ({mergeable_state})" if mergeable_state else prefix
        return click.style(text, fg="yellow", bold=True)
    prefix = "yes" if style == "ascii" else "✅"
    text = f"{prefix} ({mergeable_state})" if mergeable_state else prefix
    return click.style(text, fg="green", bold=True)


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
        ("Valentine's Day 💕 (14 Feb)", "pink"),
        ("Lunar New Year 🧧 (Feb)", "lny"),
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
        lines.append(f"  {_vpad(label, 28)}  {swatch}")

    # Pride Month rainbow — one swatch per colour in the cycle.
    pride_swatches = "  ".join(f"{code}{BLOCK}\033[0m" for code in PRIDE_RAINBOW)
    lines.append(f"  {_vpad('Pride Month 🌈 (June)', 28)}  {pride_swatches}")
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


def render_pr_summary(groups, title, label_header, colour, calendar="western"):
    """Render a compact PR summary table as a string.

    Args:
        groups: List of
            ``(name, url, count, draft_count, oldest_age_days, total_comments)``
            tuples, sorted by count descending.
        title: Heading line, e.g. ``"👤 PR Summary by Author"``.
        label_header: Column label printed above the name column,
            e.g. ``"Author"`` or ``"Repo"``.
        colour: Whether ANSI colour output is enabled.
        calendar: Seasonal calendar name (``"western"``, ``"jewish"``, etc.)
            or ``"off"`` to disable seasonal colouring entirely.

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
        # Always show at least one solid block when there are any non-draft PRs,
        # otherwise small draft minorities visually hide the open PRs entirely.
        if draft_count > 0 and count > 0:
            draft_blocks = max(1, round(draft_count / count * filled))
            if draft_count < count:
                draft_blocks = min(draft_blocks, filled - 1)
            else:
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
        if colour and calendar != "off":
            styled_name = apply_seasonal_colour(name, idx, calendar=calendar)
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
