"""Tests for geocode stage."""
from pathlib import Path

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
