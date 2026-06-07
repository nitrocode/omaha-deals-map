"""Tests for geocode stage."""
from pathlib import Path
from unittest.mock import MagicMock

import yaml


def test_geocode_uses_override_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    with open("data/extracted.yaml", "w") as f:
        yaml.safe_dump([{
            "source": "x", "source_record_id": "blue-sky", "kind": "happy_hour",
            "name": "Blue Sky", "source_url": "", "record_modified_at": "",
        }], f)
    with open("data/overrides/addresses.yaml", "w") as f:
        yaml.safe_dump({"blue-sky": {"address": "1 Main St", "lat": 41.0, "lng": -95.0}}, f)

    from scripts import _geocode_main
    _geocode_main.main(geocoder=lambda n: None)
    with open("data/geocoded.yaml") as f:
        out = yaml.safe_load(f)
    assert out[0]["lat"] == 41.0
    assert out[0]["address"] == "1 Main St"


def test_geocode_falls_back_to_geocoder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    with open("data/extracted.yaml", "w") as f:
        yaml.safe_dump([
            {"source": "x", "source_record_id": "a", "kind": "happy_hour",
             "name": "Place A", "source_url": "", "record_modified_at": ""},
            {"source": "x", "source_record_id": "b", "kind": "happy_hour",
             "name": "Place B", "source_url": "", "record_modified_at": ""},
        ], f)

    calls = []
    def geocoder(name):
        calls.append(name)
        return {"address": f"{name} addr", "lat": 41.25, "lng": -95.93,
                "category": "amenity"}

    from scripts import _geocode_main
    _geocode_main.main(geocoder=geocoder)
    assert calls == ["Place A", "Place B"]
    with open("data/geocoded.yaml") as f:
        out = yaml.safe_load(f)
    assert all(r["geocode_confidence"] == "high" for r in out)


def test_chain_falls_through_to_each_geocoder_on_miss():
    """Chain runs in order; later geocoders are only called when earlier ones miss."""
    from scripts import _geocode_main

    calls = []
    def maker(label, hit):
        def fn(name):
            calls.append(label)
            return hit
        return fn

    nominatim = maker("nominatim", None)
    photon = maker("photon", {"address": "x", "lat": 41.25, "lng": -95.93,
                              "category": "amenity", "geocode_source": "photon"})
    result = _geocode_main._chain_geocode("Test", [
        ("nominatim", nominatim), ("photon", photon),
    ])
    assert calls == ["nominatim", "photon"]
    assert result["geocode_source"] == "photon"


def test_chain_short_circuits_on_first_hit():
    from scripts import _geocode_main
    photon = MagicMock(side_effect=AssertionError("photon should not be called"))
    result = _geocode_main._chain_geocode("Test", [
        ("nominatim", lambda n: {"address": "x", "lat": 41.25, "lng": -95.93,
                                  "category": "amenity", "geocode_source": "nominatim"}),
        ("photon", photon),
    ])
    assert result["geocode_source"] == "nominatim"
    photon.assert_not_called()


def test_chain_skips_none_entries():
    """A None fn entry is skipped silently. Kept so future optional geocoders
    can plug in via the same conditional-enable pattern without breaking
    the chain."""
    from scripts import _geocode_main
    result = _geocode_main._chain_geocode("Test", [
        ("nominatim", lambda n: None),
        ("future-optional", None),
    ])
    assert result is None


def test_is_plausible_match_accepts_overlap():
    from scripts._geocode_main import _is_plausible_match
    # Multi-token overlap
    assert _is_plausible_match("Approach at Indian Creek", "The Club at Indian Creek")
    # Exact-ish
    assert _is_plausible_match("Revival House", "Revival House")
    # Short query (no significant tokens) -> accept
    assert _is_plausible_match("A&W", "A&W Burger Stand")


def test_is_plausible_match_rejects_fuzzy_false_positives():
    from scripts._geocode_main import _is_plausible_match
    # Real Photon false positives that hurt our pipeline:
    assert not _is_plausible_match("Nick's Quorum", "Fairfield Inn & Suites Omaha Downtown")
    assert not _is_plausible_match("J's Smokehouse", "US Coast Guard Omaha Moorings")
    assert not _is_plausible_match("Hacienda Real", "Real Look")  # "real" is <5 chars, dropped


def test_chain_continues_past_geocoder_exceptions():
    from scripts import _geocode_main

    def boom(name):
        raise RuntimeError("network down")

    result = _geocode_main._chain_geocode("Test", [
        ("nominatim", boom),
        ("photon", lambda n: {"address": "x", "lat": 41.25, "lng": -95.93,
                              "category": "amenity", "geocode_source": "photon"}),
    ])
    assert result["geocode_source"] == "photon"
