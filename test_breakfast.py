import click
import pytest
from click.testing import CliRunner

import breakfast


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
    assert breakfast.click_colour_grade_number(num) == expected


def test_generate_terminal_url_anchor():
    url = "https://example.com/path"
    text = "Link"
    expected = f"\033]8;;{url}\033\\{text}\033]8;;\033\\"
    assert breakfast.generate_terminal_url_anchor(url, text) == expected


def test_make_github_api_request_builds_headers_and_url(monkeypatch):
    calls = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_get(url, headers):
        calls["url"] = url
        calls["headers"] = headers
        return DummyResponse()

    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast.requests, "get", fake_get)

    result = breakfast.make_github_api_request("/repos/org/repo")

    assert result == {"ok": True}
    assert calls["url"] == f"{breakfast.GITHUB_API_URL}/repos/org/repo"
    assert calls["headers"]["Authorization"] == "token token-123"
    assert calls["headers"]["Accept"] == "application/vnd.github.v3+json"


def test_get_github_prs_filters_and_paginates(monkeypatch):
    responses = [
        {
            "data": {
                "organization": {
                    "repositories": {
                        "nodes": [
                            {
                                "name": "app-one",
                                "pullRequests": {
                                    "nodes": [
                                        {
                                            "url": "https://example.com/app-one/1",
                                            "author": {"login": "alice"},
                                        }
                                    ]
                                },
                            },
                            {
                                "name": "other",
                                "pullRequests": {
                                    "nodes": [
                                        {
                                            "url": "https://example.com/other/2",
                                            "author": {"login": "bob"},
                                        }
                                    ]
                                },
                            },
                        ],
                        "pageInfo": {"endCursor": "cursor-1", "hasNextPage": True},
                    }
                }
            }
        },
        {
            "data": {
                "organization": {
                    "repositories": {
                        "nodes": [
                            {
                                "name": "app-two",
                                "pullRequests": {
                                    "nodes": [
                                        {
                                            "url": "https://example.com/app-two/3",
                                            "author": {"login": "carol"},
                                        }
                                    ]
                                },
                            }
                        ],
                        "pageInfo": {"endCursor": "cursor-2", "hasNextPage": False},
                    }
                }
            }
        },
    ]
    iterator = iter(responses)

    def fake_graphql_request(_query, _variables):
        return next(iterator)

    monkeypatch.setattr(breakfast, "make_github_graphql_request", fake_graphql_request)
    monkeypatch.setattr(breakfast, "BREAKFAST_ITEMS", ["*"])

    prs = breakfast.get_github_prs("org", "app")

    assert prs == [
        "https://example.com/app-one/1",
        "https://example.com/app-two/3",
    ]


def test_get_github_prs_ignore_author(monkeypatch):
    response = {
        "data": {
            "organization": {
                "repositories": {
                    "nodes": [
                        {
                            "name": "app-one",
                            "pullRequests": {
                                "nodes": [
                                    {
                                        "url": "https://example.com/app-one/1",
                                        "author": {"login": "dependabot[bot]"},
                                    },
                                    {
                                        "url": "https://example.com/app-one/2",
                                        "author": {"login": "alice"},
                                    },
                                ]
                            },
                        }
                    ],
                    "pageInfo": {"endCursor": "cursor-1", "hasNextPage": False},
                }
            }
        }
    }

    monkeypatch.setattr(
        breakfast,
        "make_github_graphql_request",
        lambda _query, _variables: response,
    )
    monkeypatch.setattr(breakfast, "BREAKFAST_ITEMS", ["*"])

    prs = breakfast.get_github_prs("org", "app", ignore_author="Dependabot[Bot]")

    assert prs == ["https://example.com/app-one/2"]


def test_cli_exits_when_token_missing(monkeypatch):
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", None)
    runner = CliRunner()

    result = runner.invoke(breakfast.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 1
    assert "GITHUB_TOKEN not set" in result.output


def test_cli_outputs_table(monkeypatch):
    monkeypatch.setattr(breakfast, "SECRET_GITHUB_TOKEN", "token-123")
    monkeypatch.setattr(breakfast, "BREAKFAST_ITEMS", ["*"])

    def fake_get_prs(_org, _repo_filter, ignore_author=None):
        return ["https://github.com/org/repo/pull/1"]

    def fake_api_request(_path):
        return {
            "mergeable": True,
            "mergeable_state": "clean",
            "additions": 5,
            "deletions": 2,
            "title": "Test PR",
            "user": {"login": "alice"},
            "state": "open",
            "changed_files": 1,
            "commits": 1,
            "review_comments": 0,
            "html_url": "https://github.com/org/repo/pull/1",
            "number": 1,
        }

    monkeypatch.setattr(breakfast, "get_github_prs", fake_get_prs)
    monkeypatch.setattr(breakfast, "make_github_api_request", fake_api_request)

    runner = CliRunner()
    result = runner.invoke(breakfast.breakfast, ["-o", "org", "-r", "repo"])

    assert result.exit_code == 0
    assert "PR-1" in result.output
    assert "repo" in result.output
