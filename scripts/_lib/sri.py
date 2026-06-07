"""Subresource Integrity (SRI) hash parsing and verification.

Used by `scripts/check_sri.py` (pre-commit + CI gate) and by the unit tests.
Parses every `<link>` and `<script>` tag in an HTML doc that has an `integrity`
attribute and a remote `href`/`src`, then verifies the declared hash matches
the actual content the CDN serves.
"""
from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

ALGO_RE = re.compile(r"^(sha256|sha384|sha512)-([A-Za-z0-9+/=]+)$")
VALID_ALGOS = {"sha256", "sha384", "sha512"}


@dataclass(frozen=True)
class SriRef:
    """One SRI-tagged subresource reference parsed out of an HTML doc."""
    tag: str        # "link" or "script"
    url: str        # absolute remote URL (http/https)
    algo: str       # "sha256" / "sha384" / "sha512"
    hash_b64: str   # the declared hash (base64, no algo prefix)


def parse_sri_tags(html: str) -> list[SriRef]:
    """Return every SRI-tagged remote subresource in the HTML doc.

    Skips: tags without `integrity`, tags without a remote URL, local paths
    (./, /, no scheme), and integrity tokens with an unknown algorithm.
    """
    soup = BeautifulSoup(html, "html.parser")
    refs: list[SriRef] = []
    for el in soup.find_all(["link", "script"]):
        integrity = el.get("integrity")
        url = el.get("href") or el.get("src")
        if not integrity or not url:
            continue
        if not url.startswith(("http://", "https://")):
            continue
        # `integrity` may contain multiple space-separated hashes (the browser
        # accepts the first that matches). Emit one SriRef per recognized token.
        for token in integrity.split():
            m = ALGO_RE.match(token.strip())
            if m:
                refs.append(SriRef(
                    tag=el.name, url=url, algo=m.group(1), hash_b64=m.group(2),
                ))
    return refs


def compute_hash(content: bytes, algo: str) -> str:
    """Return base64-encoded `algo` digest of `content`."""
    if algo not in VALID_ALGOS:
        raise ValueError(f"unsupported algo: {algo!r}")
    digest = hashlib.new(algo, content).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_sri(ref: SriRef, *, fetch=None) -> tuple[bool, str]:
    """Fetch `ref.url`, compute its `ref.algo` hash, return (matches, actual_b64).

    `fetch(url) -> bytes` overrides the default `requests.get` for tests.
    """
    if fetch is None:
        import requests
        resp = requests.get(ref.url, timeout=30)
        resp.raise_for_status()
        content = resp.content
    else:
        content = fetch(ref.url)
    actual = compute_hash(content, ref.algo)
    return (actual == ref.hash_b64, actual)
