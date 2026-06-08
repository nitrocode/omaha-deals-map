"""Tests for the OSM enrichment one-off script."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.oneoff import enrich_osm


def _sample_deals():
    return {
        "restaurants": [
            {
                "id": "with-website",
                "name": "Already Has Website",
                "lat": 41.25, "lng": -95.93,
                "website": "https://has-it.example",
            },
            {
                "id": "no-coords",
                "name": "No Coords Venue",
                "lat": None, "lng": None,
            },
            {
                "id": "needs-enrichment",
                "name": "Needs A Website",
                "lat": 41.26, "lng": -95.94,
                "website": None,
            },
            {
                "id": "already-in-cache",
                "name": "Cached Venue",
                "lat": 41.27, "lng": -95.95,
            },
        ]
    }


def test_venues_needing_enrichment_filters_correctly():
    deals = _sample_deals()
    cache = {"already-in-cache": {"_empty": True}}
    pending = enrich_osm._venues_needing_enrichment(deals, cache)
    # Only the venue that has coords, no website, and isn't cached.
    assert [v["id"] for v in pending] == ["needs-enrichment"]


def test_harvest_keeps_only_whitelisted_keys():
    extratags = {
        "website": "https://example.com",
        "addr:street": "123 Main St",
        "addr:city": "Omaha",
        "addr:postcode": "68102",
        "addr:housenumber": "123",
        "cuisine": "pizza",          # not in KEEP_TAGS, dropped
        "opening_hours": "Mo-Fr",    # not in KEEP_TAGS, dropped
    }
    harvested = enrich_osm._harvest(extratags)
    assert harvested == {
        "website": "https://example.com",
        "addr_street": "123 Main St",
        "addr_city": "Omaha",
        "addr_postcode": "68102",
        "addr_housenumber": "123",
    }


def test_harvest_skips_missing_values():
    assert enrich_osm._harvest({}) == {}
    assert enrich_osm._harvest({"website": ""}) == {}


def _redirect_paths(monkeypatch, tmp_path):
    """Module-level paths are computed at import; redirect them per test."""
    monkeypatch.setattr(enrich_osm, "DEALS", tmp_path / "data" / "deals.json")
    monkeypatch.setattr(enrich_osm, "CACHE", tmp_path / "data" / "osm_enrichment_cache.yaml")


def test_main_exits_when_deals_missing(tmp_path, monkeypatch, capsys):
    _redirect_paths(monkeypatch, tmp_path)
    assert enrich_osm.main(limit=None, sleep_s=0) == 1
    err = capsys.readouterr().err
    assert "not found" in err


def test_main_short_circuits_when_nothing_to_enrich(tmp_path, monkeypatch, capsys):
    _redirect_paths(monkeypatch, tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "deals.json").write_text(json.dumps({"restaurants": []}))
    rc = enrich_osm.main(limit=None, sleep_s=0)
    assert rc == 0
    assert "0 venues to query" in capsys.readouterr().out


def test_main_persists_websites_and_handles_errors(tmp_path, monkeypatch, capsys):
    _redirect_paths(monkeypatch, tmp_path)
    (tmp_path / "data").mkdir()
    deals = {
        "restaurants": [
            {"id": "good", "name": "Good", "lat": 1.0, "lng": 2.0},
            {"id": "bad", "name": "Bad", "lat": 1.0, "lng": 2.0},
            {"id": "empty", "name": "Empty", "lat": 1.0, "lng": 2.0},
        ]
    }
    (tmp_path / "data" / "deals.json").write_text(json.dumps(deals))

    calls: list[tuple[str, float, float]] = []

    def fake_fetch(name, lat, lng, *, session=None):
        calls.append((name, lat, lng))
        if name == "Good":
            return {"website": "https://good.example", "addr:city": "Omaha"}
        if name == "Bad":
            raise RuntimeError("boom")
        return {}  # empty extratags -> _empty sentinel

    monkeypatch.setattr(enrich_osm, "fetch_extratags", fake_fetch)
    # sleep_s=0 keeps the test fast; the real script sleeps ~1.1s/req.
    rc = enrich_osm.main(limit=None, sleep_s=0)
    assert rc == 0
    cache = yaml.safe_load((tmp_path / "data" / "osm_enrichment_cache.yaml").read_text())
    assert cache["good"]["website"] == "https://good.example"
    assert cache["good"]["addr_city"] == "Omaha"
    assert "_error" in cache["bad"]
    assert cache["empty"] == {"_empty": True}
    assert len(calls) == 3
    assert "1 new website(s) found" in capsys.readouterr().out


def test_main_honors_limit(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)
    (tmp_path / "data").mkdir()
    deals = {
        "restaurants": [
            {"id": f"v{i}", "name": f"V{i}", "lat": 1.0, "lng": 2.0}
            for i in range(5)
        ]
    }
    (tmp_path / "data" / "deals.json").write_text(json.dumps(deals))
    seen: list[str] = []

    def fake_fetch(name, lat, lng, *, session=None):
        seen.append(name)
        return {}

    monkeypatch.setattr(enrich_osm, "fetch_extratags", fake_fetch)
    enrich_osm.main(limit=2, sleep_s=0)
    assert len(seen) == 2
