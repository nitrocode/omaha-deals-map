"""growomaha REST API fetcher."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from scripts._lib.http_cache import CachedHttpClient
from sources.growomaha.taxonomies import parse_day_of_week, parse_time_slots

BASE = "https://growomaha.com/wp-json/wp/v2"
PER_PAGE = 100


@dataclass
class GrowomahaPayload:
    records: list[dict]
    day_of_week: dict[int, str]
    time_slots: dict[int, str]
    cities: dict[int, str]
    features: dict[int, str]


def _fetch_taxonomy(client, name: str) -> list[dict]:
    resp = client.get(f"{BASE}/{name}?per_page=100")
    return json.loads(resp.body)


def fetch(client: CachedHttpClient | None = None,
          cache_path: Path | None = None) -> GrowomahaPayload:
    if client is None:
        client = CachedHttpClient(cache_path or Path("data/http_cache.yaml"))
    records: list[dict] = []
    page = 1
    while True:
        resp = client.get(f"{BASE}/happy-hour?per_page={PER_PAGE}&page={page}")
        try:
            body = json.loads(resp.body)
        except json.JSONDecodeError:
            break
        if not isinstance(body, list) or len(body) == 0:
            break
        records.extend(body)
        if len(body) < PER_PAGE:
            break
        page += 1

    return GrowomahaPayload(
        records=records,
        day_of_week=parse_day_of_week(_fetch_taxonomy(client, "day-of-week")),
        time_slots=parse_time_slots(_fetch_taxonomy(client, "time-slots")),
        cities={r["id"]: r["name"] for r in _fetch_taxonomy(client, "cities")},
        features={r["id"]: r["name"] for r in _fetch_taxonomy(client, "features")},
    )
