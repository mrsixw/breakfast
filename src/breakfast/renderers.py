import csv
import io
import json
import re
import shutil
import string
import sys
import time
import urllib.parse

import click
import wcwidth
from tabulate import tabulate

from .api import get_pr_age_days
from .constants import (
    COLUMN_DISPLAY_NAMES,
    DROPPABLE_COLUMNS,
    LEGENDARY_AGE_THRESHOLD_DAYS,
    LEGENDARY_COMMENT_THRESHOLD,
    LEGENDARY_EMOJI,
)
from .ui import (
    apply_seasonal_colour,
    click_colour_grade_number,
    error_exit,
    format_approval_status,
    format_check_status,
    format_mergeable_status,
    format_pr_state,
    generate_terminal_url_anchor,
)

__all__ = [
    "format_labels",
    "format_reviewers",
    "is_legendary",
    "label_search_url",
    "render_csv",
    "render_json",
    "render_markdown",
    "render_table",
    "render_template",
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
        total_comments >= LEGENDARY_COMMENT_THRESHOLD
        and _get_pr_age_days(pr_detail, now=now) >= LEGENDARY_AGE_THRESHOLD_DAYS
    )


def _strip_ansi(s):
    return _ANSI_RE.sub("", str(s))


_OVERFLOW_LIMIT = 2


def _format_overflow_list(values: list[str], limit: int = _OVERFLOW_LIMIT) -> str:
    """Format a list of strings with +N overflow rule."""
    if not values:
        return "-"
    if len(values) > limit:
        head = ", ".join(values[:limit])
        return f"{head} +{len(values) - limit}"
    return ", ".join(values)


def format_reviewers(
    reviewers_list: list[dict] | None, teams_list: list[dict] | None = None
) -> str:
    """Format requested reviewers and teams with +N overflow rule."""
    logins = [r["login"] for r in (reviewers_list or []) if "login" in r]
    team_slugs = [f"@{t['slug']}" for t in (teams_list or []) if "slug" in t]
    return _format_overflow_list(logins + team_slugs)


def _label_repo_coords(pr_detail):
    """Return (owner, repo) for a PR, falling back to parsing its html_url.

    ``base.repo.owner`` is present on real GitHub payloads but not guaranteed,
    so mirror the org-name fallback used when building the Org column.
    """
    base_repo = pr_detail.get("base", {}).get("repo", {}) or {}
    owner = (base_repo.get("owner") or {}).get("login")
    repo = base_repo.get("name")
    if owner and repo:
        return owner, repo
    parts = str(pr_detail.get("html_url", "")).split("/")
    if len(parts) > 4:
        return owner or parts[3], repo or parts[4]
    return None, None


def label_search_url(owner: str, repo: str, label: str) -> str:
    """Return the GitHub search URL for open PRs in *owner/repo* carrying *label*."""
    query = urllib.parse.quote_plus(f'is:pr is:open label:"{label}"')
    return f"https://github.com/{owner}/{repo}/pulls?q={query}"


def format_labels(
    labels_list: list[dict] | None,
    owner: str | None = None,
    repo: str | None = None,
    style: str = "terminal",
    colourise=None,
) -> str:
    """Format label names with the +N overflow rule.

    With *owner* and *repo* supplied, each label name becomes a link to that
    repo's filtered PR search — an OSC 8 anchor for ``style="terminal"`` or a
    Markdown link for ``style="markdown"``. Without them the names stay plain,
    which is what the CSV, JSON and template renderers want.

    *colourise* optionally styles each label name before it is linked.
    """
    names = [lbl["name"] for lbl in (labels_list or []) if "name" in lbl]
    if not (owner and repo):
        return _format_overflow_list(names)

    def _link(name: str) -> str:
        url = label_search_url(owner, repo, name)
        if style == "markdown":
            return f"[{name}]({url})"
        if colourise is not None:
            # _styled_hyperlink keeps the ANSI outside the anchor, which
            # tabulate's OSC 8 parser requires of link text.
            return _styled_hyperlink(url, colourise(name))
        return generate_terminal_url_anchor(url, name)

    # Overflow is computed on the plain names, then only the survivors are linked.
    shown = names[:_OVERFLOW_LIMIT]
    linked = _format_overflow_list([_link(n) for n in shown])
    if len(names) > _OVERFLOW_LIMIT:
        return f"{linked} +{len(names) - _OVERFLOW_LIMIT}"
    return linked


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


