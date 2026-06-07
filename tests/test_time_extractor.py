"""Tests for time-window regex extractor."""
import pytest

from scripts._lib.time_extractor import extract_end_time


@pytest.mark.parametrize("text, start, expected_end", [
    ("Monday-Friday from 3-6 PM", "15:00", "18:00"),
    ("Mon-Fri 3 - 6 PM", "15:00", "18:00"),
    ("4-6 PM", "16:00", "18:00"),
    ("from 4:30-6 PM", "16:30", "18:00"),
    ("11AM-5PM", "11:00", "17:00"),
    ("3pm to 6pm", "15:00", "18:00"),
])
def test_extract_end_time_matches_simple_ranges(text, start, expected_end):
    r = extract_end_time(text, start_hint=start)
    assert r.end == expected_end
    assert r.confidence == "high"


def test_extract_end_time_handles_until():
    r = extract_end_time("Happy Hour deals until 7 PM daily", start_hint="15:00")
    assert r.end == "19:00"


def test_extract_end_time_returns_none_when_no_match():
    r = extract_end_time("Daily, see menu for details", start_hint="15:00")
    assert r.end is None
    assert r.confidence == "none"


def test_reverse_hh_detection():
    r = extract_end_time("Reverse HH Friday 9-11 PM", start_hint="21:00")
    assert r.is_reverse is True
    assert r.end == "23:00"
