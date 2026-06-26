from datetime import datetime, timezone

from tabulate import tabulate

from breakfast import renderers


def test_table_width_matches_tabulate_border():
    """_table_width must agree with the actual tabulate outline border width."""
    test_cases = [
        [{"Repo": "repo", "PR Title": "title", "Author": "alice"}],
        [
            {"Repo": "short", "PR Title": "a", "Author": "bob"},
            {
                "Repo": "a-very-long-repository-name",
                "PR Title": "longer title here",
                "Author": "carol",
            },
        ],
        [{"Col": "x"} for _ in range(10)],
        [{"A": "hello", "B": "\x1b[32mgreen\x1b[0m", "C": "plain"}],
    ]
    for rows in test_cases:
        plain_rows = [
            {k: renderers._strip_ansi(v) for k, v in row.items()} for row in rows
        ]
        expected = len(
            tabulate(
                plain_rows,
                headers="keys",
                showindex="always",
                tablefmt="outline",
                disable_numparse=True,
            ).splitlines()[0]
        )
        assert renderers._table_width(rows) == expected, f"Mismatch for rows={rows!r}"


def test_auto_fit_measures_later_rows_when_fitting_table():
    rows = [
        {
            "Repo": "short",
            "PR Title": "short",
            "Author": "alice",
            "State": "open",
            "Files": "1",
            "Commits": "1",
            "+/-": "+1/-0",
            "Comments": "0",
            "Mergeable?": "yes (clean)",
            "Link": "PR-1",
        },
        {
            "Repo": "a-very-long-repository-name-that-should-be-truncated",
            "PR Title": "short",
            "Author": "alice",
            "State": "open",
            "Files": "1",
            "Commits": "1",
            "+/-": "+1/-0",
            "Comments": "0",
            "Mergeable?": "yes (clean)",
            "Link": "PR-2",
        },
    ]

    terminal_width = renderers._table_width(rows[:1])
    fitted_rows = renderers._auto_fit(
        rows, terminal_width, explicit_max_title_length=None
    )
    rendered_width = len(
        tabulate(
            fitted_rows, headers="keys", showindex="always", tablefmt="outline"
        ).splitlines()[0]
    )

    assert rendered_width <= terminal_width
    assert fitted_rows[1]["Repo"].endswith("…")


def test_auto_fit_truncates_branches_before_repo():
    """Branches should be truncated before the repo name (#175)."""
    long_branch = "a-very-long-head-branch-name-that-should-go-first"
    long_repo = "a-long-repo-name-that-should-survive-longer"
    rows = [
        {
            "Repo": long_repo,
            "PR Title": "Short title",
            "Author": "alice",
            "State": "open",
            "Head Branch": long_branch,
            "Base Branch": "main",
            "Comments": "0",
            "Link": "PR-1",
        }
    ]

    # Width just wide enough for the full row minus the long branch — forces
    # head-branch truncation but not necessarily repo truncation.
    width_without_long_branch = renderers._table_width(
        [{**rows[0], "Head Branch": "short-branch"}]
    )
    result = renderers._auto_fit(
        rows, width_without_long_branch, explicit_max_title_length=None
    )

    visible_head = renderers._strip_ansi(result[0]["Head Branch"])
    visible_repo = renderers._strip_ansi(result[0]["Repo"])

    # Head branch should have been truncated (it's longer and was tried first)
    assert visible_head != long_branch, "Head Branch should have been truncated"
    # Repo should still be intact because truncating the branch was enough
    assert (
        visible_repo == long_repo
    ), "Repo should NOT have been truncated before branches"


def test_auto_fit_renames_mergeable_to_mrg():
    rows = [{"Mergeable?": "✅", "PR Title": "x", "Repo": "r", "Author": "a"}]
    # Set terminal width just narrow enough to trigger step 5b but not step 5+
    width = renderers._table_width(rows) - 1
    result = renderers._auto_fit(rows, width, explicit_max_title_length=None)
    keys = list(result[0].keys())
    assert "Mrg" in keys
    assert "Mergeable?" not in keys


def test_strip_ansi():
    assert renderers._strip_ansi("\x1b[32mhello\x1b[0m") == "hello"
    assert renderers._strip_ansi("plain") == "plain"


def test_visible_width():
    assert renderers._visible_width("\x1b[32mhello\x1b[0m") == 5
    assert renderers._visible_width("hello") == 5


def test_osc8_to_markdown():
    link = "\x1b]8;;http://example.com\x1b\\linktext\x1b]8;;\x1b\\"
    assert renderers._osc8_to_markdown(link) == "[linktext](http://example.com)"


