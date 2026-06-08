"""One-off scrape of npdodge.com's annual "Best Happy Hours in Omaha" blog
post. Run locally, not in CI: npdodge is behind Cloudflare bot protection,
which curl+regex can't bypass but headless Chromium does.

Usage:

    pip install -e ".[oneoff]"
    playwright install chromium      # one-time, ~150MB
    python scripts/oneoff/scrape_npdodge.py

The script appends venues to data/overrides/manual_venues.yaml (skipping
slugs that already exist there). It does NOT geocode; you'll get
lat/lng=null entries that you fix by running one Nominatim query each
(or just leave for the user to triage via the form). The intent is to
seed the venue list, not produce production-ready data.

When npdodge publishes a new guide URL (e.g., "2027 guide"), update
ARTICLE_URL below and re-run. Cheap to do once a year.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ARTICLE_URL = (
    "https://www.npdodge.com/blog/2026/04/"
    "happy-hour-in-omaha-omahas-best-happy-hours-2026-guide/"
)
MANUAL_VENUES_PATH = Path("data/overrides/manual_venues.yaml")
SOURCE_TAG = "npdodge-2026"


def _slugify(name: str) -> str:
    """Same shape as sources/_common.py slugify so manual entries collide
    cleanly with scraped ones if the venue ever appears in a source."""
    s = name.lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def fetch_html_via_playwright(url: str) -> str:
    """Drive headless Chromium to the URL, wait for Cloudflare to clear,
    and return the rendered DOM. Imported lazily so the rest of the repo
    doesn't carry a Playwright dep."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run:")
        print("  pip install -e \".[oneoff]\" && playwright install chromium")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                           "Version/17.0 Safari/605.1.15",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            # Cloudflare's challenge sometimes renders a "Just a moment..."
            # interstitial; wait for the real article to land.
            page.wait_for_selector("article, main, h2", timeout=30000)
            return page.content()
        finally:
            browser.close()


def parse_venues_from_html(html: str) -> list[dict]:
    """Extract venue names + descriptions from the article body.

    The npdodge layout uses bolded venue names (typically <strong>) followed
    by a paragraph describing the happy hour. We grep for the bold runs and
    collect them; this is loose by design since the layout will drift each
    year and we'd rather over-collect for manual review than miss venues.
    """
    # Lazy import: BeautifulSoup is in the main deps already so this is fine.
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    article = soup.find("article") or soup.find("main") or soup
    venues = []
    seen = set()

    # Pattern 1: bolded venue name followed by descriptive text.
    # Capture each <strong> with non-trivial text in the article body.
    for strong in article.find_all("strong"):
        name = strong.get_text(strip=True)
        # Filter out section headers, single-word boilerplate, etc.
        if not name or len(name) < 3 or len(name) > 80:
            continue
        # Skip obvious non-venue strings.
        lower = name.lower()
        if any(skip in lower for skip in [
            "happy hour", "best of", "guide", "click here", "more info",
            "read more", "table of", "follow us",
        ]):
            continue
        if name in seen:
            continue
        seen.add(name)

        # Next sibling paragraph usually has the description.
        desc = ""
        parent = strong.find_parent(["p", "div", "li"])
        if parent:
            desc = parent.get_text(" ", strip=True)
            # Strip the venue name itself from the desc head.
            if desc.startswith(name):
                desc = desc[len(name):].lstrip(" -:")

        venues.append({"name": name, "description": desc[:500]})

    return venues


def to_manual_venue_entry(venue: dict) -> tuple[str, dict]:
    """Convert a {name, description} dict into a manual_venues.yaml entry."""
    slug = _slugify(venue["name"])
    return slug, {
        "name": venue["name"],
        # No address / coords. Maintainer fills these in via Nominatim
        # lookup (or leaves the slug as needs_review until someone does).
        "address": "",
        "lat": None,
        "lng": None,
        "neighborhood": None,
        "price_tier": None,
        "deals": [{
            "kind": "happy_hour",
            "source": SOURCE_TAG,
            "source_url": ARTICLE_URL,
            "raw_text": venue.get("description", ""),
            "windows": [],   # no parsed times; raw_text has the prose
            "highlights": [],
        }],
    }


def merge_into_manual_venues(new_entries: dict) -> tuple[int, int]:
    """Append new entries to manual_venues.yaml. Skips slugs that already
    exist (don't clobber the maintainer's edits). Returns (added, skipped)."""
    existing = yaml.safe_load(MANUAL_VENUES_PATH.read_text()) or {} \
        if MANUAL_VENUES_PATH.exists() else {}
    added = 0
    skipped = 0
    for slug, entry in new_entries.items():
        if slug in existing:
            skipped += 1
            continue
        existing[slug] = entry
        added += 1
    if added:
        MANUAL_VENUES_PATH.write_text(yaml.safe_dump(
            existing, sort_keys=True, allow_unicode=True,
        ))
    return added, skipped


def main() -> int:
    print(f"[npdodge] fetching {ARTICLE_URL}")
    html = fetch_html_via_playwright(ARTICLE_URL)
    print(f"[npdodge] {len(html):,} bytes fetched")

    venues = parse_venues_from_html(html)
    print(f"[npdodge] parsed {len(venues)} candidate venue(s)")
    if not venues:
        print("[npdodge] WARN no venues parsed; selector may have drifted")
        return 1

    entries = dict(to_manual_venue_entry(v) for v in venues)
    added, skipped = merge_into_manual_venues(entries)
    print(f"[npdodge] {added} added, {skipped} already present "
          f"(in data/overrides/manual_venues.yaml)")
    if added:
        print()
        print("Next steps:")
        print("  1. Review the new entries in data/overrides/manual_venues.yaml")
        print("  2. Geocode each (paste address into Nominatim, copy lat/lng)")
        print("  3. Commit with `Refs: omaha-deals-map`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
