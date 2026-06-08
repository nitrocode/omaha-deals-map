"""Pipeline stage 6: discover a photo URL for each venue via OSM, Wikidata,
or the venue's own website og:image. Results cached in data/photo_cache.yaml
(including negative results) so subsequent runs only fetch new venues.

Reads data/deals.json (already merged), writes the same shape back out with
photo fields populated. Runs AFTER _build_main has produced the bundle, so
the photo is the only thing that changes between this stage and the next
build that picks it up.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from scripts._lib.io import read_yaml, write_yaml
from scripts._lib.photo_finder import find_photo

CACHE_PATH = Path("data/photo_cache.yaml")


def main(force: bool = False) -> int:
    import json
    bundle_path = Path("data/deals.json")
    if not bundle_path.exists():
        print("[photos] data/deals.json missing; run 05_build first")
        return 1
    bundle = json.loads(bundle_path.read_text())
    cache = read_yaml(CACHE_PATH, default={}) or {}

    to_check = []
    for r in bundle["restaurants"]:
        slug = r["id"]
        if not force and slug in cache:
            continue
        if r.get("lat") is None or r.get("lng") is None:
            # No coords means we can't safely match a Nominatim result.
            cache[slug] = {"url": None, "source": None, "attribution": None}
            continue
        to_check.append(r)

    print(f"[photos] {len(to_check)} venue(s) to look up "
          f"({len(cache)} already cached)")

    for i, r in enumerate(to_check, 1):
        slug = r["id"]
        try:
            photo = find_photo(r["name"], r["lat"], r["lng"])
        except Exception as e:
            print(f"  [{i}/{len(to_check)}] {slug}: ERROR {e}")
            # Don't cache errors permanently; they may be transient (timeouts,
            # rate limits). Skip without recording so next run retries.
            continue
        if photo is None:
            cache[slug] = {"url": None, "source": None, "attribution": None}
            print(f"  [{i}/{len(to_check)}] {slug}: (no photo)")
        else:
            cache[slug] = asdict(photo)
            print(f"  [{i}/{len(to_check)}] {slug}: {photo.source} "
                  f"-> {photo.url[:80]}")
        # Persist after every venue so a Ctrl-C halfway through doesn't
        # waste the work we've already done.
        write_yaml(CACHE_PATH, cache)

    found = sum(1 for v in cache.values() if v.get("url"))
    print(f"[photos] total: {found}/{len(cache)} venues have a photo")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Re-check every venue, ignoring cached negatives.")
    sys.exit(main(force=ap.parse_args().force))
