import csv
import io
import json
import re
import shutil
import sys
import time

import click
import wcwidth
from tabulate import tabulate

from .api import get_pr_age_days
from .ui import (
    apply_seasonal_colour,
    click_colour_grade_number,
    format_approval_status,
    format_check_status,
    format_mergeable_status,
    format_pr_state,
    generate_terminal_url_anchor,
)

# Constants for legendary PRs
_LEGENDARY_COMMENT_THRESHOLD = 100
_LEGENDARY_AGE_THRESHOLD_DAYS = 30
_LEGENDARY_EMOJI = "⚔️"

_COLUMN_DISPLAY_NAMES: dict[str, str] = {
    "org": "Org",
    "repo": "Repo",
    "title": "PR Title",
    "author": "Author",
    "state": "State",
    "files": "Files",
    "commits": "Commits",
    "diff": "+/-",
    "comments": "Comments",
    "age": "Age",
    "checks": "Checks",
    "approvals": "Approved",
    "head-branch": "Head Branch",
    "base-branch": "Base Branch",
    "mergeable": "Mergeable?",
    "link": "Link",
}

# Columns dropped as last resort (least important first)
_DROPPABLE_COLUMNS = [
    "State",
    "Commits",
    "Files",
    "+/-",
    "Cmt",
    "Age",
    "Checks",
    "Apr",
    "Head Branch",
    "Base Branch",
    "Mrg",
]

_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;]*[a-zA-Z]|\]8;;.*?\x1b\\|\]8;;.*?\x07)")
_ANSI_LEADING_RE = re.compile(r"^(?:\x1b\[[0-9;]*[a-zA-Z])*")
_OSC8_FULL_RE = re.compile(
    r"^(?P<prefix>(?:\x1b\[[0-9;]*[a-zA-Z])*)"
    r"\x1b]8;;(?P<url>.*?)(?:\x1b\\|\x07)"
    r"(?P<text>.*?)"
    r"\x1b]8;;(?:\x1b\\|\x07)"
    r"(?P<suffix>(?:\x1b\[[0-9;]*[a-zA-Z])*)$"
)
_OSC8_ANY_RE = re.compile(
    r"\x1b]8;;(?P<url>.*?)(?:\x1b\\|\x07)(?P<text>.*?)\x1b]8;;(?:\x1b\\|\x07)"
)
_ANSI_RESET = "\x1b[0m"


def _get_pr_age_days(pr_detail, now=None):
    return get_pr_age_days(pr_detail, now=now)


def is_legendary(pr_detail, now=None):
    """Return True if a PR qualifies as legendary.

    A PR is legendary if it has 100+ total comments AND has been open 30+ days.
    """
    total_comments = pr_detail.get("comments", 0) + pr_detail.get("review_comments", 0)
    return (
        total_comments >= _LEGENDARY_COMMENT_THRESHOLD
        and _get_pr_age_days(pr_detail, now=now) >= _LEGENDARY_AGE_THRESHOLD_DAYS
    )


def _strip_ansi(s):
    return _ANSI_RE.sub("", str(s))


def _visible_width(s):
    """Return the terminal display width of a string, ignoring ANSI escape codes."""
    plain = _strip_ansi(s)
    w = wcwidth.wcswidth(plain)
    return w if w >= 0 else len(plain)


def _slice_by_width(s: str, max_width: int) -> str:
    """Return the longest prefix of *s* whose display width is <= *max_width*.

    Uses per-character wcwidth so CJK (width-2) and emoji are handled correctly.
    """
    out, used = [], 0
    for ch in s:
        w = max(wcwidth.wcwidth(ch), 0)
        if used + w > max_width:
            break
        out.append(ch)
        used += w
    return "".join(out)


def _osc8_to_markdown(s):
    """Convert OSC 8 hyperlinks and ANSI codes in *s* to Markdown link syntax."""
    result = _OSC8_ANY_RE.sub(
        lambda m: f"[{m.group('text')}]({m.group('url')})", str(s)
    )
    return _strip_ansi(result)


