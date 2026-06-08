"""Tests for build stage."""

import json
from pathlib import Path

import yaml

SAMPLE = [
    {
        "source": "growomaha", "source_record_id": "blue-sky", "source_url": "u",
        "name": "Blue Sky Patio", "kind": "happy_hour", "raw_text": "Mon 3-6",
        "record_modified_at": "2026-01-01T00:00:00Z",
        "pre_extracted_windows": [{"day": "mon", "start": "15:00", "end": "18:00",
                                    "type": "happy_hour"}],
        "address": "1 Main", "lat": 41.25, "lng": -95.93,
        "geocode_confidence": "high",
    },
    {
        "source": "visitomaha", "source_record_id": "blue-sky", "source_url": "u2",
        "name": "Blue Sky Patio", "kind": "special", "raw_text": "",
        "record_modified_at": "2026-01-01T00:00:00Z",
        "title": "10% off", "valid_from": "2026-01-01", "valid_until": "2026-12-31",
        "address": "1 Main", "lat": 41.25, "lng": -95.93,
        "geocode_confidence": "high",
    },
]


def test_build_merges_same_restaurant_across_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    Path("site").mkdir()
    with open("data/geocoded.yaml", "w") as f:
        yaml.safe_dump(SAMPLE, f)
    with open("data/overrides/categories.yaml", "w") as f:
        yaml.safe_dump({}, f)

    from scripts import _build_main
    _build_main.main()

    bundle = json.loads(Path("data/deals.json").read_text())
    rests = bundle["restaurants"]
    assert len(rests) == 1
    assert len(rests[0]["deals"]) == 2
    assert {d["kind"] for d in rests[0]["deals"]} == {"happy_hour", "special"}
    assert json.loads(Path("site/data.json").read_text()) == bundle


def test_build_applies_category_overrides(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    Path("site").mkdir()
    with open("data/geocoded.yaml", "w") as f:
        yaml.safe_dump([SAMPLE[0]], f)
    with open("data/overrides/categories.yaml", "w") as f:
        yaml.safe_dump({"blue-sky": {
            "cuisine": ["american"],
            "neighborhood": "Aksarben",
            "price_tier": "$$",
        }}, f)
    from scripts import _build_main
    _build_main.main()
    bundle = json.loads(Path("data/deals.json").read_text())
    r = bundle["restaurants"][0]
    assert r["cuisine"] == ["american"]
    assert r["neighborhood"] == "Aksarben"
    assert r["price_tier"] == "$$"


def test_build_includes_manual_venues_from_override(tmp_path, monkeypatch):
    """data/overrides/manual_venues.yaml is for venues that aren't in any
    scrape source. They flow into deals.json next to scraped venues."""
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    Path("site").mkdir()
    # Geocoded yaml can be empty; manual venues exist without any scrape.
    with open("data/geocoded.yaml", "w") as f:
        yaml.safe_dump([], f)
    with open("data/overrides/manual_venues.yaml", "w") as f:
        yaml.safe_dump({
            "mom-and-pop": {
                "name": "Mom & Pop",
                "address": "123 Main St, Omaha NE",
                "lat": 41.26, "lng": -95.93,
                "cuisine": ["diner"],
                "neighborhood": "Midtown",
                "price_tier": "$",
                "deals": [{
                    "kind": "special", "source": "manual",
                    "source_url": "https://example.com",
                    "title": "Free pie Wednesday",
                }],
            },
        }, f)
    from scripts import _build_main
    _build_main.main()
    bundle = json.loads(Path("data/deals.json").read_text())
    assert len(bundle["restaurants"]) == 1
    r = bundle["restaurants"][0]
    assert r["id"] == "mom-and-pop"
    assert r["name"] == "Mom & Pop"
    assert r["lat"] == 41.26
    assert r["neighborhood"] == "Midtown"
    assert r["price_tier"] == "$"
    assert r["deals"][0]["title"] == "Free pie Wednesday"
    assert r["needs_review"] is False
    # Source summary should include "manual" as a source.
    assert any(s["name"] == "manual" for s in bundle["sources"])
