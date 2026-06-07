"""Tests for SourceRecord and shared helpers."""
import pytest

from sources._common import SourceRecord, Window, slugify


def test_slugify_basic():
    assert slugify("Blue Sky Patio") == "blue-sky-patio"


def test_slugify_strips_punctuation_and_entities():
    assert slugify("Addy's Sports Bar & Grill") == "addys-sports-bar-grill"
    assert slugify("72 Table & Tap") == "72-table-tap"


def test_slugify_collapses_whitespace():
    assert slugify("  Hello   World  ") == "hello-world"


def test_source_record_round_trip():
    r = SourceRecord(
        source="growomaha",
        source_record_id="blue-sky-patio",
        source_url="https://example.com/x",
        name="Blue Sky Patio",
        record_modified_at="2026-05-08T16:00:57Z",
        kind="happy_hour",
        raw_text="Mon-Fri 3-6 PM",
        external_link="http://bit.ly/x",
        pre_extracted_windows=[Window(day="mon", start="15:00")],
    )
    d = r.to_dict()
    assert d["source"] == "growomaha"
    assert d["pre_extracted_windows"][0]["day"] == "mon"
    r2 = SourceRecord.from_dict(d)
    assert r2 == r


def test_source_record_rejects_invalid_kind():
    with pytest.raises(ValueError):
        SourceRecord(
            source="x", source_record_id="x", source_url="x", name="x",
            record_modified_at="x", kind="nope", raw_text="",
        )


def test_window_validates_day_and_time_format():
    Window(day="mon", start="15:00", end="18:00")
    with pytest.raises(ValueError):
        Window(day="MON", start="15:00")
    with pytest.raises(ValueError):
        Window(day="mon", start="3pm")
