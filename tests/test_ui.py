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
        (1, "purple"),
        (4, "yellow"),  # 2026 Easter is in April
        (10, "orange"),
        (12, "red"),
    ],
)
def test_seasonal_colour_by_special_month(month, expected_key):
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(month)
        colour = ui._seasonal_colour()
    assert colour == ui.SEASONAL_PALETTES[expected_key]


@pytest.mark.parametrize("month", [2, 3, 5, 6, 7, 8, 9, 11])
def test_seasonal_colour_non_special_months_return_none(month):
    with patch("breakfast.ui.datetime") as mock_dt:
        mock_dt.date.today.return_value = _today(month)
        colour = ui._seasonal_colour()
    assert colour is None


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
    assert ui._lny_date(9999) is None


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
        groups, "👤 PR Summary by Author", "Author", False, False
    )
    assert "alice" in result
    assert "bob" in result
    assert "8 PRs" in result
    assert "5 PRs" in result


def test_render_pr_summary_shows_title():
    groups = [("alice", _ALICE_URL, 1, 0, 5, 0)]
    result = ui.render_pr_summary(
        groups, "👤 PR Summary by Author", "Author", False, False
    )
    assert "👤 PR Summary by Author" in result


def test_render_pr_summary_shows_oldest_age_and_comments():
    groups = [("alice", _ALICE_URL, 3, 0, 15, 7)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, False)
    assert "oldest: 15d" in result
    assert "comments: 7" in result


def test_render_pr_summary_empty_groups():
    result = ui.render_pr_summary([], "Title", "Author", False, False)
    assert "no PRs" in result


def test_render_pr_summary_singular_pr():
    groups = [("alice", _ALICE_URL, 1, 0, 3, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, False)
    assert "1 PR " in result  # not "1 PRs"


def test_render_pr_summary_no_ansi_when_colour_false():
    groups = [("alice", _ALICE_URL, 5, 0, 50, 2), ("bob", _BOB_URL, 2, 0, 3, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, False)
    assert "\x1b[" not in result


def test_render_pr_summary_hyperlink_when_colour_enabled():
    groups = [("alice", _ALICE_URL, 1, 0, 3, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", True, False)
    assert _ALICE_URL in result


def test_render_pr_summary_no_hyperlink_when_colour_disabled():
    groups = [("alice", _ALICE_URL, 1, 0, 3, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, False)
    assert _ALICE_URL not in result


def test_render_pr_summary_bar_proportional():
    groups = [("alice", _ALICE_URL, 10, 0, 5, 0), ("bob", _BOB_URL, 5, 0, 5, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, False)
    lines = [ln for ln in result.splitlines() if "alice" in ln or "bob" in ln]
    alice_bar = lines[0].count("█")
    bob_bar = lines[1].count("█")
    assert alice_bar > bob_bar


def test_render_pr_summary_draft_shown_in_count():
    groups = [("alice", _ALICE_URL, 5, 2, 10, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, False)
    assert "2 draft" in result


def test_render_pr_summary_no_draft_suffix_when_zero():
    groups = [("alice", _ALICE_URL, 5, 0, 10, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, False)
    assert "draft" not in result


def test_render_pr_summary_draft_blocks_shown():
    # 3 open, 2 draft — bar should contain both solid and light-shade blocks
    groups = [("alice", _ALICE_URL, 5, 2, 10, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, False)
    alice_line = next(ln for ln in result.splitlines() if "alice" in ln)
    assert "█" in alice_line
    assert "▒" in alice_line


def test_render_pr_summary_all_draft_bar_all_light():
    groups = [("alice", _ALICE_URL, 3, 3, 5, 0)]
    result = ui.render_pr_summary(groups, "Title", "Author", False, False)
    alice_line = next(ln for ln in result.splitlines() if "alice" in ln)
    assert "█" not in alice_line
    assert "▒" in alice_line