def _truncate_formatted_text(value, limit):
    """Truncate visible text while preserving ANSI and OSC 8 wrappers.

    Args:
        value: Cell value that may contain ANSI styling or OSC 8 hyperlinks.
        limit: Maximum visible character count, including the ellipsis.

    Returns:
        The truncated value with any existing formatting preserved.
    """
    plain = _strip_ansi(value)
    if _visible_width(plain) <= limit:
        return value

    truncated = _slice_by_width(plain, limit - 1) + "…"
    osc_match = _OSC8_FULL_RE.match(str(value))
    if osc_match:
        return (
            osc_match.group("prefix")
            + generate_terminal_url_anchor(osc_match.group("url"), truncated)
            + osc_match.group("suffix")
        )

    if plain != value:
        return str(value).replace(plain, truncated, 1)
    return truncated


def _styled_hyperlink(url, styled_text):
    """Wrap a click.style'd string in an OSC 8 hyperlink.

    Tabulate's OSC 8 parser requires the link text to contain no escape
    sequences. This helper moves leading ANSI colour codes outside the OSC 8
    escape so tabulate measures column width correctly while the terminal
    still renders the text in colour.
    """
    plain = _strip_ansi(styled_text)
    prefix = _ANSI_LEADING_RE.match(styled_text).group()
    suffix = _ANSI_RESET if _ANSI_RESET in styled_text else ""
    return prefix + generate_terminal_url_anchor(url, plain) + suffix


def _table_width(rows):
    """Return visual table width without rendering the full table.

    Replicates the border line width of tabulate's outline format.
    Each column contributes max(header_len+4, cell_max+2) dashes plus
    a leading '+'. The index column uses header_len=0.
    """
    if not rows:
        return 0
    headers = list(rows[0].keys())
    idx_width = len(str(len(rows) - 1))
    # Index column: header is empty, content is the row number
    total = 1 + max(4, idx_width + 2) + 1
    for h in headers:
        cell_max = max(
            (_visible_width(str(row.get(h, ""))) for row in rows),
            default=0,
        )
        total += max(_visible_width(h) + 4, cell_max + 2) + 1
    return total


def _truncate_col(pr_data, key, terminal_width, min_len=8):
    """Shrink a text column to help the table fit within terminal_width.

    For PR Title, calculates the exact available space from overhead.
    For other columns (Repo, Author), trims by the current excess so that
    even when many other wide columns are present the truncation still fires.
    """
    if key not in pr_data[0]:
        return pr_data

    if key == "PR Title":
        # Exact calculation: measure overhead with a placeholder title
        overhead = _table_width([{**pr_data[0], key: "X" * min_len}]) - min_len
        limit = terminal_width - overhead
    else:
        # Excess-based: shrink the longest value by however much the table overflows
        excess = _table_width(pr_data) - terminal_width
        if excess <= 0:
            return pr_data
        current_max = max(_visible_width(row[key]) for row in pr_data)
        limit = max(current_max - excess, min_len)

    if limit < min_len:
        return pr_data
    return [
        {
            **row,
            key: _truncate_formatted_text(row[key], limit),
        }
        for row in pr_data
    ]


def _compress_styled(styled_text):
    """Compress styled text to its first visible word, preserving ANSI colour."""
    plain = _strip_ansi(styled_text)
    words = plain.split()
    if len(words) <= 1:
        return styled_text
    if len(words) >= 2 and re.fullmatch(r"\d+/\d+", words[1]):
        compressed = " ".join(words[:2])
    else:
        compressed = words[0]
    return styled_text.replace(plain, compressed, 1)


