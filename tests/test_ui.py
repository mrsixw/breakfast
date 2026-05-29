import datetime
from unittest.mock import patch

import click
import pytest

from breakfast import ui


@pytest.mark.parametrize(
    "num,expected_color",
    [
        (5, "green"),
        (15, "yellow"),
        (30, 208),
        (60, "red"),
    ],
)
def test_click_colour_grade_number(num, expected_color):
    expected = click.style(str(num), fg=expected_color, bold=True)
    assert ui.click_colour_grade_number(num) == expected


def test_generate_terminal_url_anchor():
    url = "https://example.com/path"
    text = "Link"
    expected = f"\033]8;;{url}\033\\{text}\033]8;;\033\\"
    assert ui.generate_terminal_url_anchor(url, text) == expected


def test_format_check_status():
    result = ui.format_check_status("pass")
    assert "✅ pass" in result

    result = ui.format_check_status("fail")
    assert "❌ fail" in result

    result = ui.format_check_status("pending", style="ascii")
    assert "pending" in result
    assert "⚠️" not in result


def test_format_mergeable_status():
    assert "✅ (clean)" in ui.format_mergeable_status(True, "clean")
    assert "❌ (dirty)" in ui.format_mergeable_status(False, "dirty")
    assert "yes (clean)" in ui.format_mergeable_status(True, "clean", style="ascii")


def test_format_mergeable_status_amber_states():
    for state in ("behind", "unstable", "blocked"):
        result = ui.format_mergeable_status(True, state)
        assert "⚠️" in result, f"expected ⚠️ for state={state!r}"
        assert state in result


def test_format_mergeable_status_amber_ascii():
    result = ui.format_mergeable_status(True, "behind", style="ascii")
    assert "~" in result
    assert "behind" in result


def test_format_mergeable_status_merged_pr():
    result = ui.format_mergeable_status(None, None, pr_state="closed", merged=True)
    assert "🏁 merged" in result


def test_format_mergeable_status_closed_pr():
    result = ui.format_mergeable_status(None, None, pr_state="closed", merged=False)
    assert "🚫 closed" in result


def test_format_mergeable_status_closed_ascii():
    merged = ui.format_mergeable_status(
        None, None, style="ascii", pr_state="closed", merged=True
    )
    closed = ui.format_mergeable_status(
        None, None, style="ascii", pr_state="closed", merged=False
    )
    assert "merged" in merged
    assert "closed" in closed


def test_format_approval_status():
    result = ui.format_approval_status("approved")
    assert "✅ approved" in result

    result = ui.format_approval_status("pending")
    assert "⏳ pending" in result


def test_format_approval_status_with_counts():
    result = ui.format_approval_status(
        "pending",
        current_reviews=1,
        required_reviews=2,
    )
    assert "✅ 1/2 approvals" in result

    result = ui.format_approval_status(
        "pending",
        style="ascii",
        current_reviews=0,
        required_reviews=2,
    )
    assert "0/2 approvals" in result


def test_format_pr_state_open():
    result = ui.format_pr_state("open", is_draft=False)
    assert "open" in result
    assert "draft" not in result


def test_format_pr_state_draft():
    result = ui.format_pr_state("open", is_draft=True)
    assert "draft" in result
    assert "open" not in result


def test_format_pr_state_closed():
    result = ui.format_pr_state("closed")
    assert "closed" in result


# ---------------------------------------------------------------------------
# Seasonal colour Easter egg
# ---------------------------------------------------------------------------


def _today(month, day=1, year=2026):
    return datetime.date(year, month, day)


def test_easter_month_known_years():
    assert ui._easter_month(2024) == 3  # March 31, 2024
    assert ui._easter_month(2025) == 4  # April 20, 2025
    assert ui._easter_month(2026) == 4  # April 5, 2026
    assert ui._easter_month(2019) == 4  # April 21, 2019


@pytest.mark.parametrize(
    "month,expected_key",
    [
        (4, "yellow"),  # 2026 Easter is in April
        (10, "orange"),
    ],
)
def test_western_calendar_by_special_month(month, expected_key):
    result = ui._western_calendar(_today(month))
    assert result == ui.SEASONAL_PALETTES[expected_key]


def test_western_calendar_december_returns_candy_cane_list():
    result = ui._western_calendar(_today(12))
    assert isinstance(result, list)
    assert ui.SEASONAL_PALETTES["red"] in result
    assert ui.SEASONAL_PALETTES["green"] in result


