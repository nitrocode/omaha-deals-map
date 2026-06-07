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


def test_mapbox_called_when_nominatim_misses(monkeypatch):
    """Mapbox should be invoked only when Nominatim returns None."""
    from scripts import _geocode_main

    nominatim_calls = []
    mapbox_calls = []

    def nominatim(name):
        nominatim_calls.append(name)
        return None  # always miss

    def mapbox(name):
        mapbox_calls.append(name)
        return {"address": f"{name} mb", "lat": 41.25, "lng": -95.93,
                "category": "amenity", "geocode_source": "mapbox"}

    result = _geocode_main._chain_geocode("Test", nominatim, mapbox)
    assert nominatim_calls == ["Test"]
    assert mapbox_calls == ["Test"]
    assert result["geocode_source"] == "mapbox"


def test_mapbox_not_called_when_nominatim_hits(monkeypatch):
    from scripts import _geocode_main

    def nominatim(name):
        return {"address": "x", "lat": 41.25, "lng": -95.93,
                "category": "amenity", "geocode_source": "nominatim"}

    mapbox = MagicMock(side_effect=AssertionError("mapbox should not be called"))
    result = _geocode_main._chain_geocode("Test", nominatim, mapbox)
    assert result["geocode_source"] == "nominatim"
    mapbox.assert_not_called()


def test_chain_handles_no_mapbox_fn():
    from scripts import _geocode_main
    result = _geocode_main._chain_geocode("Test", lambda n: None, None)
    assert result is None
