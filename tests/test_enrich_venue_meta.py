"""Tests for the venue-meta enrichment one-off CLI."""
from __future__ import annotations

import json

import yaml

from scripts.oneoff import enrich_venue_meta


def _redirect_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(enrich_venue_meta, "DEALS", tmp_path / "data" / "deals.json")
    monkeypatch.setattr(enrich_venue_meta, "CACHE", tmp_path / "data" / "venue_meta_cache.yaml")


def test_venues_to_scrape_filters_correctly():
    deals = {
        "restaurants": [
            {"id": "a", "name": "A", "website": "https://a.example"},
            {"id": "b", "name": "B", "website": None},               # no site
            {"id": "c", "name": "C", "website": "https://c.example"},  # cached
        ]
    }
    cache = {"c": {"socials": {}, "canonical_url": None}}
    pending = enrich_venue_meta._venues_to_scrape(deals, cache)
    assert [v["id"] for v in pending] == ["a"]


def test_main_exits_when_deals_missing(tmp_path, monkeypatch, capsys):
    _redirect_paths(monkeypatch, tmp_path)
    assert enrich_venue_meta.main(limit=None, sleep_s=0) == 1
    assert "not found" in capsys.readouterr().err


def test_main_short_circuits_when_nothing_to_scrape(tmp_path, monkeypatch, capsys):
    _redirect_paths(monkeypatch, tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "deals.json").write_text(json.dumps({"restaurants": []}))
    assert enrich_venue_meta.main(limit=None, sleep_s=0) == 0
    assert "0 venues to scrape" in capsys.readouterr().out


def test_main_persists_socials_and_errors(tmp_path, monkeypatch, capsys):
    _redirect_paths(monkeypatch, tmp_path)
    (tmp_path / "data").mkdir()
    deals = {
        "restaurants": [
            {"id": "good", "name": "Good Cafe", "website": "https://good.example"},
            {"id": "blocked", "name": "Blocked", "website": "https://blocked.example"},
            {"id": "empty", "name": "Empty", "website": "https://empty.example"},
        ]
    }
    (tmp_path / "data" / "deals.json").write_text(json.dumps(deals))

    def fake_fetch(url, *, session=None):
        if "good" in url:
            return {"socials": {"facebook": "https://facebook.com/good"},
                    "canonical_url": "https://good.example/"}
        if "empty" in url:
            return {"socials": {}, "canonical_url": None}
        return None  # blocked: SSRF guard or fetch failure

    monkeypatch.setattr(enrich_venue_meta, "fetch_venue_meta", fake_fetch)
    rc = enrich_venue_meta.main(limit=None, sleep_s=0)
    assert rc == 0
    cache = yaml.safe_load((tmp_path / "data" / "venue_meta_cache.yaml").read_text())
    assert cache["good"]["socials"] == {"facebook": "https://facebook.com/good"}
    assert cache["good"]["canonical_url"] == "https://good.example/"
    assert cache["empty"]["socials"] == {}
    assert "_error" in cache["blocked"]
    assert "socials found on 1/3" in capsys.readouterr().out


def test_main_honors_limit(tmp_path, monkeypatch):
    _redirect_paths(monkeypatch, tmp_path)
    (tmp_path / "data").mkdir()
    deals = {"restaurants": [
        {"id": f"v{i}", "name": f"V{i}", "website": f"https://v{i}.example"}
        for i in range(5)
    ]}
    (tmp_path / "data" / "deals.json").write_text(json.dumps(deals))
    seen = []
    monkeypatch.setattr(enrich_venue_meta, "fetch_venue_meta",
                        lambda url, *, session=None: (seen.append(url),
                                                     {"socials": {}, "canonical_url": None})[1])
    enrich_venue_meta.main(limit=2, sleep_s=0)
    assert len(seen) == 2
