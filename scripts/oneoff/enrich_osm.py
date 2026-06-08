#!/usr/bin/env python3
"""One-off OSM enrichment pass: for every venue we've placed on the map,
query Nominatim's extratags and persist the FULL tag dict OSM has on file
(website, addr:*, contact:*, opening_hours, wheelchair, outdoor_seating,
cuisine, ...).

The cache stores everything because Nominatim rate-limits us to ~1 req/sec
and re-querying for newly-interesting fields would be hours of wall time.
The pipeline (_build_main) picks the subset it wants to surface; the rest
sits in the cache, ready for future UX additions.

Inputs:  data/deals.json (read-only)
Outputs: data/osm_enrichment_cache.yaml -- slug -> dict of OSM extratags
         (plus the sentinels _empty / _error for misses)

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

# Imports below the path tweak are intentional: oneoff scripts are run
# directly (not `python -m`), so the package root has to be on sys.path
# before these resolve. ruff E402 flags the order, hence the noqa.
from scripts._lib.io import read_yaml, write_yaml  # noqa: E402
from scripts._lib.photo_finder import fetch_extratags  # noqa: E402

DEALS = ROOT / "data" / "deals.json"
CACHE = ROOT / "data" / "osm_enrichment_cache.yaml"


def _venues_needing_enrichment(deals: dict, cache: dict) -> list[dict]:
    """Venues with coords that we haven't queried yet.

    We query every venue with coords (not just ones missing a website),
    because the cache now stores the full OSM tag dict and feeds many
    UI fields beyond just website. Already-cached venues are skipped;
    use `make refresh-osm` (rm the cache file) if you want a full refresh.
    """
    pending = []
    for r in deals.get("restaurants", []):
        if r.get("lat") is None or r.get("lng") is None:
            continue
        if r["id"] in cache:
            continue
        pending.append({"id": r["id"], "name": r["name"],
                        "lat": r["lat"], "lng": r["lng"]})
    return pending


def _harvest(extratags: dict) -> dict:
    """Pass through every non-empty OSM tag. We intentionally keep colon
    names (e.g. 'contact:facebook') so future readers can match against
    OSM's canonical schema without a key-rename lookup."""
    return {k: v for k, v in (extratags or {}).items() if v}


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
