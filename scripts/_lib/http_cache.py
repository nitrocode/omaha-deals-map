"""HTTP client that uses ETag / Last-Modified / body-SHA to skip unchanged content."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import requests
import yaml


@dataclass
class CachedResponse:
    status_code: int
    body: bytes
    headers: dict
    changed: bool


class CachedHttpClient:
    USER_AGENT = "omaha-deals-map/0.1 (+https://github.com/nitrocode/omaha-deals-map)"
    TIMEOUT = 30

    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self._session = requests.Session()
        self._session.headers["User-Agent"] = self.USER_AGENT
        self._cache = self._load_cache()

    def _load_cache(self) -> dict:
        if not self.cache_path.exists():
            return {}
        try:
            return yaml.safe_load(self.cache_path.read_text()) or {}
        except yaml.YAMLError:
            # Corrupt cache (e.g., partial write from a prior crash). Start fresh.
            return {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        tmp.write_text(yaml.safe_dump(self._cache, sort_keys=True))
        os.replace(tmp, self.cache_path)

    def get(self, url: str, *, extra_headers: dict | None = None) -> CachedResponse:
        prior = self._cache.get(url, {})
        headers = dict(extra_headers or {})
        if "etag" in prior:
            headers["If-None-Match"] = prior["etag"]
        if "last_modified" in prior:
            headers["If-Modified-Since"] = prior["last_modified"]

        resp = self._session.request("GET", url, headers=headers, timeout=self.TIMEOUT)
        if resp.status_code == 304:
            return CachedResponse(304, b"", dict(resp.headers), changed=False)

        body = resp.content
        body_sha = hashlib.sha256(body).hexdigest()
        changed = body_sha != prior.get("body_sha")

        entry = {"body_sha": body_sha}
        if (etag := resp.headers.get("ETag")):
            entry["etag"] = etag
        if (lm := resp.headers.get("Last-Modified")):
            entry["last_modified"] = lm
        self._cache[url] = entry
        self._save_cache()
        return CachedResponse(resp.status_code, body, dict(resp.headers), changed=changed)
