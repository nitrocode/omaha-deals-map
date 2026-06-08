"""Tests for the today.html SEO page generator. Side-effect-free."""
from datetime import UTC, datetime

import pytest

from scripts._lib.today_html import (
    DAY_KEYS,
    DAY_NAMES,
    _format_time_12h,
    _venue_window_summary,
    render_today_html,
    restaurants_for_day,
)


def _venue(name, day, start, end=None, kind="happy_hour"):
    """Build a minimal restaurant dict for tests."""
    deals = []
    if kind == "happy_hour":
        window = {"day": day, "start": start, "type": "happy_hour"}
        if end:
            window["end"] = end
        deals.append({"kind": "happy_hour", "windows": [window]})
    else:
        deals.append({"kind": kind})
    return {
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "deals": deals,
        "lat": 41.25, "lng": -95.93,
    }


def test_format_time_12h_handles_morning_and_evening():
    assert _format_time_12h("00:00") == "12:00 AM"
    assert _format_time_12h("09:30") == "9:30 AM"
    assert _format_time_12h("12:00") == "12:00 PM"
    assert _format_time_12h("16:00") == "4:00 PM"
    assert _format_time_12h("23:59") == "11:59 PM"
    assert _format_time_12h("") == ""
    assert _format_time_12h("invalid") == ""


def test_window_summary_picks_current_day_only():
    r = _venue("Test", "mon", "16:00", "19:00")
    assert _venue_window_summary(r, "mon") == "4:00 PM-7:00 PM"
    assert _venue_window_summary(r, "tue") == ""


def test_window_summary_marks_reverse_hh():
    r = {
        "deals": [{
            "kind": "happy_hour",
            "windows": [{"day": "fri", "start": "21:00", "end": "23:00",
                         "type": "reverse_hh"}],
        }],
    }
    assert _venue_window_summary(r, "fri") == "9:00 PM-11:00 PM (reverse)"


def test_window_summary_handles_open_ended_window():
    """A window with start but no end is valid (e.g. 'happy hour all evening')."""
    r = {"deals": [{"kind": "happy_hour",
                    "windows": [{"day": "wed", "start": "15:00", "type": "happy_hour"}]}]}
    assert _venue_window_summary(r, "wed") == "3:00 PM"


def test_restaurants_for_day_filters_and_sorts_alphabetically():
    venues = [
        _venue("Zebra Bar", "mon", "16:00", "18:00"),
        _venue("Apple Cafe", "mon", "17:00", "19:00"),
        _venue("Tuesday Only", "tue", "16:00", "18:00"),
    ]
    monday = restaurants_for_day(venues, "mon")
    assert [r["name"] for r in monday] == ["Apple Cafe", "Zebra Bar"]


def test_restaurants_for_day_excludes_specials_and_vouchers():
    """Only happy_hour deals get a weekday window; specials/vouchers don't
    belong on a 'happy hours on Tuesday' page."""
    venues = [
        _venue("HH Place", "tue", "16:00", "18:00"),
        _venue("Special Place", "tue", "16:00", "18:00", kind="special"),
    ]
    assert [r["name"] for r in restaurants_for_day(venues, "tue")] == ["HH Place"]


def test_render_today_html_includes_canonical_title_and_venues():
    venues = [_venue("Cool Bar", "wed", "16:00", "18:00")]
    html = render_today_html(venues, "wed",
                              now=datetime(2026, 6, 10, 12, 0, tzinfo=UTC))
    assert "Omaha Happy Hours Wednesday" in html
    assert "Cool Bar" in html
    assert "4:00 PM-6:00 PM" in html
    assert 'rel="canonical"' in html
    assert "schema.org/Restaurant" in html
    # Schema.org geo block should be present when lat/lng exist.
    assert 'itemprop="latitude"' in html
    assert "41.25" in html


def test_render_today_html_shows_empty_state_when_no_venues():
    html = render_today_html([], "sun",
                              now=datetime(2026, 6, 7, 12, 0, tzinfo=UTC))
    assert "No happy hours on file for Sunday" in html


def test_render_today_html_rejects_invalid_day_key():
    with pytest.raises(ValueError):
        render_today_html([], "funday", now=datetime.now(UTC))


def test_render_today_html_links_to_interactive_map_with_day_param():
    venues = [_venue("Cool Bar", "wed", "16:00", "18:00")]
    html = render_today_html(venues, "wed",
                              now=datetime(2026, 6, 10, 12, 0, tzinfo=UTC))
    assert 'href="index.html?day=wed' in html


def test_render_today_html_escapes_venue_names_for_xss_safety():
    venues = [{
        "id": "evil", "name": "<script>alert(1)</script>",
        "deals": [{"kind": "happy_hour",
                   "windows": [{"day": "mon", "start": "16:00", "end": "18:00"}]}],
        "lat": None, "lng": None,
    }]
    html = render_today_html(venues, "mon",
                              now=datetime(2026, 6, 8, 12, 0, tzinfo=UTC))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_day_keys_and_names_are_aligned():
    assert set(DAY_KEYS) == set(DAY_NAMES.keys())
    assert len(DAY_KEYS) == 7
