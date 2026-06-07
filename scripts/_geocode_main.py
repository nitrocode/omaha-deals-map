"""Pipeline stage 4: address + lat/lng via Nominatim w/ override + cache."""
from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from pathlib import Path

import requests

from scripts._lib.io import read_yaml, write_yaml

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "omaha-deals-map/0.1 (+https://github.com/nitrocode/omaha-deals-map)"
OMAHA_BBOX = (-96.4, 41.0, -95.5, 41.5)


def _nominatim(name: str) -> dict | None:
    time.sleep(1.0)
    r = requests.get(
        NOMINATIM_URL,
        params={
            "q": f"{name}, Omaha, NE", "format": "json", "limit": 1,
            "addressdetails": 1, "countrycodes": "us",
        },
        headers={"User-Agent": USER_AGENT}, timeout=20,
    )
    r.raise_for_status()
    results = r.json()
    if not results:
        return None
    top = results[0]
    return {
        "address": top.get("display_name", ""),
        "lat": float(top["lat"]),
        "lng": float(top["lon"]),
        "category": top.get("class", ""),
    }


def _confidence(lat: float, lng: float, category: str) -> str:
    lng_min, lat_min, lng_max, lat_max = OMAHA_BBOX
    in_bbox = lng_min <= lng <= lng_max and lat_min <= lat <= lat_max
    if category in {"amenity", "shop", "leisure", "tourism"} and in_bbox:
        return "high"
    if in_bbox:
        return "medium"
    return "low"


def main(geocoder: Callable[[str], dict | None] | None = None) -> int:
    extracted = read_yaml(Path("data/extracted.yaml"), default=[])
    overrides = read_yaml(Path("data/overrides/addresses.yaml"), default={}) or {}
    cache = read_yaml(Path("data/geocode_cache.yaml"), default={}) or {}
    geocoder = geocoder or _nominatim

    out = []
    for rec in extracted:
        rid, name = rec["source_record_id"], rec["name"]
        if rid in overrides:
            o = overrides[rid]
            rec.update({
                "address": o["address"], "lat": o["lat"], "lng": o["lng"],
                "geocode_confidence": "high", "geocode_source": "override",
            })
            out.append(rec)
            continue
        if rec.get("lat") is not None and rec.get("lng") is not None:
            rec["geocode_confidence"] = _confidence(rec["lat"], rec["lng"], "")
            rec["geocode_source"] = "source"
            rec.setdefault("address", "")
            out.append(rec)
            continue
        if name in cache:
            rec.update({**cache[name], "geocode_source": "cache"})
            out.append(rec)
            continue
        try:
            hit = geocoder(name)
        except Exception as e:
            print(f"[geocode] {name}: {e}")
            hit = None
        if hit:
            conf = _confidence(hit["lat"], hit["lng"], hit.get("category", ""))
            cache[name] = {**hit, "geocode_confidence": conf}
            rec.update({**hit, "geocode_confidence": conf, "geocode_source": "nominatim"})
            if conf == "low":
                rec["needs_review"] = True
        else:
            rec["needs_review"] = True
            rec["geocode_confidence"] = "none"
        out.append(rec)

    write_yaml(Path("data/geocoded.yaml"), out)
    write_yaml(Path("data/geocode_cache.yaml"), cache)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    raise SystemExit(main())