def _truncate_multi_anchor(value, limit):
    """Truncate a cell containing several OSC 8 hyperlinks to *limit* visible cells.

    Walks the cell as alternating unlinked and linked segments, re-emitting each
    with its own URL until the budget runs out, then appends an ellipsis.
    """
    budget = limit - 1  # reserve one cell for the ellipsis
    out = []
    pos = 0
    for match in _OSC8_ANY_RE.finditer(value):
        for text, url in (
            (value[pos : match.start()], None),
            (match.group("text"), match.group("url")),
        ):
            if not text:
                continue

            def _emit(fragment):
                if url is None:
                    return fragment
                return generate_terminal_url_anchor(url, fragment)

            width = _visible_width(text)
            if width <= budget:
                out.append(_emit(text))
                budget -= width
                continue
            kept = _slice_by_width(text, budget)
            if kept:
                out.append(_emit(kept))
            return "".join(out) + "…"
        pos = match.end()

    tail = value[pos:]
    if tail:
        kept = _slice_by_width(_strip_ansi(tail), budget)
        out.append(kept)
    return "".join(out) + "…"


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

    # A cell may hold several hyperlinks (the Labels column links each label
    # separately). Truncate segment by segment so every surviving fragment keeps
    # its own target: the single-anchor path below would otherwise re-emit the
    # whole cell under the first URL and silently drop the rest.
    if len(_OSC8_ANY_RE.findall(str(value))) > 1:
        return _truncate_multi_anchor(str(value), limit)

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

    # 2b. Truncate Reviewers / Labels
    pr_data = _truncate_col(pr_data, "Reviewers", terminal_width, min_len=8)
    if fits():
        return pr_data
    pr_data = _truncate_col(pr_data, "Labels", terminal_width, min_len=8)
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
    for col in DROPPABLE_COLUMNS:
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
    spec_names = {spec["name"] for spec in column_specs}
    optional_mapping = {
        "Age": "age",
        "Checks": "checks",
        "Approved": "approvals",
        "Head Branch": "head-branch",
        "Base Branch": "base-branch",
        "Reviewers": "reviewers",
        "Labels": "labels",
    }
    resolved_specs = list(column_specs)
    for display_key, spec_name in optional_mapping.items():
        if display_key in first and spec_name not in spec_names:
            resolved_specs.append({"name": spec_name, "header": None, "align": None})

    ordered: list[tuple[str, str, str | None]] = []
    for spec in resolved_specs:
        display_key = COLUMN_DISPLAY_NAMES.get(spec["name"])
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
    reviewers=False,
    show_labels=False,
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
        }
        if show_labels:
            entry["labels"] = [lb["name"] for lb in pr_detail.get("labels", [])]
        if reviewers:
            logins = [r["login"] for r in pr_detail.get("requested_reviewers", [])]
            teams = [f"@{t['slug']}" for t in pr_detail.get("requested_teams", [])]
            entry["requested_reviewers"] = logins + teams
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
    reviewers=False,
    show_labels=False,
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
        if reviewers:
            row["Reviewers"] = format_reviewers(
                pr_detail.get("requested_reviewers"),
                pr_detail.get("requested_teams"),
            )
        if show_labels:
            _md_owner, _md_repo = _label_repo_coords(pr_detail)
            row["Labels"] = format_labels(
                pr_detail.get("labels"),
                owner=_md_owner,
                repo=_md_repo,
                style="markdown",
            )
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
    reviewers=False,
    show_labels=False,
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
    ]
    if show_labels:
        fieldnames.append("labels")
    if reviewers:
        fieldnames.append("requested_reviewers")
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
        }
        if show_labels:
            row["labels"] = "|".join(lbl["name"] for lbl in pr_detail.get("labels", []))
        if reviewers:
            logins = [r["login"] for r in pr_detail.get("requested_reviewers", [])]
            teams = [f"@{t['slug']}" for t in pr_detail.get("requested_teams", [])]
            row["requested_reviewers"] = "|".join(logins + teams)
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


