"""Scrape a venue's own homepage for social-media links and canonical URL.

Used by scripts/oneoff/enrich_venue_meta.py to fill the gap where OSM
doesn't carry contact:facebook / contact:instagram tags but the venue
puts those links in its footer (the common case for small businesses).

Reuses the SSRF defenses from photo_finder so we don't open the same
class of holes twice: refuse non-public URLs up-front, re-validate every
redirect hop, http -> https only.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scripts._lib.photo_finder import (
    HTTP_TIMEOUT,
    MAX_REDIRECT_HOPS,
    USER_AGENT,
    _is_public_url,
)

# Platforms we extract. Order matters only for documentation; the parser
# returns a dict, so the first hit per platform wins (we de-dupe).
_PLATFORM_PATTERNS = {
    "facebook":  re.compile(r"^https?://(?:www\.|m\.|[a-z]{2}-[a-z]{2}\.)?facebook\.com/", re.I),
    "instagram": re.compile(r"^https?://(?:www\.)?instagram\.com/", re.I),
    "twitter":   re.compile(r"^https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/", re.I),
    "tiktok":    re.compile(r"^https?://(?:www\.)?tiktok\.com/", re.I),
    "youtube":   re.compile(r"^https?://(?:www\.)?youtube\.com/", re.I),
    "threads":   re.compile(r"^https?://(?:www\.)?threads\.net/", re.I),
}

# Reject "share this page" links (which point at the social network with
# the venue's URL as a query param); we only want the venue's OWN page.
_SHARE_HINTS = re.compile(r"(?:sharer|share|intent/tweet|/share[?/])", re.I)


def _normalize_social_url(url: str) -> str | None:
    """Strip query strings / fragments and trailing slashes so the same
    profile linked twice on the page de-dupes to one entry."""
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    path = parsed.path.rstrip("/")
    if not path or path == "":
        return None  # bare domain links aren't useful (e.g. "facebook.com")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def find_socials(html: str) -> dict[str, str]:
    """Parse HTML and return discovered {platform: clean_url} links.

    Returns empty dict on no matches. First match per platform wins;
    share-this-page links are skipped. Pure function for testability.
    """
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if _SHARE_HINTS.search(href):
            continue
        for platform, pattern in _PLATFORM_PATTERNS.items():
            if platform in out:
                continue
            if pattern.match(href):
                cleaned = _normalize_social_url(href)
                if cleaned:
                    out[platform] = cleaned
                break
    return out


def find_canonical_url(html: str) -> str | None:
    """Return <link rel="canonical"> or <meta property="og:url">, in that
    order. Useful when OSM's website tag points at a redirect-only page
    and we'd rather store the real homepage."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        href = link["href"].strip()
        if href.startswith(("http://", "https://")):
            return href
    meta = soup.find("meta", property="og:url")
    if meta and meta.get("content"):
        content = meta["content"].strip()
        if content.startswith(("http://", "https://")):
            return content
    return None


def fetch_venue_meta(url: str, *, session=None) -> dict | None:
    """Fetch a venue website and extract socials + canonical URL.

    Returns {"socials": {...}, "canonical_url": ...} on success, or None
    if the URL is blocked / unreachable / non-HTML. The dict may have an
    empty socials map and a null canonical_url; the caller decides what
    to do with partial results.
    """
    if not _is_public_url(url):
        return None
    sess = session or requests
    current_url = url
    resp = None
    for _ in range(MAX_REDIRECT_HOPS + 1):
        try:
            resp = sess.get(current_url, headers={"User-Agent": USER_AGENT},
                            timeout=HTTP_TIMEOUT, allow_redirects=False)
        except requests.RequestException:
            return None
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            if not location or not _is_public_url(location):
                return None
            current_url = location
            continue
        if resp.status_code >= 400:
            return None
        break
    else:
        return None
    # Some venue homepages return PDF, JSON, etc. Bail on non-HTML.
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "html" not in ctype and "xml" not in ctype:
        return None
    html = resp.text
    return {
        "socials": find_socials(html),
        "canonical_url": find_canonical_url(html),
    }
