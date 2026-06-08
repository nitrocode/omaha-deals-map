"""Tests for the photos pipeline stage (06)."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts import _photos_main
from scripts._lib.photo_finder import Photo


def _write_bundle(tmp_path: Path, restaurants: list[dict]) -> None:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "deals.json").write_text(json.dumps({"restaurants": restaurants}))


def test_main_returns_1_when_bundle_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert _photos_main.main() == 1
    assert "missing" in capsys.readouterr().out


def test_main_caches_no_coords_as_null_photo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_bundle(tmp_path, [{"id": "noloc", "name": "No Loc", "lat": None, "lng": None}])
    monkeypatch.setattr(_photos_main, "find_photo",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not be called")))
    rc = _photos_main.main()
    assert rc == 0
    cache = yaml.safe_load((tmp_path / "data" / "photo_cache.yaml").read_text())
    assert cache["noloc"] == {"url": None, "source": None, "attribution": None}


def test_main_uses_cache_when_present_and_force_false(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_bundle(tmp_path, [{"id": "cached", "name": "Cached", "lat": 1.0, "lng": 2.0}])
    (tmp_path / "data" / "photo_cache.yaml").write_text(
        yaml.safe_dump({"cached": {"url": "https://old.example/p.jpg",
                                    "source": "osm", "attribution": "x"}})
    )
    calls = []
    monkeypatch.setattr(_photos_main, "find_photo",
        lambda *a, **kw: calls.append(a) or None)
    _photos_main.main(force=False)
    assert calls == []  # cache hit, no fetch


def test_main_records_found_photo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_bundle(tmp_path, [
        {"id": "v1", "name": "V1", "lat": 1.0, "lng": 2.0, "website": "https://v1.example"},
    ])
    monkeypatch.setattr(_photos_main, "find_photo",
        lambda name, lat, lng, *, hint_website=None: Photo(
            url="https://photo.example/x.jpg", source="osm", attribution="OSM"))
    _photos_main.main()
    cache = yaml.safe_load((tmp_path / "data" / "photo_cache.yaml").read_text())
    assert cache["v1"]["url"] == "https://photo.example/x.jpg"
    assert cache["v1"]["source"] == "osm"


def test_main_records_no_photo_for_misses(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_bundle(tmp_path, [{"id": "miss", "name": "M", "lat": 1.0, "lng": 2.0}])
    monkeypatch.setattr(_photos_main, "find_photo",
        lambda *a, **kw: None)
    _photos_main.main()
    cache = yaml.safe_load((tmp_path / "data" / "photo_cache.yaml").read_text())
    assert cache["miss"] == {"url": None, "source": None, "attribution": None}


def test_main_skips_caching_on_error_so_next_run_retries(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_bundle(tmp_path, [{"id": "err", "name": "E", "lat": 1.0, "lng": 2.0}])

    def boom(*a, **kw):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(_photos_main, "find_photo", boom)
    _photos_main.main()
    # No cache file expected, or the venue isn't in it: errors are transient,
    # so the script intentionally doesn't poison the cache.
    cache_path = tmp_path / "data" / "photo_cache.yaml"
    cache = yaml.safe_load(cache_path.read_text()) if cache_path.exists() else {}
    assert "err" not in cache
    assert "ERROR" in capsys.readouterr().out


def test_main_force_revisits_cached_entries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_bundle(tmp_path, [{"id": "v1", "name": "V1", "lat": 1.0, "lng": 2.0}])
    (tmp_path / "data" / "photo_cache.yaml").write_text(
        yaml.safe_dump({"v1": {"url": None, "source": None, "attribution": None}})
    )
    seen = []
    monkeypatch.setattr(_photos_main, "find_photo",
        lambda *a, **kw: seen.append(a) or None)
    _photos_main.main(force=True)
    assert len(seen) == 1
