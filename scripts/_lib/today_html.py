"""Build the static /today.html SEO landing page from the deals bundle.

The interactive map (index.html) is fully client-side, so Googlebot sees an
empty shell. This module pre-renders today's happy hours as plain HTML
that search engines can index for "happy hour omaha <weekday>" queries.

Kept side-effect-free (returns the HTML string) so the build script owns
the file write and the tests stay fast.
"""
from __future__ import annotations

from datetime import UTC, datetime
from html import escape

# Mirror the JS_DAY constant in site/app.js so day filtering stays in sync.
DAY_KEYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
DAY_NAMES = {
    "sun": "Sunday", "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday",
    "thu": "Thursday", "fri": "Friday", "sat": "Saturday",
}


def _format_time_12h(hhmm: str) -> str:
    if not hhmm or ":" not in hhmm:
        return ""
    h, m = hhmm.split(":", 1)
    h = int(h)
    ampm = "AM" if h < 12 else "PM"
    if h == 0:
        h = 12
    elif h > 12:
        h -= 12
    return f"{h}:{m} {ampm}"


def _venue_window_summary(restaurant: dict, day_key: str) -> str:
    """Return a short '4:00 PM-6:00 PM' (or '4:00 PM') for a venue's happy
    hour on the given day. Empty string if there's no window on this day."""
    for deal in restaurant.get("deals", []):
        if deal.get("kind") != "happy_hour":
            continue
        for window in deal.get("windows", []):
            if window.get("day") != day_key:
                continue
            start = _format_time_12h(window.get("start", ""))
            end = _format_time_12h(window.get("end", ""))
            reverse_tag = " (reverse)" if window.get("type") == "reverse_hh" else ""
            if start and end:
                return f"{start}-{end}{reverse_tag}"
            if start:
                return f"{start}{reverse_tag}"
    return ""


def restaurants_for_day(restaurants: list[dict], day_key: str) -> list[dict]:
    """Filter the bundle's restaurants down to those with a happy-hour
    window on `day_key`, sorted alphabetically for stable output."""
    out = []
    for r in restaurants:
        if _venue_window_summary(r, day_key):
            out.append(r)
    return sorted(out, key=lambda r: (r.get("name") or "").lower())


def render_today_html(restaurants: list[dict], day_key: str, *, now=None) -> str:
    """Return a self-contained HTML page listing today's happy hours.

    Design choices:
      - Inline minimal CSS so the page is fast and works without JS.
      - Schema.org Restaurant markup per venue so Google can render rich
        snippets ("Restaurant in Omaha, open until 7 PM" style cards).
      - Each venue links back to the interactive map with the day
        pre-selected via query string, so a Google visitor who clicks
        through lands on a useful state of the map.
      - No tracking, no analytics, no JS dependencies.
    """
    if day_key not in DAY_NAMES:
        raise ValueError(f"Unknown day_key: {day_key!r}")
    day_name = DAY_NAMES[day_key]
    title = f"Omaha Happy Hours {day_name} | Omaha Deals Map"
    description = (
        f"Restaurants and bars in Omaha, Nebraska with happy hour deals on "
        f"{day_name}. Updated weekly from multiple sources."
    )
    venues = restaurants_for_day(restaurants, day_key)
    venue_count = len(venues)

    now = now or datetime.now(UTC)
    # Date only (no time), so a same-day rebuild with unchanged data produces
    # no diff. Different day = 1-line diff in the footer; acceptable noise.
    built_on = now.date().isoformat()

    def venue_li(r: dict) -> str:
        name = escape(r.get("name") or "Unnamed")
        slug = escape(r.get("id") or "")
        window = _venue_window_summary(r, day_key)
        address = escape(r.get("address") or "")
        neighborhood = escape(r.get("neighborhood") or "")
        lat = r.get("lat")
        lng = r.get("lng")
        # Schema.org Restaurant; only emit fields we actually have so the
        # output is stable when data is sparse.
        ld_addr = f'<meta itemprop="address" content="{address}">' if address else ""
        ld_geo = (
            f'<meta itemprop="latitude" content="{lat}">'
            f'<meta itemprop="longitude" content="{lng}">'
            if lat is not None and lng is not None else ""
        )
        neighborhood_html = (
            f' &middot; <span class="neighborhood">{neighborhood}</span>'
            if neighborhood else ""
        )
        return (
            f'<li class="venue" itemscope itemtype="https://schema.org/Restaurant">'
            f'<a href="index.html?day={day_key}#venue={slug}" itemprop="url">'
            f'<span itemprop="name">{name}</span></a> '
            f'<span class="hours">{escape(window)}</span>'
            f'{neighborhood_html}'
            f'{ld_addr}{ld_geo}'
            f'</li>'
        )

    items_html = "\n".join(venue_li(r) for r in venues) or (
        '<li class="empty">No happy hours on file for ' + escape(day_name) +
        ' yet. The map updates weekly.</li>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
<link rel="canonical" href="https://nitrocode.github.io/omaha-deals-map/today.html">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:type" content="website">
<meta name="theme-color" content="#2c5aa0">
<script defer src="umami.js" data-website-id="8166cd95-14b1-4f03-b872-ebc1d4afc99f"></script>
<style>
body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 48rem;
       margin: 0 auto; padding: 1rem; color: #222; background: #f5f5f5; }}
header {{ background: #2c5aa0; color: #fff; margin: -1rem -1rem 1rem;
         padding: 1rem; }}
header h1 {{ margin: 0; font-size: 1.4rem; }}
header p {{ margin: .25rem 0 0; font-size: .9rem; opacity: .9; }}
.cta {{ display: inline-block; margin: 0 0 1rem; padding: .5rem 1rem;
        background: #2c5aa0; color: #fff; text-decoration: none; border-radius: 4px; }}
ul.venues {{ list-style: none; padding: 0; }}
.venue {{ padding: .65rem .25rem; border-bottom: 1px solid #ddd; }}
.venue a {{ color: #2c5aa0; text-decoration: none; font-weight: 600; }}
.venue a:hover {{ text-decoration: underline; }}
.hours {{ color: #555; font-size: .9rem; }}
.neighborhood {{ color: #888; font-size: .85rem; }}
footer {{ margin-top: 2rem; color: #888; font-size: .8rem; }}
.empty {{ color: #888; font-style: italic; }}
</style>
</head>
<body>
<header>
  <h1>Happy hours in Omaha &middot; {escape(day_name)}</h1>
  <p>{venue_count} venue{'s' if venue_count != 1 else ''} with a happy hour today.</p>
</header>
<a class="cta" href="index.html?day={day_key}">Open the interactive map</a>
<ul class="venues">
{items_html}
</ul>
<footer>
  Updated {escape(built_on)}. Data scraped weekly from growomaha.com,
  visitomaha.com, and omaha.bigdealsmedia.net. See the
  <a href="https://github.com/nitrocode/omaha-deals-map">source on GitHub</a>.
</footer>
</body>
</html>
"""