def test_is_legendary():
    # Legendary: 100+ comments (total) AND 30+ days open.
    pr = {
        "comments": 50,
        "review_comments": 50,
        "created_at": "2026-01-01T00:00:00Z",
    }
    now = datetime(2026, 2, 10, tzinfo=timezone.utc)
    assert renderers.is_legendary(pr, now=now) is True

    # Not enough comments
    pr["comments"] = 49
    assert renderers.is_legendary(pr, now=now) is False

    # Not open long enough
    pr["comments"] = 50
    now_too_early = datetime(2026, 1, 20, tzinfo=timezone.utc)
    assert renderers.is_legendary(pr, now=now_too_early) is False


def test_compress_styled_preserves_ansi_colour():
    import click

    styled = click.style("✅ pass", fg="green", bold=True)
    compressed = renderers._compress_styled(styled)
    # Should keep the emoji but drop " pass"
    assert "✅" in renderers._strip_ansi(compressed)
    assert "pass" not in renderers._strip_ansi(compressed)
    # ANSI colour codes should be preserved
    assert "\x1b[" in compressed


def test_compress_styled_noop_for_single_word():
    import click

    styled = click.style("✅", fg="green", bold=True)
    assert renderers._compress_styled(styled) == styled


def test_compress_styled_plain_text():
    assert renderers._compress_styled("hello world") == "hello"
    assert renderers._compress_styled("single") == "single"


def test_compress_styled_preserves_approval_fraction():
    from breakfast.ui import format_approval_status

    styled = format_approval_status(
        "pending",
        current_reviews=1,
        required_reviews=2,
    )

    compressed = renderers._compress_styled(styled)

    assert renderers._strip_ansi(compressed) == "✅ 1/2"


def test_truncate_formatted_text_preserves_osc8_anchor():
    from breakfast.ui import generate_terminal_url_anchor

    linked_repo = generate_terminal_url_anchor(
        "https://github.com/myorg/really-long-repo-name",
        "really-long-repo-name",
    )

    truncated = renderers._truncate_formatted_text(linked_repo, 8)

    assert renderers._strip_ansi(truncated) == "really-…"
    assert "\x1b]8;;https://github.com/myorg/really-long-repo-name\x1b\\" in truncated
    assert truncated.endswith("\x1b]8;;\x1b\\")
    assert "]8;;ht…" not in truncated


def test_truncate_col_preserves_repo_and_author_hyperlinks():
    from breakfast.ui import generate_terminal_url_anchor

    rows = [
        {
            "Repo": generate_terminal_url_anchor(
                "https://github.com/myorg/really-long-repo-name",
                "really-long-repo-name",
            ),
            "PR Title": "Short title",
            "Author": generate_terminal_url_anchor(
                "https://github.com/some-very-long-author-name",
                "some-very-long-author-name",
            ),
            "State": "open",
            "Files": "1",
            "Commits": "1",
            "+/-": "+1/-0",
            "Comments": "0",
            "Mergeable?": "✅ (clean)",
            "Link": "PR-1",
        }
    ]

    truncated = renderers._truncate_col(rows, "Repo", terminal_width=40, min_len=8)
    truncated = renderers._truncate_col(
        truncated, "Author", terminal_width=40, min_len=8
    )

    assert (
        "\x1b]8;;https://github.com/myorg/really-long-repo-name\x1b\\"
        in truncated[0]["Repo"]
    )
    assert (
        "\x1b]8;;https://github.com/some-very-long-author-name\x1b\\"
        in truncated[0]["Author"]
    )
    assert "]8;;ht…" not in truncated[0]["Repo"]
    assert "]8;;ht…" not in truncated[0]["Author"]


def test_auto_fit_preserves_checks_colour(monkeypatch):
    import click

    styled_checks = click.style("✅ pass", fg="green", bold=True)
    rows = [
        {
            "Repo": "myrepo",
            "PR Title": "Some title",
            "Author": "alice",
            "State": "open",
            "Files": "1",
            "Commits": "1",
            "+/-": "+1/-0",
            "Comments": "0",
            "Checks": styled_checks,
            "Mergeable?": click.style("✅ (clean)", fg="green", bold=True),
            "Link": "PR-1",
        }
    ]
    # Very narrow width to force all compression steps
    result = renderers._auto_fit(rows, 80, explicit_max_title_length=None)
    checks_key = "Checks" if "Checks" in result[0] else None
    if checks_key:
        # Colour should be preserved even after compression
        assert "\x1b[" in result[0][checks_key]


def test_styled_hyperlink_puts_colour_outside_osc8():
    import click

    styled = click.style("pending", fg="yellow", bold=True)
    result = renderers._styled_hyperlink("https://example.com/checks", styled)
    # Find the link text between the OSC 8 open and close tags
    osc_open_end = result.index("\x1b\\") + 2
    osc_close_start = result.index("\x1b]8;;\x1b\\", osc_open_end)
    link_text = result[osc_open_end:osc_close_start]
    assert link_text == "pending"  # plain text inside the OSC 8, no escape sequences
    assert "\x1b[" in result  # colour codes still present outside the OSC 8


