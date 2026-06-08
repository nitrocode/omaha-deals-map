"""Pipeline stage 5: merge by restaurant identity, apply overrides, emit deals.json."""
from __future__ import annotations

import argparse
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scripts._lib.io import read_yaml, write_json
from scripts._lib.today_html import DAY_KEYS, render_today_html

SITE_BASE_URL = "https://nitrocode.github.io/omaha-deals-map/"

SCHEMA_VERSION = "1.0"


def _merge_key(rec: dict, merges: dict) -> str:
    rid = rec["source_record_id"]
    return merges.get(f"{rec['source']}:{rid}", rid)


def _photo_for(rid: str, photos: dict) -> dict | None:
    """Pull a photo entry from the cache. Negative cache entries (url: null)
    return None so the front-end doesn't render an empty <img>."""
    entry = photos.get(rid)
    if not entry or not entry.get("url"):
        return None
    return {
        "url": entry["url"],
        "source": entry.get("source"),
        "attribution": entry.get("attribution"),
    }


def _deal(rec: dict) -> dict:
    base = {
        "kind": rec["kind"],
        "source": rec["source"],
        "source_url": rec["source_url"],
        "raw_text": rec.get("raw_text", ""),
    }
    if (lk := rec.get("external_link")):
        base["external_link"] = lk
    if rec["kind"] == "happy_hour":
        base["windows"] = rec.get("pre_extracted_windows") or []
        base["highlights"] = rec.get("highlights", [])
    elif rec["kind"] == "special":
        base.update({
            "title": rec.get("title"),
            "description": rec.get("description"),
            "valid_from": rec.get("valid_from"),
            "valid_until": rec.get("valid_until"),
        })
    elif rec["kind"] == "voucher":
        base.update({
            "title": rec.get("title"),
            "original_price": rec.get("original_price"),
            "sale_price": rec.get("sale_price"),
            "savings": rec.get("savings"),
            "category": rec.get("category"),
        })
    return base


def main() -> int:
    geocoded = read_yaml(Path("data/geocoded.yaml"), default=[])
    categories = read_yaml(Path("data/overrides/categories.yaml"), default={}) or {}
    personal = read_yaml(Path("data/overrides/personal.yaml"), default={}) or {}
    merges = read_yaml(Path("data/overrides/merges.yaml"), default={}) or {}
    # Optional: photos discovered by stage 06_photos. Build is the single
    # place that knows the deals.json schema, so the merge lives here.
    photos = read_yaml(Path("data/photo_cache.yaml"), default={}) or {}

    by_id: dict[str, list[dict]] = defaultdict(list)
    for rec in geocoded:
        by_id[_merge_key(rec, merges)].append(rec)

    summary: dict[str, dict] = {}
    restaurants = []
    for rid, recs in sorted(by_id.items()):
        first = recs[0]
        restaurants.append({
            "id": rid,
            "name": first["name"],
            "address": first.get("address", ""),
            "lat": first.get("lat"),
            "lng": first.get("lng"),
            "geocode_confidence": first.get("geocode_confidence", "none"),
            "cuisine": categories.get(rid, {}).get("cuisine", []),
            "neighborhood": categories.get(rid, {}).get("neighborhood"),
            # Price tier: "$" / "$$" / "$$$" / "$$$$" / null. Matches the
            # universal restaurant pricing convention so contributors don't
            # have to learn a new vocabulary.
            "price_tier": categories.get(rid, {}).get("price_tier"),
            "photo": _photo_for(rid, photos),
            "personal": personal.get(rid, {}),
            "deals": [_deal(r) for r in recs],
            "needs_review": any(r.get("needs_review", False) for r in recs),
        })
        for r in recs:
            summary.setdefault(r["source"], {"count": 0})["count"] += 1

    # Manual venues: hand-curated entries that don't come from any scrape
    # source. Keyed by slug. Same shape as the merged-restaurant record so
    # they flow through the rest of the pipeline (and the map UI) the same
    # way as scraped venues. Useful for one-off restaurants the user knows
    # about but no source aggregates.
    manual_venues = read_yaml(Path("data/overrides/manual_venues.yaml"), default={}) or {}
    for rid, entry in manual_venues.items():
        restaurants.append({
            "id": rid,
            "name": entry["name"],
            "address": entry.get("address", ""),
            "lat": entry.get("lat"),
            "lng": entry.get("lng"),
            "geocode_confidence": entry.get("geocode_confidence", "manual"),
            "cuisine": entry.get("cuisine", []),
            "neighborhood": entry.get("neighborhood"),
            "price_tier": entry.get("price_tier"),
            "photo": _photo_for(rid, photos),
            "personal": personal.get(rid, {}),
            "deals": entry.get("deals", []),
            "needs_review": False,
        })
        summary.setdefault("manual", {"count": 0})["count"] += 1
    # Keep alphabetical order stable.
    restaurants.sort(key=lambda r: r["id"])

    bundle = {
        "schema_version": SCHEMA_VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        "sources": [{"name": k, **v} for k, v in summary.items()],
        "restaurants": restaurants,
    }
    out_path = Path("data/deals.json")
    write_json(out_path, bundle)
    Path("site").mkdir(exist_ok=True)
    shutil.copyfile(out_path, "site/data.json")
    _write_seo_pages(restaurants)
    print(f"[build] {len(restaurants)} restaurants, "
          f"{sum(len(r['deals']) for r in restaurants)} deals")
    print(f"[build] needs_review: {sum(1 for r in restaurants if r['needs_review'])}")
    return 0


def _write_seo_pages(restaurants: list[dict]) -> None:
    """Generate static today.html + per-weekday pages + robots.txt + sitemap.xml.

    Each day gets its own crawlable page so Google can rank "happy hour
    omaha <weekday>" queries against an exact-match URL. today.html is
    a convenience redirect-target so external links don't have to know
    the current weekday.
    """
    site = Path("site")
    now = datetime.now(UTC)
    today_key = DAY_KEYS[(now.weekday() + 1) % 7]  # weekday(): Mon=0; DAY_KEYS: Sun=0

    # Per-weekday pages (sun.html ... sat.html) so each gets its own
    # canonical URL for search.
    for day_key in DAY_KEYS:
        (site / f"{day_key}.html").write_text(
            render_today_html(restaurants, day_key, now=now),
        )

    # today.html mirrors whichever weekday it is, with canonical pointing
    # at the per-day page so search doesn't index two URLs as duplicates.
    today_html = render_today_html(restaurants, today_key, now=now).replace(
        "today.html",
        f"{today_key}.html",
    )
    (site / "today.html").write_text(today_html)

    (site / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: " + SITE_BASE_URL + "sitemap.xml\n",
    )

    sitemap_urls = [SITE_BASE_URL, SITE_BASE_URL + "today.html"]
    sitemap_urls += [SITE_BASE_URL + f"{d}.html" for d in DAY_KEYS]
    lastmod = now.date().isoformat()
    url_xml = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{lastmod}</lastmod></url>"
        for u in sitemap_urls
    )
    (site / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{url_xml}\n"
        "</urlset>\n",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    raise SystemExit(main())
