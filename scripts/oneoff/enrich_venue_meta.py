#!/usr/bin/env python3
"""One-off venue-meta enrichment: scrape each venue's homepage for
social-media links and canonical URL. Closes the gap where OSM
doesn't carry contact:facebook / contact:instagram tags but the venue
puts those links in its footer.

Reads venues with a known `website` from data/deals.json and stores
results in data/venue_meta_cache.yaml. _build_main merges the socials
into venue.socials (taking precedence over OSM-supplied socials only
if OSM didn't have one, since OSM tags are more deliberate signal).

Run:
    .venv/bin/python scripts/oneoff/enrich_venue_meta.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts._lib.io import read_yaml, write_yaml  # noqa: E402
from scripts._lib.venue_meta import fetch_venue_meta  # noqa: E402

DEALS = ROOT / "data" / "deals.json"
CACHE = ROOT / "data" / "venue_meta_cache.yaml"


def _venues_to_scrape(deals: dict, cache: dict) -> list[dict]:
    """Venues with a website and no cache entry yet. Skipping already-
    cached venues makes the script resumable; rm the cache to refresh."""
    pending = []
    for r in deals.get("restaurants", []):
        if not r.get("website"):
            continue
        if r["id"] in cache:
            continue
        pending.append({"id": r["id"], "name": r["name"], "website": r["website"]})
    return pending


def main(limit: int | None = None, sleep_s: float = 1.0) -> int:
    if not DEALS.exists():
        print(f"[enrich_venue_meta] {DEALS} not found, run `make build` first",
              file=sys.stderr)
        return 1
    deals = json.loads(DEALS.read_text())
    cache = read_yaml(CACHE, default={}) or {}
    pending = _venues_to_scrape(deals, cache)
    if limit:
        pending = pending[:limit]
    print(f"[enrich_venue_meta] {len(pending)} venues to scrape "
          f"(cache has {len(cache)})")
    if not pending:
        return 0

    sess = requests.Session()
    socials_found = 0
    for i, v in enumerate(pending, 1):
        meta = fetch_venue_meta(v["website"], session=sess)
        if meta is None:
            cache[v["id"]] = {"_error": "fetch_failed_or_blocked"}
            print(f"  [{i}/{len(pending)}] {v['name']!r}: blocked or error")
        else:
            cache[v["id"]] = meta
            if meta["socials"]:
                socials_found += 1
                socials_str = ", ".join(meta["socials"].keys())
                print(f"  [{i}/{len(pending)}] {v['name']!r}: {socials_str}")
            else:
                print(f"  [{i}/{len(pending)}] {v['name']!r}: (no socials found)")
        if i % 20 == 0:
            write_yaml(CACHE, cache)  # periodic flush
        time.sleep(sleep_s)

    write_yaml(CACHE, cache)
    print(f"[enrich_venue_meta] done. socials found on {socials_found}/"
          f"{len(pending)} venues")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="seconds between requests (be nice to small business sites)")
    args = ap.parse_args()
    raise SystemExit(main(limit=args.limit, sleep_s=args.sleep))