def _auto_fit(pr_data, terminal_width, explicit_max_title_length):
    """Progressively compress the table to fit within terminal_width."""
    if not pr_data:
        return pr_data

    def fits():
        return _table_width(pr_data) <= terminal_width

    # 1. Auto-truncate PR Title (skip if caller already applied an explicit limit)
    if explicit_max_title_length is None:
        pr_data = _truncate_col(pr_data, "PR Title", terminal_width, min_len=10)

    if fits():
        return pr_data

    # 2. Truncate Author
    pr_data = _truncate_col(pr_data, "Author", terminal_width, min_len=8)
    if fits():
        return pr_data

    # 3. Truncate Head Branch / Base Branch (before Repo — branches matter less)
    pr_data = _truncate_col(pr_data, "Head Branch", terminal_width, min_len=8)
    if fits():
        return pr_data
    pr_data = _truncate_col(pr_data, "Base Branch", terminal_width, min_len=8)
    if fits():
        return pr_data

    # 4. Truncate Repo (last text column — repo identity should stay readable longest)
    pr_data = _truncate_col(pr_data, "Repo", terminal_width, min_len=8)
    if fits():
        return pr_data

    # 5. Compress Mergeable?: drop the reason suffix
    if "Mergeable?" in pr_data[0]:

        def _compress_mergeable(val):
            plain = _strip_ansi(val)
            compressed = re.sub(r" \(.*\)$", "", plain)
            if compressed != plain:
                return val.replace(plain, compressed, 1)
            return val

        pr_data = [
            {**row, "Mergeable?": _compress_mergeable(row["Mergeable?"])}
            for row in pr_data
        ]
    if fits():
        return pr_data

    # 5b. Rename "Mergeable?" → "Mrg" (shorter header)
    if "Mergeable?" in pr_data[0]:
        pr_data = [
            {("Mrg" if k == "Mergeable?" else k): v for k, v in row.items()}
            for row in pr_data
        ]
    if fits():
        return pr_data

    # 6. Compress Checks: "✅ pass" → "✅" (preserving colour)
    if "Checks" in pr_data[0]:
        pr_data = [
            {**row, "Checks": _compress_styled(row["Checks"])} for row in pr_data
        ]
    if fits():
        return pr_data

    # 6b. Compress Approved: "✅ approved" → "✅", "✅ 1/2 approvals" → "✅ 1/2"
    if "Approved" in pr_data[0]:
        pr_data = [
            {**row, "Approved": _compress_styled(row["Approved"])} for row in pr_data
        ]
    if fits():
        return pr_data

    # 7. Rename "Comments" → "Cmt" (shorter header)
    if "Comments" in pr_data[0]:
        pr_data = [
            {("Cmt" if k == "Comments" else k): v for k, v in row.items()}
            for row in pr_data
        ]
    if fits():
        return pr_data

    # 7b. Rename "Approved" → "Apr" (shorter header)
    if "Approved" in pr_data[0]:
        pr_data = [
            {("Apr" if k == "Approved" else k): v for k, v in row.items()}
            for row in pr_data
        ]
    if fits():
        return pr_data

    # 8. Drop low-priority columns as last resort
    for col in _DROPPABLE_COLUMNS:
        if fits():
            break
        if col in pr_data[0]:
            pr_data = [{k: v for k, v in row.items() if k != col} for row in pr_data]

    return pr_data


def _apply_column_specs(
    pr_data: list[dict],
    column_specs: list[dict],
    multi_org: bool,
) -> tuple[list[dict], tuple | None]:
    """Reorder, filter, and rename columns per user column specs.

    Returns ``(new_pr_data, colalign)`` where *colalign* is either a tuple of
    alignment strings (one per column) for tabulate, or ``None`` when no custom
    alignments are set.
    """
    if not pr_data:
        return pr_data, None

    first = pr_data[0]
    ordered: list[tuple[str, str, str | None]] = []
    for spec in column_specs:
        display_key = _COLUMN_DISPLAY_NAMES.get(spec["name"])
        if not display_key:
            continue
        if spec["name"] == "org" and not multi_org:
            continue
        if display_key not in first:
            continue
        header = spec["header"] if spec["header"] else display_key
        ordered.append((display_key, header, spec["align"]))

    if not ordered:
        return pr_data, None

    new_pr_data = [
        {header: row[display_key] for display_key, header, _ in ordered}
        for row in pr_data
    ]

    has_custom_align = any(align is not None for _, _, align in ordered)
    colalign = (
        tuple(align if align else "left" for _, _, align in ordered)
        if has_custom_align
        else None
    )
    return new_pr_data, colalign


