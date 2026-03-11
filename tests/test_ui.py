import click
import pytest

from breakfast import ui


@pytest.mark.parametrize(
    "num,expected_color",
    [
        (5, "green"),
        (15, "yellow"),
        (30, (255, 165, 0)),
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
    assert "pass" in result

    result = ui.format_check_status("fail")
    assert "fail" in result
