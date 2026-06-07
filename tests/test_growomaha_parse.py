"""Tests for growomaha.parse."""
from sources.growomaha.fetch import GrowomahaPayload
from sources.growomaha.parse import parse

SAMPLE = {
    "id": 12345, "slug": "blue-sky-patio",
    "title": {"rendered": "Blue Sky Patio"},
    "link": "https://growomaha.com/happy-hour/blue-sky-patio/",
    "modified_gmt": "2026-05-08T16:00:57",
    "excerpt": {"rendered": "<p>Monday-Friday from 3-6 PM</p>"},
    "content": {"rendered": "<p>Monday-Friday from 3-6 PM. $5 wells.</p>"},
    "day-of-week": [161, 147, 148, 146, 141],
    "time-slots": [168, 169],
    "cities": [143],
}


def _payload(rec):
    return GrowomahaPayload(
        records=[rec],
        day_of_week={161: "mon", 147: "tue", 148: "wed", 146: "thu",
                     141: "fri", 144: "sat", 145: "sun"},
        time_slots={168: "15:00", 169: "15:30"},
        cities={143: "Omaha"}, features={},
    )


def test_parse_emits_source_record_with_pre_extracted_windows():
    records = parse(_payload(SAMPLE))
    r = records[0]
    assert r.source == "growomaha" and r.source_record_id == "blue-sky-patio"
    assert r.kind == "happy_hour"
    assert r.record_modified_at == "2026-05-08T16:00:57Z"
    starts = {w.day: w.start for w in r.pre_extracted_windows}
    assert starts == {"mon": "15:00", "tue": "15:00", "wed": "15:00",
                      "thu": "15:00", "fri": "15:00"}


def test_parse_strips_html_entities_in_name():
    rec = {**SAMPLE, "title": {"rendered": "Addy&#8217;s Sports Bar"}}
    assert parse(_payload(rec))[0].name == "Addy's Sports Bar"


def test_parse_excerpt_used_as_raw_text():
    assert "Monday-Friday from 3-6 PM" in parse(_payload(SAMPLE))[0].raw_text