# _stdout_is_tty removed to avoid circular imports


def render_json(
    pr_details,
    checks,
    approvals,
    check_statuses,
    approval_statuses,
    approval_details,
):
    from .logger import logger

    logger.info("render format=json row_count=%d", len(pr_details))
    t_render = time.monotonic()
    json_data = []
    for pr_detail in pr_details:
        entry = {
            "repo": pr_detail["base"]["repo"]["name"],
            "pr_number": pr_detail["number"],
            "title": pr_detail["title"],
            "author": pr_detail["user"]["login"],
            "url": pr_detail["html_url"],
            "state": pr_detail["state"],
            "draft": pr_detail.get("draft", False),
            "created_at": pr_detail.get("created_at"),
            "updated_at": pr_detail.get("updated_at"),
            "additions": pr_detail.get("additions"),
            "deletions": pr_detail.get("deletions"),
            "changed_files": pr_detail.get("changed_files"),
            "commits": pr_detail.get("commits"),
            "review_comments": pr_detail.get("review_comments"),
            "labels": [lb["name"] for lb in pr_detail.get("labels", [])],
            "requested_reviewers": [
                r["login"] for r in pr_detail.get("requested_reviewers", [])
            ],
        }
        if checks:
            entry["checks"] = check_statuses.get(pr_detail["id"], "none")
        if approvals:
            entry["approval"] = approval_statuses.get(pr_detail["id"], "pending")
            approval_detail = approval_details.get(pr_detail["id"], {})
            if approval_detail.get("current") is not None:
                entry["approval_current"] = approval_detail["current"]
            if approval_detail.get("required") is not None:
                entry["approval_required"] = approval_detail["required"]
        json_data.append(entry)
    click.echo(json.dumps(json_data, indent=2))
    logger.info(
        "render_complete elapsed_ms=%d", int((time.monotonic() - t_render) * 1000)
    )


