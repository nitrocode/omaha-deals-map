#!/usr/bin/env python3
"""One-off OSM enrichment pass: for venues that we've placed on the map but
have no website link, query Nominatim's extratags and persist `website` and
`addr:street/city/postcode` if OSM knows them.

Inputs:  data/deals.json (read-only)
Outputs: data/osm_enrichment_cache.yaml  -- slug -> {website, addr_*}

The pipeline merges this in _build_main as a fallback when the source-
supplied website is empty. Nominatim's usage policy asks for ~1 req/sec
from a single client, so the script sleeps between calls.

Run:
    .venv/bin/python scripts/oneoff/enrich_osm.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts._lib.io import read_yaml, write_yaml
from scripts._lib.photo_finder import fetch_extratags

DEALS = ROOT / "data" / "deals.json"
CACHE = ROOT / "data" / "osm_enrichment_cache.yaml"
KEEP_TAGS = {"website", "addr:street", "addr:city", "addr:postcode", "addr:housenumber"}


def _venues_needing_enrichment(deals: dict, cache: dict) -> list[dict]:
    pending = []
    for r in deals.get("restaurants", []):
        if r.get("website"):
            continue
        if r.get("lat") is None or r.get("lng") is None:
            continue
        if r["id"] in cache:
            continue
        pending.append({"id": r["id"], "name": r["name"],
                        "lat": r["lat"], "lng": r["lng"]})
    return pending


def _harvest(extratags: dict) -> dict:
    out = {}
    for k in KEEP_TAGS:
        v = extratags.get(k)
        if v:
            out[k.replace(":", "_")] = v
    return out


def main(limit: int | None = None, sleep_s: float = 1.1) -> int:
    if not DEALS.exists():
        print(f"[enrich_osm] {DEALS} not found, run `make build` first", file=sys.stderr)
        return 1
    deals = json.loads(DEALS.read_text())
    cache = read_yaml(CACHE, default={}) or {}
    pending = _venues_needing_enrichment(deals, cache)
    if limit:
        pending = pending[:limit]
    print(f"[enrich_osm] {len(pending)} venues to query (cache has {len(cache)})")
    if not pending:
        return 0

    sess = requests.Session()
    hits = 0
    for i, v in enumerate(pending, 1):
        try:
            tags = fetch_extratags(v["name"], v["lat"], v["lng"], session=sess)
        except Exception as e:
            print(f"  [{i}/{len(pending)}] {v['name']!r}: error {e}", file=sys.stderr)
            cache[v["id"]] = {"_error": str(e)[:120]}
            time.sleep(sleep_s)
            continue
        harvested = _harvest(tags or {})
        cache[v["id"]] = harvested or {"_empty": True}
        if "website" in harvested:
            hits += 1
            print(f"  [{i}/{len(pending)}] {v['name']!r}: website -> {harvested['website']}")
        if i % 20 == 0:
            # Periodic flush so a crash doesn't lose progress.
            write_yaml(CACHE, cache)
        time.sleep(sleep_s)

    write_yaml(CACHE, cache)
    print(f"[enrich_osm] done. {hits} new website(s) found across {len(pending)} venues")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="max venues to query this run (resumable via cache)")
    ap.add_argument("--sleep", type=float, default=1.1,
                    help="seconds between requests (Nominatim asks ~1/s)")
    args = ap.parse_args()
    raise SystemExit(main(limit=args.limit, sleep_s=args.sleep))
