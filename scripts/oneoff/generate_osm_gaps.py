"""Generate docs/osm-contribution-list.md: a per-venue checklist of what's
missing from OpenStreetMap so the maintainer can contribute it back.

Classification is inferred from data/photo_cache.yaml (already produced by
the photo scrape). The cache tells us which source supplied the photo (if
any), which is a proxy for what's already in OSM:

  source = "osm"        -> OSM has an image tag (no gap)
  source = "wikidata"   -> OSM has a wikidata tag but no image
  source = "og"         -> OSM has a website tag but no image
  url = null            -> OSM has neither website nor image

The output is grouped by gap class with direct edit links into the OSM iD
editor at each venue's coordinates.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

PHOTO_CACHE_PATH = Path("data/photo_cache.yaml")
DEALS_JSON_PATH = Path("data/deals.json")
OUTPUT_PATH = Path("docs/osm-contribution-list.md")

OSM_EDIT_URL = "https://www.openstreetmap.org/edit?lat={lat}&lon={lng}&zoom=19"


def classify_gap(photo_entry: dict | None) -> str | None:
    """Return one of: None | 'no_osm_image_but_has_wikidata' |
    'no_osm_image_but_has_website' | 'missing_website_and_image'.

    `None` means the venue already has an OSM image tag (no contribution
    needed for the photo path)."""
    if photo_entry is None or not photo_entry.get("url"):
        return "missing_website_and_image"
    source = photo_entry.get("source")
    if source == "osm":
        return None
    if source == "wikidata":
        return "no_osm_image_but_has_wikidata"
    if source == "og":
        return "no_osm_image_but_has_website"
    return "missing_website_and_image"


GAP_LABELS = {
    "no_osm_image_but_has_wikidata": "Has Wikidata tag; needs an OSM image",
    "no_osm_image_but_has_website": "Has website tag; needs an OSM image",
    "missing_website_and_image": "Missing OSM website AND image tags",
}


def main(output: Path = OUTPUT_PATH) -> int:
    if not DEALS_JSON_PATH.exists():
        print("ERROR: data/deals.json missing. Run `make build` first.")
        return 1
    if not PHOTO_CACHE_PATH.exists():
        print("ERROR: data/photo_cache.yaml missing. Run `make photos` first.")
        return 1

    bundle = json.loads(DEALS_JSON_PATH.read_text())
    photo_cache = yaml.safe_load(PHOTO_CACHE_PATH.read_text()) or {}

    buckets: dict[str, list[dict]] = {k: [] for k in GAP_LABELS}
    for r in bundle["restaurants"]:
        gap = classify_gap(photo_cache.get(r["id"]))
        if gap is None:
            continue
        if r.get("lat") is None or r.get("lng") is None:
            continue
        buckets[gap].append(r)

    lines: list[str] = []
    lines.append("# OSM contribution list")
    lines.append("")
    lines.append(
        "Per-venue gaps inferred from the photo scrape "
        "(`data/photo_cache.yaml`). Each entry links to the iD editor at "
        "the venue's coordinates so you can add the missing tag in two clicks."
    )
    lines.append("")
    lines.append(
        "**Why this matters:** every OSM tag you add benefits "
        "every downstream tool, not just this map. The richer the OSM data "
        "for Omaha venues, the more useful the map (and OpenStreetMap "
        "broadly) becomes."
    )
    lines.append("")
    lines.append("Common tags worth filling in:")
    lines.append("- `website` - the venue's own URL")
    lines.append("- `image` - photo of the venue (URL)")
    lines.append("- `phone` - international format, e.g. `+1-402-555-0100`")
    lines.append(
        "- `opening_hours` - using the OSM "
        "[opening_hours](https://wiki.openstreetmap.org/wiki/Key:opening_hours) syntax"
    )
    lines.append("- `cuisine` - one or more of the OSM "
                 "[cuisine](https://wiki.openstreetmap.org/wiki/Key:cuisine) values")
    lines.append("")

    total_gaps = sum(len(v) for v in buckets.values())
    lines.append(f"**Total venues with at least one missing tag: {total_gaps}**")
    lines.append("")

    for gap_key, label in GAP_LABELS.items():
        venues = buckets[gap_key]
        if not venues:
            continue
        lines.append(f"## {label} ({len(venues)})")
        lines.append("")
        for r in sorted(venues, key=lambda x: (x.get("name") or "").lower()):
            lat = r["lat"]
            lng = r["lng"]
            edit_url = OSM_EDIT_URL.format(lat=lat, lng=lng)
            address = r.get("address") or "(no address)"
            lines.append(
                f"- **{r['name']}** at {address}  "
                f"[[edit in OSM]({edit_url})]"
            )
        lines.append("")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines))
    print(f"[osm-gaps] wrote {output} ({total_gaps} venues with gaps)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", type=Path, default=OUTPUT_PATH)
    sys.exit(main(output=ap.parse_args().output))