def _template_fields(pr_detail):
    """Build the substitution map exposed to --template for one PR."""
    return {
        "repo": pr_detail["base"]["repo"]["name"],
        "title": pr_detail.get("title", ""),
        "author": pr_detail.get("user", {}).get("login", ""),
        "url": pr_detail.get("html_url", ""),
        "state": pr_detail.get("state", ""),
        # 0, not "": a str default would pass the int-typed probe and then
        # crash on "{number:d}" for the one PR that happens to lack a number.
        "number": pr_detail.get("number", 0),
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


# A synthetic PR used to dry-run a template before any row is printed. It is
# deliberately fed through _template_fields rather than hand-listing the field
# names: that keeps the probe's keys *and value types* in lockstep with real
# rows, so a field added above can never be missing here. Types matter as much
# as keys — "{title:d}" is only detectable as invalid when title is a str.
_TEMPLATE_PROBE_PR = {
    "base": {"repo": {"name": "repo"}},
    "title": "title",
    "user": {"login": "author"},
    "html_url": "https://github.com/org/repo/pull/1",
    "state": "open",
    "number": 1,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "additions": 0,
    "deletions": 0,
    "changed_files": 0,
    "commits": 0,
    "review_comments": 0,
    "labels": [],
    "requested_reviewers": [],
}


# Generous ceiling on a template's field width. Real padding is terminal-sized;
# anything past this is a mistake or a hostile config, and the cost is paid in
# allocation before any error can be raised.
_MAX_TEMPLATE_FIELD_WIDTH = 10_000

# Width sits between the optional fill/align/sign/#/0 prefix and an optional
# ,/_ grouping, .precision and type suffix.
_FORMAT_SPEC_WIDTH_RE = re.compile(
    r"^(?:.?[<>=^])?[-+ ]?#?0?(?P<width>\d+)?(?:[,_])?(?:\.\d+)?[bcdeEfFgGnosxX%]?$"
)


def _template_field_width_over_limit(template_str):
    """Return the first field width exceeding the cap, or None.

    A width of 10^15 raises MemoryError — which is not something to catch after
    the fact, since by then the allocation has already been attempted. Worse, a
    width of 10^11 *succeeds*, quietly building a ~100GB string. Both are
    refused here, before format_map ever runs.

    Args:
        template_str: The template to inspect.

    Returns:
        The offending width as an int, or None if every width is acceptable.
    """
    try:
        parsed = list(string.Formatter().parse(template_str))
    except ValueError:
        return None  # Malformed braces; the probe reports that properly.
    for _literal, name, spec, _conv in parsed:
        if name is None or not spec or "{" in spec:
            continue  # No field, no spec, or a nested spec we cannot read statically.
        match = _FORMAT_SPEC_WIDTH_RE.match(spec)
        if not match or not match.group("width"):
            continue
        width = int(match.group("width"))
        if width > _MAX_TEMPLATE_FIELD_WIDTH:
            return width
    return None


def _template_has_positional_fields(template_str):
    """Report whether a template uses positional fields like {} or {0}.

    format_map reports these as a bare "Format string contains positional
    fields" ValueError, which does not tell the user what to do about it.
    Detecting them here earns a message that names the fix.

    Args:
        template_str: The template to inspect.

    Returns:
        True if any replacement field is positional rather than named.
    """
    try:
        parsed = list(string.Formatter().parse(template_str))
    except ValueError:
        return False  # Malformed braces; the probe below reports it properly.
    return any(
        name is not None and (name == "" or name.split(".")[0].split("[")[0].isdigit())
        for _literal, name, _spec, _conv in parsed
    )


def _template_error_message(exc):
    """Turn a str.format_map failure into a message aimed at the user."""
    if isinstance(exc, KeyError):
        return f"Error: unknown template field {exc}. See --help for available fields."
    return f"Error: invalid template syntax: {exc}"


def _fail_template(exc, template_str, colour):
    """Report a template that format_map rejected, and stop.

    Module level rather than a closure over render_template: it is reached
    from both the up-front probe and the per-row loop, and being importable
    means it can be tested directly.

    Args:
        exc: The exception str.format_map raised.
        template_str: The offending template, for the log line.
        colour: Whether to colourise the error output.

    Raises:
        SystemExit: Always.
    """
    from .logger import logger

    logger.error("invalid_template template=%r error=%s", template_str, exc)
    error_exit(_template_error_message(exc), colour)


def render_template(pr_details, template_str, colour):
    from .logger import logger

    logger.info("render format=template row_count=%d", len(pr_details))
    t_render = time.monotonic()
    if not template_str:
        error_exit(
            "Error: --template is required when using --format template.", colour
        )

    # Validate once, before printing anything. Formatting per row and failing
    # part-way would leave a partial result set on stdout for whatever script
    # is consuming it, followed by an error it cannot un-read.
    if _template_has_positional_fields(template_str):
        error_exit(
            "Error: invalid template: positional fields like {0} are not"
            " supported. Use named fields, e.g. {title}."
            " See --help for available fields.",
            colour,
        )
    oversized_width = _template_field_width_over_limit(template_str)
    if oversized_width is not None:
        error_exit(
            f"Error: invalid template: field width {oversized_width} exceeds"
            f" the maximum of {_MAX_TEMPLATE_FIELD_WIDTH}.",
            colour,
        )
    try:
        template_str.format_map(_template_fields(_TEMPLATE_PROBE_PR))
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        _fail_template(exc, template_str, colour)

    for pr_detail in pr_details:
        # Reading the PR apart from formatting it: a gap in GitHub's payload is
        # not a fault in the user's template, and must not be reported as one.
        try:
            fields = _template_fields(pr_detail)
        except (KeyError, TypeError) as exc:
            logger.error("template_field_extraction_failed error=%s", exc)
            error_exit(f"Error: could not read PR data for the template: {exc}", colour)
        try:
            click.echo(template_str.format_map(fields))
        except (KeyError, ValueError, IndexError, TypeError) as exc:
            # The probe above catches malformed templates; this catches a row
            # whose data defeats an otherwise valid one (a null title, say).
            _fail_template(exc, template_str, colour)
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
    reviewers=False,
    show_labels=False,
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
            state_label = state_label + " " + LEGENDARY_EMOJI

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
        if reviewers:
            row["Reviewers"] = _seasonal_colour(
                format_reviewers(
                    pr_detail.get("requested_reviewers"),
                    pr_detail.get("requested_teams"),
                )
            )
        if show_labels:
            _lbl_owner, _lbl_repo = _label_repo_coords(pr_detail)
            row["Labels"] = format_labels(
                pr_detail.get("labels"),
                owner=_lbl_owner,
                repo=_lbl_repo,
                colourise=_seasonal_colour,
            )
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
