"""Tests for the npdodge oneoff scraper's parsing logic. The Playwright
fetch is integration-only (and runs on a developer's machine, not in CI),
but the HTML -> venue list mapping is testable with synthetic HTML."""
from scripts.oneoff.scrape_npdodge import (
    _slugify,
    parse_venues_from_html,
    to_manual_venue_entry,
)


def test_slugify_matches_common_format():
    assert _slugify("Addy's") == "addys"
    assert _slugify("Mom & Pop") == "mom-pop"
    assert _slugify("  trailing  ") == "trailing"


def test_parser_extracts_bolded_venue_names_from_typical_article_layout():
    """npdodge's blog posts use <strong>VENUE</strong> followed by a
    descriptive paragraph. The parser should grab the name + first 500
    chars of surrounding context as raw_text."""
    html = """
    <html><body><article>
      <h1>Best Happy Hours in Omaha 2026</h1>
      <p><strong>The Boiler Room</strong> - 4-7 PM weekdays, $5 cocktails
         and half off shareables on the Old Market patio.</p>
      <p><strong>Block 16</strong> - 3-6 PM Tue-Fri, $2 off all draught beer.</p>
    </article></body></html>
    """
    venues = parse_venues_from_html(html)
    names = [v["name"] for v in venues]
    assert "The Boiler Room" in names
    assert "Block 16" in names
    boiler = next(v for v in venues if v["name"] == "The Boiler Room")
    assert "$5 cocktails" in boiler["description"]


def test_parser_filters_boilerplate_strong_tags():
    """Section headers and CTAs are commonly bolded too; we drop them
    so they don't pollute the venue list."""
    html = """
    <article>
      <p><strong>HAPPY HOUR</strong></p>
      <p><strong>Click here for more</strong></p>
      <p><strong>Real Bar Name</strong> - actual venue prose here.</p>
    </article>
    """
    venues = parse_venues_from_html(html)
    names = [v["name"] for v in venues]
    assert "Real Bar Name" in names
    assert "HAPPY HOUR" not in names
    assert "Click here for more" not in names


def test_parser_skips_duplicates_and_short_strings():
    html = """
    <article>
      <p><strong>Yo</strong> - too short to be a venue name.</p>
      <p><strong>Same Place</strong> - first mention.</p>
      <p><strong>Same Place</strong> - second mention, should be deduped.</p>
    </article>
    """
    venues = parse_venues_from_html(html)
    names = [v["name"] for v in venues]
    assert names.count("Same Place") == 1
    assert "Yo" not in names


def test_to_manual_venue_entry_produces_yaml_compatible_dict():
    """The output should slot directly into manual_venues.yaml."""
    slug, entry = to_manual_venue_entry({
        "name": "Test Bar",
        "description": "4-7 PM weekdays, $5 wells.",
    })
    assert slug == "test-bar"
    assert entry["name"] == "Test Bar"
    assert entry["lat"] is None
    assert entry["lng"] is None
    assert entry["deals"][0]["kind"] == "happy_hour"
    assert entry["deals"][0]["source"] == "npdodge-2026"
    assert "$5 wells" in entry["deals"][0]["raw_text"]