def test_western_calendar_june_returns_pride_rainbow():
    result = ui._western_calendar(_today(6))
    assert result == ui.PRIDE_RAINBOW


@pytest.mark.parametrize("month", [1, 2, 3, 5, 7, 8, 9, 11])
def test_western_calendar_non_special_months_return_none(month):
    result = ui._western_calendar(_today(month))
    assert result is None


def test_apply_seasonal_colour_uses_single_colour():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(1)  # January → purple
        for pr_num in range(8):
            result = ui.apply_seasonal_colour("alice", pr_num)
            assert result.startswith(ui.SEASONAL_PALETTES["purple"])
            assert result.endswith("\033[0m")
            assert "alice" in result


def test_apply_seasonal_colour_non_special_month_returns_plain():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(7)  # July → no seasonal theme
        for pr_num in range(4):
            result = ui.apply_seasonal_colour("alice", pr_num)
            assert result == "alice"


def test_apply_seasonal_colour_christmas_alternates():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(12)  # December
        even_result = ui.apply_seasonal_colour("Test PR", 2)
        odd_result = ui.apply_seasonal_colour("Test PR", 3)
    # Even PR numbers → red, odd → green
    assert even_result.startswith(ui.SEASONAL_PALETTES["red"])
    assert odd_result.startswith(ui.SEASONAL_PALETTES["green"])


def test_apply_seasonal_colour_wraps_and_resets():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(10)  # October → orange
        result = ui.apply_seasonal_colour("hello", 0)
    assert "\033[0m" in result
    assert "hello" in result


# ---------------------------------------------------------------------------
# Valentine's Day 💕
# ---------------------------------------------------------------------------


def test_apply_seasonal_colour_valentines_day():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(2, day=14)  # Feb 14
        result = ui.apply_seasonal_colour("alice", 0)
    assert result.startswith(ui.SEASONAL_PALETTES["pink"])
    assert result.endswith("\033[0m")
    assert "alice" in result


def test_apply_seasonal_colour_not_valentines_day():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(2, day=15)  # Feb 15 — plain
        result = ui.apply_seasonal_colour("alice", 0)
    assert result == "alice"


# ---------------------------------------------------------------------------
# Lunar New Year 🧧
# ---------------------------------------------------------------------------


def test_lny_date_known_years():
    assert ui._lny_date(2024) == (2, 10)
    assert ui._lny_date(2025) == (1, 29)
    assert ui._lny_date(2026) == (2, 17)
    assert ui._lny_date(2028) == (1, 26)
    assert ui._lny_date(2031) == (1, 23)
    assert ui._lny_date(2034) == (2, 19)


def test_apply_seasonal_colour_lny_february():
    # 2026 LNY is 17 February — should show gold.
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = datetime.date(2026, 2, 17)
        result = ui.apply_seasonal_colour("alice", 0)
    assert result.startswith(ui.SEASONAL_PALETTES["lny"])
    assert result.endswith("\033[0m")


def test_apply_seasonal_colour_lny_january_stays_purple():
    # 2025 LNY is 29 January — January purple (birthday) must NOT be overridden.
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = datetime.date(2025, 1, 29)
        result = ui.apply_seasonal_colour("alice", 0)
    assert result.startswith(ui.SEASONAL_PALETTES["purple"])
    assert not result.startswith(ui.SEASONAL_PALETTES["lny"])


# ---------------------------------------------------------------------------
# Pride Month 🌈
# ---------------------------------------------------------------------------


def test_apply_seasonal_colour_pride_cycles_rainbow():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(6)  # June → Pride
        for i, expected_colour in enumerate(ui.PRIDE_RAINBOW):
            result = ui.apply_seasonal_colour("alice", i)
            assert result.startswith(expected_colour)
            assert result.endswith("\033[0m")


def test_apply_seasonal_colour_pride_wraps():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(6)
        n = len(ui.PRIDE_RAINBOW)
        assert ui.apply_seasonal_colour("x", 0) == ui.apply_seasonal_colour("x", n)


# ---------------------------------------------------------------------------
# render_colour_diagnostics (#189)
# ---------------------------------------------------------------------------


def test_render_colour_diagnostics_contains_section_headings():
    result = ui.render_colour_diagnostics()
    assert "Seasonal colours" in result
    assert "PR state" in result
    assert "Check status" in result
    assert "Approval status" in result
    assert "Mergeable status" in result
    assert "Number gradient" in result
    assert "Summary bar gradient" in result
    assert "UI / system colours" in result
    assert "+/- column" in result