def test_table_width_auto_fit_emoji_regression():
    """Verify that _table_width accounts for double-width emojis correctly

    so that auto-fit does not underestimate table display width.
    """
    rows = [
        {
            "Repo": "short",
            "PR Title": "short title",
            "Author": "alice",
            "Checks": "✅ pass",
            "Approved": "⏳ pending",
            "Mergeable?": "❌ (dirty)",
        }
    ]
    # Estimate width using _table_width
    estimated_width = renderers._table_width(rows)

    # Actual width from tabulate (with wcwidth installed)
    from tabulate import tabulate

    actual_width = len(
        tabulate(
            rows,
            headers="keys",
            showindex="always",
            tablefmt="outline",
            disable_numparse=True,
        ).splitlines()[0]
    )

    # They should match exactly, preventing line wrap double spacing
    assert estimated_width == actual_width


def test_render_table_stdout_is_tty(capsys):
    """Test that render_table uses stdout_is_tty parameter to skip auto-fitting."""
    pr_details = [
        {
            "number": 1,
            "html_url": "https://github.com/org/repo/pull/1",
            "title": "A very long title that would normally be truncated or fitted",
            "user": {"login": "alice"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "additions": 5,
            "deletions": 2,
            "base": {
                "ref": "main",
                "repo": {"name": "repo", "owner": {"login": "org"}},
            },
        }
    ]

    renderers.render_table(
        pr_details=pr_details,
        organizations=["org"],
        legendary=False,
        age=False,
        checks=False,
        approvals=False,
        check_statuses={},
        approval_statuses={},
        approval_details={},
        head_branch=False,
        base_branch=False,
        status_style="emoji",
        seasonal_calendar="western",
        colour=False,
        colour_index=False,
        max_title_length=None,
        column_specs=None,
        stdout_is_tty=False,
    )
    captured = capsys.readouterr()
    assert "A very long title" in captured.out


def test_droppable_columns_approved():
    """Verify that the Approved column (renamed to Apr) is droppable under auto-fit."""
    rows = [
        {
            "Repo": "short",
            "PR Title": "title",
            "Author": "alice",
            "Approved": "⏳ pending",
        }
    ]
    # We call _auto_fit directly with a narrow terminal width to force column dropping
    fitted = renderers._auto_fit(
        rows, terminal_width=20, explicit_max_title_length=None
    )
    # The column "Apr" should be dropped since we fixed the name in _DROPPABLE_COLUMNS
    for row in fitted:
        assert "Approved" not in row
        assert "Apr" not in row


def test_format_reviewers_and_labels_overflow():
    """Verify that reviewers and labels format correctly with +N overflow."""
    assert renderers.format_reviewers([{"login": "alice"}]) == "alice"
    assert (
        renderers.format_reviewers([{"login": "alice"}, {"login": "bob"}])
        == "alice, bob"
    )
    assert (
        renderers.format_reviewers(
            [{"login": "alice"}, {"login": "bob"}, {"login": "charlie"}]
        )
        == "alice, bob +1"
    )
    assert renderers.format_reviewers([]) == "-"
    assert renderers.format_reviewers(None) == "-"

    # Teams review requests tests
    assert (
        renderers.format_reviewers([{"login": "alice"}], [{"slug": "team-slug"}])
        == "alice, @team-slug"
    )
    assert (
        renderers.format_reviewers(
            [{"login": "alice"}, {"login": "bob"}], [{"slug": "team-slug"}]
        )
        == "alice, bob +1"
    )

    assert renderers.format_labels([{"name": "bug"}]) == "bug"
    assert (
        renderers.format_labels([{"name": "bug"}, {"name": "urgent"}]) == "bug, urgent"
    )
    assert (
        renderers.format_labels(
            [{"name": "bug"}, {"name": "urgent"}, {"name": "enhancement"}]
        )
        == "bug, urgent +1"
    )
    assert renderers.format_labels([]) == "-"


def test_autofit_truncates_reviewers_and_labels():
    """Verify that reviewers and labels columns are truncated and dropped by autofit."""
    rows = [
        {
            "Repo": "short",
            "PR Title": "title",
            "Author": "alice",
            "Reviewers": "alice, bob +5",
            "Labels": "bug, urgent +3",
        }
    ]
    truncated = renderers._auto_fit(
        rows, terminal_width=65, explicit_max_title_length=None
    )
    assert len(truncated[0]["Reviewers"]) <= 12
    assert len(truncated[0]["Labels"]) <= 12

    # Verify dropping under extremely narrow terminal
    fitted = renderers._auto_fit(
        rows, terminal_width=20, explicit_max_title_length=None
    )
    for row in fitted:
        assert "Reviewers" not in row
        assert "Labels" not in row
