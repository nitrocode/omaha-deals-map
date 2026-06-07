"""Pipeline stage 5: merge by restaurant identity, apply overrides, emit deals.json."""
from __future__ import annotations

import argparse
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scripts._lib.io import read_yaml, write_json

SCHEMA_VERSION = "1.0"


def _merge_key(rec: dict, merges: dict) -> str:
    rid = rec["source_record_id"]
    return merges.get(f"{rec['source']}:{rid}", rid)


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
            "personal": personal.get(rid, {}),
            "deals": [_deal(r) for r in recs],
            "needs_review": any(r.get("needs_review", False) for r in recs),
        })
        for r in recs:
            summary.setdefault(r["source"], {"count": 0})["count"] += 1

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
    print(f"[build] {len(restaurants)} restaurants, "
          f"{sum(len(r['deals']) for r in restaurants)} deals")
    print(f"[build] needs_review: {sum(1 for r in restaurants if r['needs_review'])}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    raise SystemExit(main())
