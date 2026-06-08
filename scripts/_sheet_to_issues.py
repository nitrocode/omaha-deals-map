"""Pure mapping: Google Form response row -> GitHub Issue payload.

Sheet column layout, matching the Omaha Deals Map form questions in order:

    0  Timestamp (auto-filled by Forms)
    1  What are you reporting?       (multiple choice)
    2  Venue name
    3  Venue ID (slug, prefilled from the map when opened from a venue)
    4  Address
    5  Details (free text)
    6  Source URL
    7  Reporter email (optional)

Keeping this module side-effect-free so we can unit-test the row -> issue
mapping without faking out Sheets API or the GitHub REST client.
"""
from __future__ import annotations

LABEL_BY_TYPE = {
    "Fix info for a venue": "fix",
    "Add or update a deal": "deal",
    "Suggest a new source": "source",
    "Venue is closed": "closed",
    "Other": "triage",
}

# Tag every form-driven issue so it's easy to filter in the issues UI and
# distinguish from issues opened directly via the GitHub Issue templates.
COMMON_LABEL = "community-form"


def _cell(row: list, idx: int) -> str:
    """Index into a Forms row defensively. Sheets returns ragged rows (trailing
    blanks are trimmed), so an "optional" cell past the last filled column is
    simply missing rather than empty-string."""
    if idx >= len(row):
        return ""
    value = row[idx]
    return (value or "").strip() if isinstance(value, str) else str(value).strip()


def row_to_issue(row: list) -> dict | None:
    """Return {title, body, labels} for a row, or None to skip an empty row.

    Skips rows where the type, venue, and details are ALL blank (e.g. an
    accidental Tab-Enter in a form, or a Sheet padded with empty rows).
    Everything else gets an issue even if some fields are missing, because
    a partial submission is still worth triaging.
    """
    timestamp = _cell(row, 0)
    submission_type = _cell(row, 1)
    name = _cell(row, 2)
    slug = _cell(row, 3)
    address = _cell(row, 4)
    details = _cell(row, 5)
    source_url = _cell(row, 6)
    email = _cell(row, 7)

    if not submission_type and not name and not details:
        return None

    label = LABEL_BY_TYPE.get(submission_type, "triage")
    labels = [COMMON_LABEL, label]

    name_display = name or "(unnamed)"
    if label == "source":
        # Source nominations are about a URL, not a venue, so put the URL in
        # the title when present; fall back to name otherwise.
        title = f"[source] {source_url or name_display}"
    else:
        title = f"[{label}] {name_display}"

    body_lines = [
        f"_Submitted via the in-app form at `{timestamp or 'unknown time'}`._",
        "",
        f"**Type**: {submission_type or '(not specified)'}",
        f"**Venue**: {name_display}" + (f" (`{slug}`)" if slug else ""),
    ]
    if address:
        body_lines.append(f"**Address**: {address}")
    if source_url:
        body_lines.append(f"**Source URL**: {source_url}")
    if email:
        # Public repo + indexed-by-search issue body would expose the
        # submitter's email to scrapers within hours. The form copy
        # ("only if you want a reply") implies a private channel, so
        # the actual address never gets echoed here. Maintainer reads
        # the linked Sheet (which is not public) to find the email.
        body_lines.append("**Reporter email**: provided (check the form responses sheet)")
    body_lines.extend([
        "",
        "---",
        "",
        details or "_(no details provided)_",
    ])

    return {"title": title, "body": "\n".join(body_lines), "labels": labels}
