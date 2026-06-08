"""Find a venue photo without any paid API or signup-with-CC.

Tries three sources in order and returns the first hit:

  1. OSM `image` tag, surfaced via Nominatim's extratags. Sparse (~3% of
     POIs) but unambiguous: the OSM contributor literally said "this is
     the venue's image."
  2. Wikidata `P18` (image) claim, looked up via the OSM `wikidata` tag.
     Notable venues only (~1%), but high-quality and CC-licensed.
  3. The venue's own website `<meta property="og:image">`, discovered
     via the OSM `website` tag. ~30% of small businesses set this.

Each lookup writes a row to data/photo_cache.yaml keyed by venue slug,
INCLUDING negative results (url: null). Subsequent runs skip cached
slugs entirely so the script is idempotent and rate-limit friendly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
WIKIDATA_API = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
COMMONS_FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/{name}?width=600"

USER_AGENT = "omaha-deals-map/0.1 (+https://github.com/nitrocode/omaha-deals-map)"
HTTP_TIMEOUT = 20

# Roughly 1 mi (~0.014 deg lat). Used to reject Nominatim matches that
# share a name with our venue but sit somewhere else in town.
COORD_TOLERANCE_DEG = 0.02


@dataclass
class Photo:
    url: str
    source: str  # "osm" | "wikidata" | "og"
    attribution: str


def _haversine_close(a_lat, a_lng, b_lat, b_lng) -> bool:
    """Cheap planar approximation; we just need 'same neighborhood?'"""
    return abs(a_lat - b_lat) <= COORD_TOLERANCE_DEG and \
           abs(a_lng - b_lng) <= COORD_TOLERANCE_DEG


def fetch_extratags(name: str, lat: float, lng: float, *, session=None) -> dict:
    """Re-query Nominatim with extratags=1 to surface website/image/wikidata
    tags for this venue. Returns the extratags dict or {} on miss/mismatch."""
    sess = session or requests
    resp = sess.get(NOMINATIM_URL, params={
        "q": f"{name} Omaha",
        "format": "json",
        "extratags": 1,
        "limit": 1,
    }, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return {}
    hit_lat = float(results[0]["lat"])
    hit_lng = float(results[0]["lon"])
    if not _haversine_close(hit_lat, hit_lng, lat, lng):
        # Name matched something elsewhere in the city; don't trust it.
        return {}
    return results[0].get("extratags") or {}


def fetch_wikidata_image(qid: str, *, session=None) -> str | None:
    """Resolve a Wikidata entity ID to a Commons photo URL via P18."""
    sess = session or requests
    resp = sess.get(WIKIDATA_API.format(qid=qid),
                    headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    entities = resp.json().get("entities", {})
    claims = entities.get(qid, {}).get("claims", {}).get("P18", [])
    if not claims:
        return None
    filename = claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
    if not filename:
        return None
    return COMMONS_FILEPATH.format(name=quote(filename))


def fetch_og_image(url: str, *, session=None) -> str | None:
    """Fetch a URL and return its og:image content, or None."""
    sess = session or requests
    resp = sess.get(url, headers={"User-Agent": USER_AGENT},
                    timeout=HTTP_TIMEOUT, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    meta = soup.find("meta", property="og:image")
    if not meta or not meta.get("content"):
        # Try twitter:image as a fallback.
        meta = soup.find("meta", attrs={"name": "twitter:image"})
        if not meta or not meta.get("content"):
            return None
    src = meta["content"].strip()
    if not src.startswith(("https://", "http://")):
        return None
    # Browser will block mixed-content http:// images on our HTTPS site.
    if src.startswith("http://"):
        https_attempt = "https://" + src[len("http://"):]
        return https_attempt
    return src


def find_photo(name: str, lat: float | None, lng: float | None, *,
               session=None, sleep_fn=time.sleep) -> Photo | None:
    """Try all three sources in order and return the first hit.

    `sleep_fn` is parameterized so tests can swap in a no-op, and so callers
    can swap in a stricter rate-limiter for batch runs. Nominatim's usage
    policy asks for ~1 req/sec from a single client.
    """
    if lat is None or lng is None:
        return None
    extratags = fetch_extratags(name, lat, lng, session=session)
    sleep_fn(1.1)  # be a polite Nominatim citizen

    if (osm_image := extratags.get("image")):
        return Photo(url=osm_image, source="osm",
                     attribution="© OpenStreetMap contributors")

    if (qid := extratags.get("wikidata")):
        try:
            wd_url = fetch_wikidata_image(qid, session=session)
        except Exception:
            wd_url = None
        if wd_url:
            return Photo(url=wd_url, source="wikidata",
                         attribution="Wikimedia Commons")

    if (website := extratags.get("website")):
        try:
            og_url = fetch_og_image(website, session=session)
        except Exception:
            og_url = None
        if og_url:
            return Photo(url=og_url, source="og", attribution=website)

    return None