def render_markdown(
    pr_details,
    age,
    checks,
    approvals,
    check_statuses,
    approval_statuses,
    approval_details,
    head_branch,
    base_branch,
    status_style,
):
    from .logger import logger

    logger.info("render format=markdown row_count=%d", len(pr_details))
    t_render = time.monotonic()
    md_data = []
    for pr_detail in pr_details:
        repo = pr_detail["base"]["repo"]
        repo_url = repo.get("html_url") or pr_detail["html_url"].split("/pull/")[0]
        author = pr_detail["user"]
        author_url = author.get("html_url") or f"https://github.com/{author['login']}"
        state_str = pr_detail["state"]
        if pr_detail.get("draft"):
            state_str = "draft"
        adds = pr_detail.get("additions", 0)
        subs = pr_detail.get("deletions", 0)
        row = {
            "Repo": f"[{repo['name']}]({repo_url})",
            "PR Title": pr_detail["title"],
            "Author": f"[{author['login']}]({author_url})",
            "State": state_str,
            "Files": str(pr_detail["changed_files"]),
            "Commits": str(pr_detail["commits"]),
            "+/-": f"+{adds}/-{subs}",
            "Comments": str(pr_detail["review_comments"]),
        }
        if age:
            row["Age"] = str(_get_pr_age_days(pr_detail))
        if checks:
            row["Checks"] = _osc8_to_markdown(
                format_check_status(
                    check_statuses.get(pr_detail["id"], "none"),
                    style=status_style,
                )
            )
        if approvals:
            approval_detail = approval_details.get(pr_detail["id"], {})
            row["Approved"] = _osc8_to_markdown(
                format_approval_status(
                    approval_statuses.get(pr_detail["id"], "pending"),
                    style=status_style,
                    current_reviews=approval_detail.get("current"),
                    required_reviews=approval_detail.get("required"),
                )
            )
        if head_branch:
            _hb_name = pr_detail["head"]["ref"]
            _hb_owner = pr_detail["base"]["repo"]["owner"]["login"]
            _hb_repo = pr_detail["base"]["repo"]["name"]
            _hb_url = f"https://github.com/{_hb_owner}/{_hb_repo}/tree/{_hb_name}"
            row["Head Branch"] = f"[{_hb_name}]({_hb_url})"
        if base_branch:
            _bb_name = pr_detail["base"]["ref"]
            _bb_owner = pr_detail["base"]["repo"]["owner"]["login"]
            _bb_repo = pr_detail["base"]["repo"]["name"]
            _bb_url = f"https://github.com/{_bb_owner}/{_bb_repo}/tree/{_bb_name}"
            row["Base Branch"] = f"[{_bb_name}]({_bb_url})"
        row["Mergeable?"] = _osc8_to_markdown(
            format_mergeable_status(
                pr_detail.get("mergeable"),
                pr_detail.get("mergeable_state"),
                style=status_style,
                pr_state=pr_detail.get("state"),
                merged=pr_detail.get("merged", False),
            )
        )
        row["Link"] = f"[PR-{pr_detail['number']}]({pr_detail['html_url']})"
        md_data.append(row)
    click.echo(
        tabulate(
            md_data,
            headers="keys",
            tablefmt="github",
            disable_numparse=True,
        )
    )
    logger.info(
        "render_complete elapsed_ms=%d", int((time.monotonic() - t_render) * 1000)
    )


def render_csv(
    pr_details,
    age,
    checks,
    approvals,
    check_statuses,
    approval_statuses,
    approval_details,
):
    from .logger import logger

    logger.info("render format=csv row_count=%d", len(pr_details))
    t_render = time.monotonic()
    buf = io.StringIO()
    fieldnames = [
        "repo",
        "pr_number",
        "title",
        "author",
        "url",
        "state",
        "draft",
        "created_at",
        "updated_at",
        "additions",
        "deletions",
        "changed_files",
        "commits",
        "review_comments",
        "labels",
        "requested_reviewers",
    ]
    if age:
        fieldnames.append("age_days")
    if checks:
        fieldnames.append("checks")
    if approvals:
        fieldnames.append("approval")
        fieldnames.append("approval_current")
        fieldnames.append("approval_required")
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for pr_detail in pr_details:
        row = {
            "repo": pr_detail["base"]["repo"]["name"],
            "pr_number": pr_detail["number"],
            "title": pr_detail["title"],
            "author": pr_detail["user"]["login"],
            "url": pr_detail["html_url"],
            "state": pr_detail["state"],
            "draft": pr_detail.get("draft", False),
            "created_at": pr_detail.get("created_at", ""),
            "updated_at": pr_detail.get("updated_at", ""),
            "additions": pr_detail.get("additions", ""),
            "deletions": pr_detail.get("deletions", ""),
            "changed_files": pr_detail.get("changed_files", ""),
            "commits": pr_detail.get("commits", ""),
            "review_comments": pr_detail.get("review_comments", ""),
            "labels": "|".join(lb["name"] for lb in pr_detail.get("labels", [])),
            "requested_reviewers": "|".join(
                r["login"] for r in pr_detail.get("requested_reviewers", [])
            ),
        }
        if age:
            row["age_days"] = _get_pr_age_days(pr_detail)
        if checks:
            row["checks"] = check_statuses.get(pr_detail["id"], "none")
        if approvals:
            approval_detail = approval_details.get(pr_detail["id"], {})
            row["approval"] = approval_statuses.get(pr_detail["id"], "pending")
            row["approval_current"] = approval_detail.get("current", "")
            row["approval_required"] = approval_detail.get("required", "")
        writer.writerow(row)
    click.echo(buf.getvalue(), nl=False)
    logger.info(
        "render_complete elapsed_ms=%d", int((time.monotonic() - t_render) * 1000)
    )


