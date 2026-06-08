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


def test_build_aggregates_external_link_into_website(tmp_path, monkeypatch):
    """Sources like visitomaha + bigdealsmedia attach the venue's own
    website to each record via external_link. The build aggregates that
    into a venue-level `website` field so the photo finder can use it
    as a fallback when OSM is sparse."""
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    Path("site").mkdir()
    sample = dict(SAMPLE[0])
    sample["external_link"] = "https://example-bar.com"
    with open("data/geocoded.yaml", "w") as f:
        yaml.safe_dump([sample], f)
    from scripts import _build_main
    _build_main.main()
    bundle = json.loads(Path("data/deals.json").read_text())
    assert bundle["restaurants"][0]["website"] == "https://example-bar.com"


def test_build_website_is_none_when_no_source_supplies_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    Path("site").mkdir()
    # SAMPLE[0] has no external_link set.
    with open("data/geocoded.yaml", "w") as f:
        yaml.safe_dump([SAMPLE[0]], f)
    from scripts import _build_main
    _build_main.main()
    bundle = json.loads(Path("data/deals.json").read_text())
    assert bundle["restaurants"][0]["website"] is None


def test_build_uses_osm_enrichment_website_as_fallback(tmp_path, monkeypatch):
    """When sources don't supply a website but the OSM enrichment cache
    has one (from scripts/oneoff/enrich_osm.py), use it."""
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    Path("site").mkdir()
    with open("data/geocoded.yaml", "w") as f:
        yaml.safe_dump([SAMPLE[0]], f)
    with open("data/osm_enrichment_cache.yaml", "w") as f:
        yaml.safe_dump({"blue-sky": {"website": "https://blueskypatio.example"}}, f)
    from scripts import _build_main
    _build_main.main()
    bundle = json.loads(Path("data/deals.json").read_text())
    assert bundle["restaurants"][0]["website"] == "https://blueskypatio.example"


def test_build_source_link_wins_over_osm_enrichment(tmp_path, monkeypatch):
    """When a source provides a website AND OSM does too, prefer the
    source link. Sources often point at a deal landing page; OSM points
    at the homepage; the deal page is more useful when both exist."""
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    Path("site").mkdir()
    sample = dict(SAMPLE[0])
    sample["external_link"] = "https://example-bar.com/happy-hour"
    with open("data/geocoded.yaml", "w") as f:
        yaml.safe_dump([sample], f)
    with open("data/osm_enrichment_cache.yaml", "w") as f:
        yaml.safe_dump({"blue-sky": {"website": "https://example-bar.com"}}, f)
    from scripts import _build_main
    _build_main.main()
    bundle = json.loads(Path("data/deals.json").read_text())
    assert bundle["restaurants"][0]["website"] == "https://example-bar.com/happy-hour"


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


def test_neighborhood_heuristic_picks_known_keyword_from_address():
    from scripts._build_main import _guess_neighborhood
    assert _guess_neighborhood("1020 Howard St, Old Market, Omaha NE") == "Old Market"
    assert _guess_neighborhood("4007 Farnam St, Blackstone, Omaha NE 68131") == "Blackstone"
    assert _guess_neighborhood("123 Main, Council Bluffs IA") == "Council Bluffs"


def test_neighborhood_heuristic_returns_none_when_no_keyword_matches():
    from scripts._build_main import _guess_neighborhood
    assert _guess_neighborhood("1234 Anywhere St, Omaha, NE") is None
    assert _guess_neighborhood("") is None
    assert _guess_neighborhood(None) is None


def test_build_applies_neighborhood_heuristic_when_no_override(tmp_path, monkeypatch):
    """If categories.yaml doesn't set a neighborhood for a venue but the
    address contains a known keyword, the heuristic fills it in."""
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    Path("site").mkdir()
    sample = dict(SAMPLE[0])
    sample["address"] = "1020 Howard St, Old Market, Omaha NE 68102"
    with open("data/geocoded.yaml", "w") as f:
        yaml.safe_dump([sample], f)
    # No categories.yaml -> empty overrides.
    from scripts import _build_main
    _build_main.main()
    bundle = json.loads(Path("data/deals.json").read_text())
    assert bundle["restaurants"][0]["neighborhood"] == "Old Market"


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
