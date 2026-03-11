from breakfast import config


def test_filter_pr_details_ignores_authors():
    pr_details = [
        {"user": {"login": "dependabot[bot]"}},
        {"user": {"login": "alice"}},
        {"user": {"login": "bob"}},
    ]

    filtered = config.filter_pr_details(
        pr_details,
        ignore_authors=["Dependabot[Bot]", "bob"],
    )

    assert filtered == [{"user": {"login": "alice"}}]


def test_filter_pr_details_mine_only():
    pr_details = [
        {"user": {"login": "alice"}},
        {"user": {"login": "bob"}},
    ]

    filtered = config.filter_pr_details(
        pr_details,
        ignore_authors=[],
        mine_only=True,
        current_user_login="alice",
    )

    assert filtered == [{"user": {"login": "alice"}}]


def test_normalize_ignore_authors_multiple():
    ignore_authors = [" Dependabot[Bot] ", "", "ALICE", "alice", None, "bob"]

    result = config.normalize_ignore_authors(ignore_authors)

    assert result == {"dependabot[bot]", "alice", "bob"}