def render_template(pr_details, template_str, colour):
    from .logger import logger

    logger.info("render format=template row_count=%d", len(pr_details))
    t_render = time.monotonic()
    if not template_str:
        click.echo(
            click.style(
                "Error: --template is required when using --format template.",
                fg="red",
                bold=True,
            ),
            err=True,
            color=colour,
        )
        sys.exit(1)
    for pr_detail in pr_details:
        fields = {
            "repo": pr_detail["base"]["repo"]["name"],
            "title": pr_detail.get("title", ""),
            "author": pr_detail.get("user", {}).get("login", ""),
            "url": pr_detail.get("html_url", ""),
            "state": pr_detail.get("state", ""),
            "number": pr_detail.get("number", ""),
            "created_at": pr_detail.get("created_at", ""),
            "updated_at": pr_detail.get("updated_at", ""),
            "additions": pr_detail.get("additions", 0),
            "deletions": pr_detail.get("deletions", 0),
            "changed_files": pr_detail.get("changed_files", 0),
            "commits": pr_detail.get("commits", 0),
            "review_comments": pr_detail.get("review_comments", 0),
            "labels": "|".join(lb["name"] for lb in pr_detail.get("labels", [])),
            "requested_reviewers": "|".join(
                r["login"] for r in pr_detail.get("requested_reviewers", [])
            ),
        }
        try:
            click.echo(template_str.format_map(fields))
        except KeyError as e:
            click.echo(
                click.style(
                    f"Error: unknown template field {e}. "
                    "See --help for available fields.",
                    fg="red",
                    bold=True,
                ),
                err=True,
                color=colour,
            )
            sys.exit(1)
    logger.info(
        "render_complete elapsed_ms=%d", int((time.monotonic() - t_render) * 1000)
    )