def test_render_colour_diagnostics_contains_ansi_codes():
    result = ui.render_colour_diagnostics()
    assert "\033[" in result


def test_render_colour_diagnostics_is_string():
    result = ui.render_colour_diagnostics()
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# render_pr_summary (#177)
# ---------------------------------------------------------------------------


_ALICE_URL = "https://github.com/alice"
_BOB_URL = "https://github.com/bob"


def test_render_pr_summary_contains_names():
    groups = [
        ("alice", _ALICE_URL, 8, 0, 42, 14),
        ("bob", _BOB_URL, 5, 0, 7, 3),
    ]
    result = ui.render_pr_summary(
        groups, "👤 PR Summary by Author", "Author", False, "off"
    )
    assert "alice" in result
    assert "bob" in result
    assert "8 PRs" in result
    assert "5 PRs" in result


def test_render_pr_summary_shows_title():
    groups = [("alice", _ALICE_URL, 1, 0, 5, 0)]
    result = ui.render_pr_summary(
        groups, "👤 PR Summary by Author", "Author", False, "off"
    )
    assert "👤 PR Summary by Author" in result


def test_render_pr_summary_shows_oldest_age_and_comments():
    groups = [("alice", _ALICE_URL, 3, 0, 15, 7)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, "off")
    assert "oldest: 15d" in result
    assert "comments: 7" in result


def test_render_pr_summary_empty_groups():
    result = ui.render_pr_summary([], "Title", "Author", False, "off")
    assert "no PRs" in result


