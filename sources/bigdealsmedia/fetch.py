"""bigdealsmedia HTML fetcher (SSR)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scripts._lib.http_cache import CachedHttpClient

_URL = "https://omaha.bigdealsmedia.net/category/restaurants"


@dataclass
class BigDealsPayload:
    html: bytes
    source_url: str
    fetched_at: str


def fetch(client: CachedHttpClient | None = None,
          cache_path: Path | None = None) -> BigDealsPayload:
    if client is None:
        client = CachedHttpClient(cache_path or Path("data/http_cache.yaml"))
    resp = client.get(_URL)
    return BigDealsPayload(
        html=resp.body,
        source_url=_URL,
        fetched_at=datetime.now(UTC).isoformat(),
    )
