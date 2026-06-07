"""Pipeline stage 4: address + lat/lng via Nominatim (and Mapbox fallback) + override + cache."""
from __future__ import annotations

import argparse
import os
import time
from collections.abc import Callable
from pathlib import Path

import requests

from scripts._lib.io import read_yaml, write_yaml

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MAPBOX_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places"
USER_AGENT = "omaha-deals-map/0.1 (+https://github.com/nitrocode/omaha-deals-map)"
OMAHA_BBOX = (-96.4, 41.0, -95.5, 41.5)  # lng_min, lat_min, lng_max, lat_max
OMAHA_PROXIMITY = (-95.9345, 41.2565)    # downtown for Mapbox proximity bias


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
        "geocode_source": "nominatim",
    }


def _mapbox(name: str, token: str) -> dict | None:
    """Mapbox forward geocoding, restricted to Omaha-area, biased toward downtown."""
    # Build query: restaurant name + Omaha NE
    q = f"{name}, Omaha, NE"
    lng_min, lat_min, lng_max, lat_max = OMAHA_BBOX
    r = requests.get(
        f"{MAPBOX_URL}/{requests.utils.quote(q)}.json",
        params={
            "access_token": token,
            "country": "us",
            "limit": 1,
            "types": "poi,address",
            "bbox": f"{lng_min},{lat_min},{lng_max},{lat_max}",
            "proximity": f"{OMAHA_PROXIMITY[0]},{OMAHA_PROXIMITY[1]}",
        },
        timeout=20,
    )
    r.raise_for_status()
    body = r.json()
    feats = body.get("features", [])
    if not feats:
        return None
    f = feats[0]
    lng, lat = f["geometry"]["coordinates"]
    # Mapbox 'place_type' is a list like ['poi'] or ['address']; treat poi as amenity-equivalent.
    place_types = f.get("place_type", [])
    category = "amenity" if "poi" in place_types else (place_types[0] if place_types else "")
    return {
        "address": f.get("place_name", ""),
        "lat": float(lat),
        "lng": float(lng),
        "category": category,
        "geocode_source": "mapbox",
    }


def _confidence(lat: float, lng: float, category: str) -> str:
    lng_min, lat_min, lng_max, lat_max = OMAHA_BBOX
    in_bbox = lng_min <= lng <= lng_max and lat_min <= lat <= lat_max
    if category in {"amenity", "shop", "leisure", "tourism"} and in_bbox:
        return "high"
    if in_bbox:
        return "medium"
    return "low"


def _chain_geocode(name: str, nominatim_fn, mapbox_fn) -> dict | None:
    """Try Nominatim first; if empty AND mapbox available, fall back to Mapbox."""
    try:
        hit = nominatim_fn(name)
    except Exception as e:
        print(f"[geocode] nominatim {name}: {e}")
        hit = None
    if hit:
        return hit
    if mapbox_fn is None:
        return None
    try:
        return mapbox_fn(name)
    except Exception as e:
        print(f"[geocode] mapbox {name}: {e}")
        return None


def main(geocoder: Callable[[str], dict | None] | None = None) -> int:
    extracted = read_yaml(Path("data/extracted.yaml"), default=[])
    overrides = read_yaml(Path("data/overrides/addresses.yaml"), default={}) or {}
    cache = read_yaml(Path("data/geocode_cache.yaml"), default={}) or {}

    mapbox_token = os.environ.get("MAPBOX_TOKEN") or os.environ.get("MAPBOX_ACCESS_TOKEN")
    mapbox_fn = (lambda n: _mapbox(n, mapbox_token)) if mapbox_token else None
    nominatim_fn = _nominatim
    chain = geocoder or (lambda n: _chain_geocode(n, nominatim_fn, mapbox_fn))

    if mapbox_token:
        print("[geocode] Mapbox fallback enabled")
    else:
        print("[geocode] Mapbox fallback disabled (set MAPBOX_TOKEN to enable)")

    stats = {"override": 0, "source": 0, "cache": 0, "nominatim": 0, "mapbox": 0, "miss": 0}
    out = []
    for rec in extracted:
        rid, name = rec["source_record_id"], rec["name"]
        # 1) Manual override
        if rid in overrides:
            o = overrides[rid]
            rec.update({
                "address": o["address"], "lat": o["lat"], "lng": o["lng"],
                "geocode_confidence": "high", "geocode_source": "override",
            })
            stats["override"] += 1
            rec["needs_review"] = False
            out.append(rec)
            continue
        # 2) Source already had lat/lng (visitomaha sometimes)
        if rec.get("lat") is not None and rec.get("lng") is not None:
            rec["geocode_confidence"] = _confidence(rec["lat"], rec["lng"], "")
            rec["geocode_source"] = "source"
            rec.setdefault("address", "")
            stats["source"] += 1
            out.append(rec)
            continue
        # 3) Cache (keyed by name)
        if name in cache:
            cached = cache[name]
            rec.update({**cached, "geocode_source": cached.get("geocode_source", "cache")})
            stats["cache"] += 1
            out.append(rec)
            continue
        # 4) Live geocode (Nominatim then Mapbox if available)
        hit = chain(name)
        if hit:
            conf = _confidence(hit["lat"], hit["lng"], hit.get("category", ""))
            entry = {**hit, "geocode_confidence": conf}
            cache[name] = entry
            src = hit.get("geocode_source", "nominatim")
            rec.update({**entry, "geocode_source": src})
            stats[src] = stats.get(src, 0) + 1
            rec["needs_review"] = conf == "low"
        else:
            rec["needs_review"] = True
            rec["geocode_confidence"] = "none"
            stats["miss"] += 1
        out.append(rec)

    write_yaml(Path("data/geocoded.yaml"), out)
    write_yaml(Path("data/geocode_cache.yaml"), cache)
    print(f"[geocode] {len(out)} records | by source: {stats}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    raise SystemExit(main())
