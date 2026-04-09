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