def render_table(
    pr_details,
    organizations,
    legendary,
    age,
    checks,
    approvals,
    check_statuses,
    approval_statuses,
    approval_details,
    head_branch,
    base_branch,
    status_style,
    seasonal_calendar,
    colour,
    colour_index,
    max_title_length,
    column_specs,
    stdout_is_tty=None,
):
    from .logger import logger

    if stdout_is_tty is None:
        stdout_is_tty = sys.stdout.isatty()

    logger.info("render format=table row_count=%d", len(pr_details))
    t_render = time.monotonic()
    pr_data = []
    colored_indices = []
    for idx, pr_detail in enumerate(pr_details):
        adds = click.style(
            "+" + str(pr_detail.get("additions", 0)), fg="green", bold=True
        )
        subs = click.style(
            "-" + str(pr_detail.get("deletions", 0)), fg="red", bold=True
        )

        state_label = format_pr_state(pr_detail["state"], pr_detail.get("draft", False))
        if legendary and is_legendary(pr_detail):
            state_label = state_label + " " + _LEGENDARY_EMOJI

        repo = pr_detail["base"]["repo"]
        repo_url = repo.get("html_url") or pr_detail["html_url"].split("/pull/")[0]
        author = pr_detail["user"]
        author_url = author.get("html_url") or f"https://github.com/{author['login']}"
        pr_num = pr_detail["number"]
        _pr_url_parts = pr_detail["html_url"].split("/")
        org_name = repo.get("owner", {}).get("login") or _pr_url_parts[3]
        org_url = f"https://github.com/{org_name}"

        def _seasonal_colour(text: str) -> str:
            if seasonal_calendar != "off" and colour:
                return apply_seasonal_colour(text, pr_num, calendar=seasonal_calendar)
            return text

        def _seasonal_colour_link(url: str, text: str) -> str:
            if seasonal_calendar != "off" and colour:
                return _styled_hyperlink(
                    url, apply_seasonal_colour(text, pr_num, calendar=seasonal_calendar)
                )
            return generate_terminal_url_anchor(url, text)

        row = {}
        if len(organizations) > 1:
            row["Org"] = _seasonal_colour_link(org_url, org_name)
        row["Repo"] = _seasonal_colour_link(repo_url, repo["name"])
        row["PR Title"] = _seasonal_colour(pr_detail["title"])
        row["Author"] = _seasonal_colour_link(author_url, author["login"])
        row["State"] = state_label
        row["Files"] = click_colour_grade_number(pr_detail["changed_files"])
        row["Commits"] = click_colour_grade_number(pr_detail["commits"])
        row["+/-"] = _seasonal_colour(f"{adds}/{subs}")
        row["Comments"] = click_colour_grade_number(pr_detail["review_comments"])
        if age:
            row["Age"] = click_colour_grade_number(_get_pr_age_days(pr_detail))
        if checks:
            row["Checks"] = _styled_hyperlink(
                f"{pr_detail['html_url']}/checks",
                format_check_status(
                    check_statuses.get(pr_detail["id"], "none"),
                    style=status_style,
                ),
            )
        if approvals:
            approval_detail = approval_details.get(pr_detail["id"], {})
            row["Approved"] = format_approval_status(
                approval_statuses.get(pr_detail["id"], "pending"),
                style=status_style,
                current_reviews=approval_detail.get("current"),
                required_reviews=approval_detail.get("required"),
            )
        if head_branch:
            _hb_name = pr_detail["head"]["ref"]
            _hb_owner = pr_detail["base"]["repo"]["owner"]["login"]
            _hb_repo = pr_detail["base"]["repo"]["name"]
            _hb_url = f"https://github.com/{_hb_owner}/{_hb_repo}/tree/{_hb_name}"
            row["Head Branch"] = _seasonal_colour_link(_hb_url, _hb_name)
        if base_branch:
            _bb_name = pr_detail["base"]["ref"]
            _bb_owner = pr_detail["base"]["repo"]["owner"]["login"]
            _bb_repo = pr_detail["base"]["repo"]["name"]
            _bb_url = f"https://github.com/{_bb_owner}/{_bb_repo}/tree/{_bb_name}"
            row["Base Branch"] = _seasonal_colour_link(_bb_url, _bb_name)
        row["Mergeable?"] = format_mergeable_status(
            pr_detail.get("mergeable"),
            pr_detail.get("mergeable_state"),
            style=status_style,
            pr_state=pr_detail.get("state"),
            merged=pr_detail.get("merged", False),
        )
        row["Link"] = _seasonal_colour_link(
            pr_detail["html_url"], f"PR-{pr_detail['number']}"
        )
        colored_indices.append(_seasonal_colour(str(idx)) if colour_index else str(idx))
        pr_data.append(row)

    # Apply explicit title truncation, then auto-fit to terminal if interactive
    if max_title_length and pr_data and "PR Title" in pr_data[0]:
        pr_data = [
            {
                **row,
                "PR Title": _truncate_formatted_text(row["PR Title"], max_title_length),
            }
            for row in pr_data
        ]
    if stdout_is_tty and pr_data:
        terminal_width = shutil.get_terminal_size().columns
        pr_data = _auto_fit(pr_data, terminal_width, max_title_length)

    colalign = None
    if column_specs:
        pr_data, colalign = _apply_column_specs(
            pr_data, column_specs, len(organizations) > 1
        )

    click.echo(
        tabulate(
            pr_data,
            headers="keys",
            showindex=colored_indices,
            tablefmt="outline",
            disable_numparse=True,
            **({"colalign": colalign} if colalign else {}),
        ),
        color=stdout_is_tty and colour,
    )

    logger.info(
        "render_complete elapsed_ms=%d", int((time.monotonic() - t_render) * 1000)
    )
