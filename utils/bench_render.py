#!/usr/bin/env python3
"""
Benchmark: table rendering pipeline for breakfast.

Measures _table_width, _auto_fit, and final tabulate call at varying PR counts.
Run with:
    uv run python utils/bench_render.py
"""

import re
import sys
import time
from pathlib import Path

# Make sure the src package is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from tabulate import tabulate

from breakfast.cli import _auto_fit, _table_width
from breakfast.ui import (
    click_colour_grade_number,
    format_mergeable_status,
    generate_terminal_url_anchor,
)

_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;]*[mK]|\]8;;[^\x1b]*\x1b\\)")

TERMINAL_WIDTH = 200  # wide enough that auto_fit won't drop columns
NARROW_WIDTH = 120  # forces auto_fit to work hard


def _make_pr_data(n):
    rows = []
    for i in range(n):
        row = {
            "Repo": f"some-long-repository-name-{i % 10}",
            "PR Title": f"feat: implement the extremely important feature number {i}",
            "Author": f"developer-with-a-longish-username-{i % 5}",
            "State": "open",
            "Files": click_colour_grade_number(i % 30 + 1),
            "Commits": click_colour_grade_number(i % 10 + 1),
            "+/-": (
                f"{click.style('+100', fg='green', bold=True)}"
                f"/{click.style('-50', fg='red', bold=True)}"
            ),
            "Comments": click_colour_grade_number(i % 5),
            "Mergeable?": format_mergeable_status(True, "clean"),
            "Link": generate_terminal_url_anchor(
                f"https://github.com/org/repo/pull/{i}", f"PR-{i}"
            ),
        }
        rows.append(row)
    return rows


def bench(label, fn, iterations=50):
    # warmup
    fn()
    fn()

    start = time.perf_counter()
    for _ in range(iterations):
        fn()
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / iterations) * 1000
    print(f"  {label:<55} {avg_ms:8.2f} ms/call")
    return avg_ms


def count_tabulate_calls(pr_data, terminal_width):
    """Monkey-patch tabulate to count how many times _auto_fit calls it."""
    import breakfast.cli as cli_mod

    original = cli_mod.tabulate
    count = [0]

    def counting_tabulate(*args, **kwargs):
        count[0] += 1
        return original(*args, **kwargs)

    cli_mod.tabulate = counting_tabulate
    try:
        _auto_fit(pr_data, terminal_width, None)
    finally:
        cli_mod.tabulate = original
    return count[0]


def run_benchmarks():
    print(f"\n{'=' * 75}")
    print("breakfast — table rendering benchmark")
    print(f"{'=' * 75}\n")

    for n in [10, 50, 100, 200]:
        pr_data = _make_pr_data(n)
        print(f"── {n} PRs ──")

        # How many tabulate() calls does auto_fit make at narrow width?
        calls_narrow = count_tabulate_calls(list(pr_data), NARROW_WIDTH)
        calls_wide = count_tabulate_calls(list(pr_data), TERMINAL_WIDTH)
        print(
            f"  tabulate() calls inside _auto_fit: "
            f"{calls_narrow} (narrow={NARROW_WIDTH}px)  /  "
            f"{calls_wide} (wide={TERMINAL_WIDTH}px)"
        )

        # _table_width alone
        bench(f"_table_width (1 call, {n} rows)", lambda d=pr_data: _table_width(d))

        # _auto_fit at narrow (most work)
        bench(
            f"_auto_fit    (narrow={NARROW_WIDTH}, {n} rows)",
            lambda d=pr_data: _auto_fit(list(d), NARROW_WIDTH, None),
        )

        # _auto_fit at wide (early return)
        bench(
            f"_auto_fit    (wide={TERMINAL_WIDTH},  {n} rows)",
            lambda d=pr_data: _auto_fit(list(d), TERMINAL_WIDTH, None),
        )

        # Final tabulate render
        bench(
            f"tabulate     (final render, {n} rows)",
            lambda d=pr_data: tabulate(
                d, headers="keys", showindex="always", tablefmt="outline"
            ),
        )

        # ANSI-strip cost alone
        def strip_only(d=pr_data):
            return [{k: _ANSI_RE.sub("", str(v)) for k, v in row.items()} for row in d]

        bench(f"ANSI strip   (all cells, {n} rows)", strip_only)

        print()

    print("Done.")


if __name__ == "__main__":
    run_benchmarks()
