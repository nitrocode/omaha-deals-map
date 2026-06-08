"""Tests for the sheet-row to GitHub-issue mapping. Side-effect-free."""
from scripts._sheet_to_issues import LABEL_BY_TYPE, row_to_issue


def _row(**kw) -> list:
    """Build a sheet row from named fields so tests stay readable when the
    column order changes."""
    cells = [
        kw.get("timestamp", ""),
        kw.get("type", ""),
        kw.get("name", ""),
        kw.get("slug", ""),
        kw.get("address", ""),
        kw.get("details", ""),
        kw.get("source_url", ""),
        kw.get("email", ""),
    ]
    return cells


def test_fix_type_yields_fix_label_and_titled_with_venue():
    issue = row_to_issue(_row(
        timestamp="2026-06-08T10:00:00Z",
        type="Fix info for a venue",
        name="Test Bar",
        slug="test-bar",
        address="123 Main St",
        details="Wrong hours, actually 4-7 not 3-6",
        source_url="https://example.com",
        email="user@example.com",
    ))
    assert issue["title"] == "[fix] Test Bar"
    assert set(issue["labels"]) == {"community-form", "fix"}
    assert "Wrong hours" in issue["body"]
    assert "`test-bar`" in issue["body"]
    assert "123 Main St" in issue["body"]


def test_email_is_never_echoed_into_public_issue_body():
    """The repo is public; the form's email field is opt-in ("only if you
    want a reply"). Echoing the actual address into the issue body would
    expose it to search-engine scraping. The maintainer reads the linked
    sheet (not public) to recover the email when responding."""
    issue = row_to_issue(_row(
        type="Fix info for a venue", name="X", details="d",
        email="someone@example.com",
    ))
    body = issue["body"]
    assert "someone@example.com" not in body
    assert "Reporter email" in body
    assert "form responses sheet" in body


def test_no_email_section_when_field_blank():
    issue = row_to_issue(_row(type="Fix info for a venue", name="X", details="d"))
    assert "Reporter email" not in issue["body"]


def test_deal_and_closed_and_other_get_appropriate_labels():
    for type_, expected_label in [
        ("Add or update a deal", "deal"),
        ("Venue is closed", "closed"),
        ("Other", "triage"),
    ]:
        issue = row_to_issue(_row(type=type_, name="X", details="d"))
        assert issue["labels"][-1] == expected_label, type_
        assert issue["title"].startswith(f"[{expected_label}]")


def test_source_type_uses_url_in_title():
    issue = row_to_issue(_row(
        type="Suggest a new source",
        source_url="https://new-deals-site.com",
        details="cool new aggregator",
    ))
    assert issue["title"] == "[source] https://new-deals-site.com"
    assert "source" in issue["labels"]


def test_source_type_falls_back_to_name_when_url_missing():
    issue = row_to_issue(_row(
        type="Suggest a new source",
        name="That site whose name I forget",
        details="check it out",
    ))
    assert issue["title"] == "[source] That site whose name I forget"


def test_unknown_type_defaults_to_triage():
    issue = row_to_issue(_row(type="WEIRDLY UNEXPECTED VALUE", name="X", details="d"))
    assert "triage" in issue["labels"]
    # Sanity check: every recognised type maps to a real label, and the
    # default-to-triage path matches the "Other" mapping.
    assert LABEL_BY_TYPE["Other"] == "triage"


def test_blank_row_returns_none():
    assert row_to_issue([]) is None
    assert row_to_issue(_row()) is None
    assert row_to_issue(_row(timestamp="2026-06-08T10:00:00Z")) is None


def test_ragged_row_with_only_first_few_cells_is_handled():
    """Sheets API returns ragged rows when trailing cells are blank. The
    mapper must default each missing index to empty, not raise IndexError."""
    issue = row_to_issue(["2026-06-08T10:00:00Z", "Fix info for a venue", "Test"])
    assert issue["title"] == "[fix] Test"
    assert "(no details provided)" in issue["body"]


def test_unnamed_venue_falls_back_to_placeholder_title():
    issue = row_to_issue(_row(type="Fix info for a venue", details="something"))
    assert issue["title"] == "[fix] (unnamed)"


def test_non_string_cell_does_not_raise():
    """Sheets sometimes returns numbers as numbers, not strings (e.g. a
    submitter typed only digits into the name field). _cell should coerce."""
    issue = row_to_issue(["t", "Fix info for a venue", 42, "", "", "details"])
    assert issue["title"] == "[fix] 42"


def test_body_omits_optional_lines_when_blank():
    issue = row_to_issue(_row(
        type="Fix info for a venue",
        name="X",
        details="d",
        # no address, no source_url, no email
    ))
    body = issue["body"]
    assert "**Address**" not in body
    assert "**Source URL**" not in body
    assert "**Reporter email**" not in body
