"""Tests for visitomaha.parse."""
from sources.visitomaha.fetch import VisitomahaPayload
from sources.visitomaha.parse import parse

SAMPLE = {
    "_id": "abc", "recid": "1628",
    "title": "$3 off Bike Share",
    "description": "Use promo VISITOMA26.",
    "poststart": "2024-01-02T05:00:00.000Z",
    "postend":   "2027-01-01T04:59:59.000Z",
    "updated":   "2026-06-04T12:30:37.643Z",
    "offerlink": "https://heartlandbikeshare.org",
    "url": "/coupon/heartland/1628/",
    "listings": [{"latitude": 41.26, "longitude": -95.93, "title": "Heartland Bike Share"}],
}


def test_parse_emits_special_record():
    p = VisitomahaPayload(records=[SAMPLE], total_count=1, source_url="https://x")
    r = parse(p)[0]
    assert r.kind == "special" and r.source == "visitomaha"
    assert r.source_record_id == "1628"
    assert r.valid_from == "2024-01-02" and r.valid_until == "2027-01-01"
    assert r.lat == 41.26 and r.lng == -95.93
    assert r.name == "Heartland Bike Share"


def test_parse_falls_back_to_title_when_listings_empty():
    rec = {**SAMPLE, "listings": []}
    r = parse(VisitomahaPayload(records=[rec], total_count=1, source_url=""))[0]
    assert r.name == rec["title"]
    assert r.lat is None
