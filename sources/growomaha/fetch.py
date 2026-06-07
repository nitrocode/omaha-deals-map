"""growomaha REST API fetcher."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from scripts._lib.http_cache import CachedHttpClient
from sources.growomaha.taxonomies import parse_day_of_week, parse_time_slots

BASE = "https://growomaha.com/wp-json/wp/v2"
PER_PAGE = 100
# Content-validity retry. urllib3's retry adapter on the HTTP client only
# retries on status codes (429/5xx). Sometimes WP fronts return a HTTP 200
# with an empty body or a Cloudflare interstitial HTML page; json.loads then
# fails. Re-issuing the request after a short pause usually clears it.
JSON_RETRY_ATTEMPTS = 3
JSON_RETRY_BACKOFF = 1.5  # seconds: 1.5, 3, 6 between attempts


@dataclass
class GrowomahaPayload:
    records: list[dict]
    day_of_week: dict[int, str]
    time_slots: dict[int, str]
    cities: dict[int, str]
    features: dict[int, str]


def _get_json(client, url: str, *, sleep_fn=time.sleep):
    """GET a URL expecting JSON. Retry on JSONDecodeError or empty body."""
    last_err: Exception | None = None
    for attempt in range(JSON_RETRY_ATTEMPTS):
        resp = client.get(url)
        body_bytes = resp.body or b""
        try:
            return json.loads(body_bytes)
        except json.JSONDecodeError as e:
            last_err = e
            snippet = body_bytes[:120].decode("utf-8", errors="replace")
            print(f"[growomaha] non-JSON body from {url} "
                  f"(len={len(body_bytes)}, status={resp.status_code}, "
                  f"attempt {attempt + 1}/{JSON_RETRY_ATTEMPTS}): {snippet!r}")
            if attempt < JSON_RETRY_ATTEMPTS - 1:
                sleep_fn(JSON_RETRY_BACKOFF * (2 ** attempt))
    raise RuntimeError(
        f"growomaha returned non-JSON {JSON_RETRY_ATTEMPTS}x for {url}; last: {last_err}"
    )


def _fetch_taxonomy(client, name: str) -> list[dict]:
    return _get_json(client, f"{BASE}/{name}?per_page=100")


def fetch(client: CachedHttpClient | None = None,
          cache_path: Path | None = None) -> GrowomahaPayload:
    if client is None:
        client = CachedHttpClient(cache_path or Path("data/http_cache.yaml"))
    records: list[dict] = []
    page = 1
    while True:
        body = _get_json(client, f"{BASE}/happy-hour?per_page={PER_PAGE}&page={page}")
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
