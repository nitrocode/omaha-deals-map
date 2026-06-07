"""visitomaha REST API fetcher."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from scripts._lib.http_cache import CachedHttpClient

_QUERY = {
    "filter": {
        "$and": [
            {"categories.categoryid": {"$in": [1, 3, 4, 9, 2, 7]}},
            {"filter_tags": {"$in": ["site_primary"]}},
        ]
    },
    "options": {
        "limit": 100,
        "skip": 0,
        "count": True,
        "sort": {"qualityScore": -1, "title_sort": 1},
    },
}
_TOKEN = "7d890807f6e33bbfee82427523fda90c"
_URL = (
    "https://www.visitomaha.com/includes/rest_v2/plugins_offers_offers/find/"
    f"?json={quote(json.dumps(_QUERY, separators=(',', ':')))}"
    f"&token={_TOKEN}"
)


@dataclass
class VisitomahaPayload:
    records: list[dict]
    total_count: int
    source_url: str


def fetch(
    client: CachedHttpClient | None = None,
    cache_path: Path | None = None,
) -> VisitomahaPayload:
    if client is None:
        client = CachedHttpClient(cache_path or Path("data/http_cache.yaml"))
    resp = client.get(_URL)
    body = json.loads(resp.body)
    docs = body["docs"]
    return VisitomahaPayload(
        records=docs["docs"],
        total_count=docs.get("count", len(docs["docs"])),
        source_url=_URL,
    )