def test_render_pr_summary_singular_pr():
    groups = [("alice", _ALICE_URL, 1, 0, 3, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, "off")
    assert "1 PR " in result  # not "1 PRs"


def test_render_pr_summary_no_ansi_when_colour_false():
    groups = [("alice", _ALICE_URL, 5, 0, 50, 2), ("bob", _BOB_URL, 2, 0, 3, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, "off")
    assert "\x1b[" not in result


def test_render_pr_summary_hyperlink_when_colour_enabled():
    groups = [("alice", _ALICE_URL, 1, 0, 3, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", True, "off")
    assert _ALICE_URL in result


def test_render_pr_summary_no_hyperlink_when_colour_disabled():
    groups = [("alice", _ALICE_URL, 1, 0, 3, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, "off")
    assert _ALICE_URL not in result


def test_render_pr_summary_bar_proportional():
    groups = [("alice", _ALICE_URL, 10, 0, 5, 0), ("bob", _BOB_URL, 5, 0, 5, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, "off")
    lines = [ln for ln in result.splitlines() if "alice" in ln or "bob" in ln]
    alice_bar = lines[0].count("█")
    bob_bar = lines[1].count("█")
    assert alice_bar > bob_bar


def test_render_pr_summary_draft_shown_in_count():
    groups = [("alice", _ALICE_URL, 5, 2, 10, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, "off")
    assert "2 draft" in result


def test_render_pr_summary_no_draft_suffix_when_zero():
    groups = [("alice", _ALICE_URL, 5, 0, 10, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, "off")
    assert "draft" not in result


def test_render_pr_summary_draft_blocks_shown():
    # 3 open, 2 draft — bar should contain both solid and light-shade blocks
    groups = [("alice", _ALICE_URL, 5, 2, 10, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, "off")
    alice_line = next(ln for ln in result.splitlines() if "alice" in ln)
    assert "█" in alice_line
    assert "▒" in alice_line


def test_render_pr_summary_all_draft_bar_all_light():
    groups = [("alice", _ALICE_URL, 3, 3, 5, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, "off")
    alice_line = next(ln for ln in result.splitlines() if "alice" in ln)
    assert "█" not in alice_line
    assert "▒" in alice_line


def test_render_pr_summary_small_draft_minority_keeps_solid_block():
    """A group with only one draft out of many PRs must still show open PRs.

    Previously, max(1, ...) forced a draft block even when filled was 1,
    erasing the solid blocks for small (relative) groups.
    """
    # bob is the largest group (filled bar). alice has 10 PRs total, only 1
    # draft, but is small relative to bob — filled will be 1.
    groups = [
        ("bob", _ALICE_URL, 200, 0, 5, 0),
        ("alice", _ALICE_URL, 10, 1, 5, 0),
    ]
    result = ui.render_pr_summary(groups, "Title", "Author", False, "off")
    alice_line = next(ln for ln in result.splitlines() if "alice" in ln)
    assert "█" in alice_line


# ---------------------------------------------------------------------------
# Pluggable calendar system (#196)
# ---------------------------------------------------------------------------


def test_apply_seasonal_colour_off_returns_plain():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(1)  # January — normally purple
        result = ui.apply_seasonal_colour("alice", 0, calendar="off")
    assert result == "alice"


def test_apply_seasonal_colour_unknown_calendar_returns_plain():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(1)
        result = ui.apply_seasonal_colour("alice", 0, calendar="nonexistent")
    assert result == "alice"


def test_apply_seasonal_colour_western_default():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(1)  # January → purple
        result = ui.apply_seasonal_colour("alice", 0)  # default calendar
    assert result.startswith(ui.SEASONAL_PALETTES["purple"])


def test_jewish_calendar_hanukkah():
    hanukkah_2025 = datetime.date(2025, 12, 14)
    result = ui._jewish_calendar(hanukkah_2025)
    assert result == ui.SEASONAL_PALETTES["blue"]


def test_jewish_calendar_hanukkah_window():
    # 2025 Hanukkah is Dec 14–21 (8 nights)
    for day in range(14, 22):
        result = ui._jewish_calendar(datetime.date(2025, 12, day))
        assert result == ui.SEASONAL_PALETTES["blue"], f"day={day}"


def test_jewish_calendar_rosh_hashanah():
    rosh_2024 = datetime.date(2024, 10, 2)
    result = ui._jewish_calendar(rosh_2024)
    assert result == ui.SEASONAL_PALETTES["gold"]


def test_jewish_calendar_passover():
    passover_2025 = datetime.date(2025, 4, 12)
    result = ui._jewish_calendar(passover_2025)
    assert result == ui.SEASONAL_PALETTES["spring_green"]


def test_jewish_calendar_non_holiday_returns_none():
    result = ui._jewish_calendar(datetime.date(2025, 7, 15))
    assert result is None


def test_islamic_calendar_eid_al_fitr():
    eid_2024 = datetime.date(2024, 4, 10)
    result = ui._islamic_calendar(eid_2024)
    assert result == ui.SEASONAL_PALETTES["green"]


def test_islamic_calendar_eid_window():
    # Eid al-Fitr 2024: Apr 10, 3-day window
    for day in range(10, 13):
        result = ui._islamic_calendar(datetime.date(2024, 4, day))
        assert result == ui.SEASONAL_PALETTES["green"], f"day={day}"


def test_islamic_calendar_non_holiday_returns_none():
    result = ui._islamic_calendar(datetime.date(2025, 6, 15))
    assert result is None


def test_hindu_calendar_diwali():
    diwali_2024 = datetime.date(2024, 11, 1)
    result = ui._hindu_calendar(diwali_2024)
    assert result == ui.SEASONAL_PALETTES["gold"]


def test_hindu_calendar_holi_returns_rainbow():
    holi_2025 = datetime.date(2025, 3, 14)
    result = ui._hindu_calendar(holi_2025)
    assert isinstance(result, list)
    assert result == ui.HOLI_RAINBOW


def test_hindu_calendar_non_holiday_returns_none():
    result = ui._hindu_calendar(datetime.date(2025, 8, 15))
    assert result is None


def test_sikh_calendar_vaisakhi():
    vaisakhi = datetime.date(2025, 4, 13)
    result = ui._sikh_calendar(vaisakhi)
    assert result == ui.SEASONAL_PALETTES["spring_green"]


def test_sikh_calendar_diwali():
    diwali_2024 = datetime.date(2024, 11, 1)
    result = ui._sikh_calendar(diwali_2024)
    assert result == ui.SEASONAL_PALETTES["gold"]


def test_sikh_calendar_non_holiday_returns_none():
    result = ui._sikh_calendar(datetime.date(2025, 7, 4))
    assert result is None


def test_apply_seasonal_colour_jewish_calendar():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = datetime.date(2025, 12, 14)  # Hanukkah
        result = ui.apply_seasonal_colour("alice", 0, calendar="jewish")
    assert result.startswith(ui.SEASONAL_PALETTES["blue"])
    assert result.endswith("\033[0m")


def test_apply_seasonal_colour_holi_cycles_by_pr_number():
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = datetime.date(2025, 3, 14)  # Holi
        results = [ui.apply_seasonal_colour("x", i, calendar="hindu") for i in range(6)]
    for i, expected in enumerate(ui.HOLI_RAINBOW):
        assert results[i].startswith(expected)


def test_unknown_year_returns_none_gracefully():
    # Year 2099 is not in any lookup table — should return None, not crash.
    result = ui._jewish_calendar(datetime.date(2099, 12, 10))
    assert result is None


def test_in_holiday_window_unknown_year():
    result = ui._in_holiday_window(datetime.date(2099, 4, 1), ui._PASSOVER_START)
    assert result is False


def test_western_calendar_january_stays_purple_on_lny_2025():
    # 2025 LNY is Jan 29 — must return purple, not LNY gold.
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = datetime.date(2025, 1, 29)
        result = ui.apply_seasonal_colour("alice", 0, calendar="western")
    assert result.startswith(ui.SEASONAL_PALETTES["purple"])


def test_render_pr_summary_seasonal_calendar():
    # When a non-"off" calendar is passed, seasonal colours are applied.
    groups = [("alice", _ALICE_URL, 3, 0, 10, 0)]
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(1)  # January → purple
        result = ui.render_pr_summary(groups, "Title", "Author", True, "western")
    assert "\033[" in result


def test_global_january_purple_across_calendars():
    # Eid al-Fitr (2031-01-24), Eid al-Adha (2038-01-16), or LNY (2025-01-29)
    # falling in January must always return purple regardless of calendar.
    for cal in ["jewish", "islamic", "hindu", "sikh", "east-asian", "western"]:
        with patch("breakfast.ui.datetime") as mock_dt:
            mock_dt.date.today.return_value = datetime.date(2025, 1, 29)
            result = ui.apply_seasonal_colour("x", 0, calendar=cal)
        assert result.startswith(ui.SEASONAL_PALETTES["purple"]), f"cal={cal}"


def test_islamic_calendar_eid_al_adha():
    # Eid al-Adha 2024 starts June 16, 3-day window
    for d in range(16, 19):
        result = ui._islamic_calendar(datetime.date(2024, 6, d))
        assert result == ui.SEASONAL_PALETTES["green"], f"day={d}"


def test_jewish_calendar_sukkot():
    # Sukkot 2025 starts Oct 6, 7-day window
    for d in range(6, 13):
        result = ui._jewish_calendar(datetime.date(2025, 10, d))
        assert result == ui.SEASONAL_PALETTES["orange"], f"day={d}"


def test_east_asian_calendar_songkran():
    # Songkran: April 13-15 (fixed)
    for d in range(13, 16):
        result = ui._east_asian_calendar(datetime.date(2025, 4, d))
        assert result == ui.SEASONAL_PALETTES["blue"], f"day={d}"


def test_east_asian_calendar_hanami():
    # Hanami: April 1-7 (fixed)
    for d in range(1, 8):
        result = ui._east_asian_calendar(datetime.date(2025, 4, d))
        assert result == ui.SEASONAL_PALETTES["pink"], f"day={d}"


def test_east_asian_calendar_lny():
    # Lunar New Year 2026 starts Feb 17, 3-day window
    for d in range(17, 20):
        result = ui._east_asian_calendar(datetime.date(2026, 2, d))
        assert result == ui.SEASONAL_PALETTES["lny"], f"day={d}"


def test_east_asian_calendar_mid_autumn():
    # Mid-Autumn Festival 2024 starts Sep 17, 2-day window
    for d in range(17, 19):
        result = ui._east_asian_calendar(datetime.date(2024, 9, d))
        assert result == ui.SEASONAL_PALETTES["yellow"], f"day={d}"


def test_east_asian_calendar_non_holiday():
    result = ui._east_asian_calendar(datetime.date(2025, 8, 15))
    assert result is None


def test_unknown_year_graceful_east_asian():
    result = ui._east_asian_calendar(datetime.date(2099, 5, 5))
    assert result is None


def test_render_colour_diagnostics_shows_all_new_palettes_and_holi():
    result = ui.render_colour_diagnostics()
    assert "Hanukkah / Songkran" in result
    assert "Passover / Vaisakhi" in result
    assert "Lunar New Year" in result
    assert "Rosh / Diwali / Bandi" in result
    assert "Holi 🎨" in result
