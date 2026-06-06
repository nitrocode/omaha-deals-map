# Omaha Deals Map, Design Spec

**Status:** Draft, pending user review
**Date:** 2026-06-06
**Owner:** REDACTED (personal project)

## Goal

A mobile-first map that shows Omaha-area restaurant deals (happy hours, date-range specials, vouchers) on a per-day basis, sourced from multiple websites that the user can rescrape on demand and enhance with personal metadata (cuisine, neighborhood, tags, ratings, notes).

## Non-goals (v1)

- Public-facing service for other users
- User accounts, sharing, social features
- Real-time deal updates (weekly rescrape is enough)
- Crawling sources that require auth (Reddit OAuth is deferred to v2)
- Yelp / Google Maps deal data (TOS + low signal-to-noise)

## Architecture overview

A static site on GitHub Pages backed by a multi-stage Python pipeline that fetches, parses, enriches, and serializes a single JSON bundle the site consumes.

```
sources (3 in v1)  →  fetch  →  parse  →  extract_times  →  geocode  →  build  →  data/deals.json  →  static site (Leaflet)
                                                          ↑
                                                     overrides/*.yaml
                                                     (manual enrichments: cuisine, neighborhood, personal)
```

- **Editable / intermediate files**: YAML.
- **Browser-consumed bundle**: JSON (no client-side YAML parser dep).
- **Pipeline stages are pluggable per source**. Each source provides its own `fetch()` and `parse()` returning a normalized `SourceRecord`.
- **Caching**: 3 layers (HTTP-level, per-record by source `modified` timestamp, per-stage by content hash).

## v1 sources

| Source | Endpoint | Records | Native structure | Deal kind |
|---|---|---|---|---|
| growomaha | `GET /wp-json/wp/v2/happy-hour?per_page=100&page=N` | 261 | day-of-week + time-slots taxonomies, per-record `modified_gmt` | `happy_hour` |
| visitomaha | `GET /includes/rest_v2/plugins_offers_offers/find/?json=...` | ~11 | date ranges (`poststart`/`postend`), per-record lat/lng in `listings[]`, `updated` | `special` |
| bigdealsmedia | `GET https://omaha.bigdealsmedia.net/category/restaurants` (SSR HTML) | ~10-30, exact count established on first scrape | inline merchant cards with original/sale/savings prices; no day/time | `voucher` |

### Source-specific notes

**growomaha**, uses WordPress + FacetWP. The REST API exposes the underlying taxonomies that the public site filters by. We fetch:
- `/wp-json/wp/v2/happy-hour?per_page=100` (3 pages to cover 261 records)
- `/wp-json/wp/v2/day-of-week` (7 entries; cached, almost never changes)
- `/wp-json/wp/v2/time-slots` (~46 entries; cached)
- `/wp-json/wp/v2/cities` (8 entries; cached)
- `/wp-json/wp/v2/features` (16 entries; cached)

Time-slot taxonomy gives **start times only** (`300pm`, `330pm`, `400pm`, ...). End time comes from the prose in `excerpt.rendered`. The parser does:
1. Day list = taxonomy lookup of `day-of-week[]` IDs.
2. Start time = earliest entry in `time-slots[]` (after taxonomy lookup).
3. End time = LLM extracted from `excerpt.rendered`; cached by SHA(excerpt).
4. `kind: happy_hour`. Reverse HH windows detected when prose mentions "reverse" near a time range; emitted as additional windows with `type: reverse_hh`.

**visitomaha**, Mongo-style REST query baked into the URL (categories filter, `site_primary` tag, sort by quality). Each offer has `poststart`/`postend` for validity and `listings[0].latitude`/`longitude` if the offer is tied to a venue. The token in the URL is public (visible in browser).

**bigdealsmedia**, SSR HTML. Pure server-rendered cards before the SPA hydrates, so a simple HTML parse is sufficient. Each card surface: merchant name, deal title, original price, sale price, savings, category. No day/time. No address (geocode by name).

## Data model

### Final bundle (`data/deals.json`, browser-loaded)

```json
{
  "schema_version": "1.0",
  "scraped_at": "2026-06-06T12:34:56Z",
  "sources": [
    {"name": "growomaha", "url": "...", "fetched_at": "...", "record_count": 261},
    {"name": "visitomaha", "url": "...", "fetched_at": "...", "record_count": 11},
    {"name": "bigdealsmedia", "url": "...", "fetched_at": "...", "record_count": 30}
  ],
  "restaurants": [
    {
      "id": "blue-sky-patio",
      "name": "Blue Sky Patio",
      "address": "1234 Example St, Omaha, NE 68102",
      "lat": 41.2565,
      "lng": -95.9345,
      "geocode_confidence": "high",
      "cuisine": ["american", "sports_bar"],
      "neighborhood": "Aksarben",
      "personal": {
        "tags": ["date_spot", "favorite"],
        "rating": 4,
        "notes": "Great patio after work"
      },
      "deals": [
        {
          "kind": "happy_hour",
          "source": "growomaha",
          "source_url": "https://growomaha.com/happy-hour/blue-sky-patio/",
          "external_link": "http://example.com/menu",
          "windows": [
            {"day": "mon", "start": "15:00", "end": "18:00", "type": "happy_hour"},
            {"day": "fri", "start": "21:00", "end": "23:00", "type": "reverse_hh"}
          ],
          "highlights": ["$5 wells", "half-off apps"],
          "raw_text": "Monday-Friday from 3-6 PM and reverse HH Fri 9-11 PM..."
        }
      ],
      "needs_review": false
    }
  ]
}
```

### Normalized `SourceRecord` (output of every source's `parse()`)

```yaml
- source: growomaha
  source_record_id: blue-sky-patio
  source_url: https://growomaha.com/happy-hour/blue-sky-patio/
  external_link: http://example.com/menu
  name: "Blue Sky Patio"
  record_modified_at: 2026-05-08T16:00:57Z   # source's own timestamp; cache key
  kind: happy_hour                            # determines downstream parser behavior
  # kind-specific payload:
  raw_text: "Monday-Friday from 3-6 PM..."
  pre_extracted_windows:                      # if source had structured day/time data
    - {day: mon, start: "15:00"}              # end times still need extraction
    - {day: tue, start: "15:00"}
```

For `kind: special`, `pre_extracted_windows` is null and `valid_from`/`valid_until` are populated. For `kind: voucher`, no time/date data; `original_price`/`sale_price`/`savings` are populated.

### Override files (hand-edited YAML)

- `data/overrides/addresses.yaml`, manual address+coord fixes when geocoding fails or returns garbage.
- `data/overrides/categories.yaml`, cuisine + neighborhood per restaurant ID.
- `data/overrides/personal.yaml`, tags, ratings, notes (your stuff; gitignored if private flag is set).
- `data/overrides/merges.yaml`, `merge_key` aliases so the same restaurant from different sources joins into one entry. Empty in v1 (we'll seed it when the second source produces a known duplicate).

## Repository layout

```
omaha-deals-map/
├── README.md                        # quickstart + how to add a source
├── Makefile                         # make scrape | extract | geocode | build | serve | test | rebuild
├── pyproject.toml                   # deps: requests, beautifulsoup4, pyyaml, pytest, anthropic
├── .python-version                  # pinned via pyenv/asdf
├── .gitignore
├── sources/
│   ├── registry.yaml                # active sources list
│   ├── _common.py                   # SourceRecord, BaseSource, shared helpers
│   ├── growomaha/
│   │   ├── __init__.py
│   │   ├── fetch.py
│   │   └── parse.py
│   ├── visitomaha/
│   │   ├── __init__.py
│   │   ├── fetch.py
│   │   └── parse.py
│   └── bigdealsmedia/
│       ├── __init__.py
│       ├── fetch.py
│       └── parse.py
├── scripts/
│   ├── 01_fetch.py                  # iterates sources/registry.yaml
│   ├── 02_parse.py                  # iterates sources/registry.yaml
│   ├── 03_extract_times.py          # regex + Claude API fallback for windows missing end times
│   ├── 04_geocode.py                # Nominatim + overrides/addresses.yaml
│   ├── 05_build.py                  # merge stages + overrides -> deals.json
│   └── review_queue.py              # CLI: list rows where needs_review = true
├── data/
│   ├── raw/<source>/<timestamp>.{html,json}    # archived per-source raw pulls; git-tracked; 01_fetch dedups by body SHA so only changed snapshots get committed; prune to last 12 in 05_build
│   ├── parsed.yaml                  # union of all sources' SourceRecords
│   ├── extracted.yaml               # parsed.yaml + resolved windows
│   ├── geocode_cache.yaml           # name -> {address, lat, lng, confidence}
│   ├── llm_cache.yaml               # SHA(raw_text) -> extracted end-times / structured highlights
│   ├── http_cache.yaml              # per-URL ETag / Last-Modified / body SHA
│   ├── deals.json                   # FINAL, site consumes this
│   └── overrides/
│       ├── addresses.yaml
│       ├── categories.yaml
│       ├── personal.yaml
│       └── merges.yaml
├── site/                            # served by GitHub Pages
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   ├── icons/                       # SVG markers per deal kind + per day
│   └── data.json                    # copied (not symlinked) from data/deals.json by 05_build.py, GitHub Pages doesn't follow symlinks reliably
├── tests/
│   ├── conftest.py
│   ├── fixtures/<source>/sample_response.{html,json}
│   ├── test_growomaha_parse.py
│   ├── test_visitomaha_parse.py
│   ├── test_bigdealsmedia_parse.py
│   ├── test_extract_times.py
│   ├── test_geocode.py
│   ├── test_build_merge.py
│   └── test_cache_invalidation.py
└── .github/workflows/
    ├── scrape.yml                   # weekly cron; commits diffs; redeploys Pages
    ├── pages.yml                    # deploy site/ on push to main
    └── ci.yml                       # pytest + lint on PRs
```

## Pipeline stages

Each stage reads its predecessor's output, writes its own, and is independently re-runnable with a `--force` flag.

### `01_fetch.py`

For each source in `sources/registry.yaml`:
1. Call `source.fetch()` which returns `(raw_bytes, content_type, response_meta)`.
2. Use `data/http_cache.yaml` to send `If-None-Match` / `If-Modified-Since` if previous run captured them.
3. On 304 (or matching body SHA), short-circuit: log "no changes" and exit 0 for this source.
4. Otherwise, write to `data/raw/<source>/<UTC-timestamp>.{html,json}` and update `data/raw/<source>/latest.{html,json}` symlink.
5. Fail loudly if HTTP error or response size < 50% of last successful run (anti-silent-breakage guard).

### `02_parse.py`

For each source, call `source.parse(latest_raw)` -> `list[SourceRecord]`. Concatenate into `data/parsed.yaml`. Each row carries `source`, `source_record_id`, `record_modified_at`, `kind`. Fails if total record count drops by >50% vs previous run.

### `03_extract_times.py`

Operates only on `kind: happy_hour` records. For each:
1. If `pre_extracted_windows` covers all days and has start+end -> done; copy to output.
2. If start-only (growomaha pattern) -> run end-time extraction:
   - Regex first: patterns like `\d+(:\d+)?\s*-\s*\d+(:\d+)?\s*[ap]m`.
   - Claude API fallback for blobs the regex can't parse with confidence. Cached by SHA(raw_text) in `data/llm_cache.yaml`. Cache hits skip the API call.
3. If `record_modified_at` is unchanged from previous run AND prior extraction exists -> reuse cached extraction (skip both regex and LLM).
4. Set `needs_review: true` if extraction fails entirely.

Writes `data/extracted.yaml`.

### `04_geocode.py`

For each record (any kind):
1. If `data/overrides/addresses.yaml` has an entry by `id` -> use override (skip Nominatim).
2. If `data/geocode_cache.yaml` has a hit by `name` -> use cache.
3. Else: Nominatim query `"{name}, Omaha, NE"` with 1s rate limit, custom UA + email per their policy.
4. Confidence label: `high` if result has `class=amenity` or `class=shop` and is within ~15 mi of Omaha center; `medium` if result is in `Douglas|Sarpy|Pottawattamie` counties; `low` otherwise.
5. `low` -> also set `needs_review: true`.

Writes `data/geocoded.yaml` and refreshes `data/geocode_cache.yaml`.

### `05_build.py`

1. Read `data/geocoded.yaml`.
2. Group records by `merge_key` (default = slug(name); overridable via `overrides/merges.yaml`).
3. For each merged restaurant, build the final entry: identity fields from first record (alphabetically by source), `deals[]` from all source records.
4. Merge in `overrides/categories.yaml` and `overrides/personal.yaml` by restaurant `id`.
5. Validate: every restaurant has lat/lng in Omaha-ish bounding box (-96.4 to -95.5 lng, 41.0 to 41.5 lat) or `geocode_confidence: low`. No duplicate IDs.
6. Write `data/deals.json` and copy to `site/data.json`.
7. Print summary: total restaurants, count by kind, count by `needs_review`, geocode confidence distribution.

### `review_queue.py`

CLI helper. Reads `data/deals.json`, prints all entries where `needs_review: true` with the field(s) that triggered the flag, in a format that paste-edits cleanly into the right override YAML.

## Caching summary

| Layer | Where | Key | Skip condition |
|---|---|---|---|
| HTTP | per source's `fetch()` | URL | 304 response OR body SHA matches `http_cache.yaml` |
| Per-record | extract_times + geocode | `(source, source_record_id)` | `record_modified_at` unchanged from prior run |
| Content-hash | LLM extractor + Nominatim | SHA(raw_text) / normalized name | hit found in `llm_cache.yaml` / `geocode_cache.yaml` |

`make rebuild` = run all stages with `--force` to bypass every cache.

## Mobile UX (Leaflet on phone)

- **Top app bar**: title + date (today) + filter icon.
- **Filter sheet** (slide-up): toggle deal kinds (`happy hours` / `specials` / `vouchers`), cuisine multi-select, neighborhood multi-select, "favorites only" toggle, "now" toggle (only show deals whose window contains current time).
- **Day-of-week tabs**: M T W T F S S, full-width, default to today. Tap a day to switch the happy-hour layer to that day's windows. Specials and vouchers ignore the day tab.
- **Map**: Leaflet + default OSM tiles (`tile.openstreetmap.org`) in v1. Swap to Stadia or CARTO Voyager free tier later if we want prettier styling; both are drop-in replacements with attribution-only. Restaurants render as markers; color/icon encodes deal kind. Tap marker -> bottom sheet with name, all deals at this venue, time windows for the selected day, "Open in Google Maps" button (handoff), personal notes/rating if present.
- **Performance**: 261 + 11 + 30 markers, around 300 markers total. Leaflet handles this trivially. We can add `Leaflet.markercluster` later if it feels crowded; not in v1.
- **Offline / weak signal**: bundle is small (around 200KB compressed JSON estimate). Map tiles need network; user accepts this (declined PWA option earlier).

## Error handling

- **Source HTTP failure** (timeout, 5xx, DNS): log error, skip that source for this run, continue with others. Build emits `deals.json` based on most-recent successful pulls (using `data/raw/<source>/latest.*`). Site banner if any source's data is >7 days stale.
- **Parse failure** (record count drops >50%): hard fail. Don't overwrite `parsed.yaml`. Hand the issue back to the operator.
- **LLM API failure** (rate limit, auth): retry with backoff; if it persists, mark affected records `needs_review: true` and continue.
- **Nominatim failure**: same, mark `needs_review: true`, continue.
- **Schema validation failure in build**: hard fail. The site never serves an invalid bundle.

## Testing

Pytest. Fixtures captured from real responses, stored under `tests/fixtures/<source>/`.

- **Per-source parser tests**: feed a fixture HTML/JSON, assert specific `SourceRecord` rows + structure.
- **Extractor tests**: deal-text -> windows. Cover common shapes: "Mon-Fri 3-6", "Daily", "All day Sunday", "reverse HH 9-11 PM", typos in fixtures.
- **Geocoder tests**: mock Nominatim responses; verify override precedence.
- **Build merge tests**: synthetic SourceRecords across sources with `merges.yaml` rules -> expected merged restaurant entries.
- **Cache invalidation tests**: simulate unchanged vs changed `record_modified_at`, assert downstream stages reuse vs recompute.

Test runner is `make test`. CI runs it on PRs.

## CI / scheduled scrape

- **`.github/workflows/scrape.yml`**: weekly cron (Mondays 06:00 UTC). Runs `make all`. If `data/` changed, commits with `chore(data): scrape ${{date}}` and `Refs: omaha-deals-map`. Push triggers Pages redeploy.
- **`.github/workflows/pages.yml`**: deploys `site/` to GitHub Pages on every push to `main`.
- **`.github/workflows/ci.yml`**: lint (ruff) + pytest on PRs.

All workflow `uses:` references pinned to commit SHA per the REDACTED policy. Runner is `prod-arc-runner-set` if available, otherwise `ubuntu-latest` for this personal repo (no REDACTED-managed runner available outside the org).

## Token cost estimate (LLM usage)

- **End-time extraction** for growomaha: ~261 records times around 200 input tokens each, one-time on first run; cached thereafter. ~52k input tokens. Using Claude Haiku 4.5: ~$0.04 first run, ~$0 on subsequent (cache hits unless prose changes).
- **No LLM use** for visitomaha or bigdealsmedia in v1.
- **Estimated steady-state cost**: <$0.10 per rescrape.

## Deferred (v2+)

- **Reddit r/Omaha "Cheap Eats Daily" weekly thread**. High value (OP organizes deals by day-of-week). Requires Reddit OAuth app + `praw` dependency. Spec stub: see appendix A.
- **ohmyomaha.com day-of-week pages**, HTML scrape + LLM extractor. Adds coverage for small/neighborhood spots.
- **npdodge / oldmarket / happyhourintown**, additional HTML scrapes; LLM extraction.
- **happyhopper.app**, investigate their API; might need a key.
- **PWA wrapper**, install to phone home screen with offline tile cache (user declined for v1).
- **MarkerCluster** if 300+ markers feels crowded.
- **Auto-detect dead sources**, if a source returns 0 records 3 runs in a row, surface in scrape-workflow output.

### Appendix A, Reddit source future-prep (v2 notes only)

When ready to add:
1. Create a Reddit script-type app at https://www.reddit.com/prefs/apps. Save client_id + client_secret.
2. Add `praw` to `pyproject.toml`.
3. `sources/reddit/fetch.py`: search subreddit for newest "Cheap Eats Daily" thread, return post body + top-N comments.
4. `sources/reddit/parse.py`: pass full thread to Claude with a JSON-schema prompt. Output `SourceRecord` rows with `kind: happy_hour` or `kind: daily_special`.
5. Token cost: bigger blob per scrape but cached by SHA; ~$0.10-0.30 per new weekly thread.
6. Auth secrets via GitHub Actions repo secrets, not in repo.

## Open questions / decisions to confirm at user review

- **growomaha end-time extraction**, relying on LLM to parse `excerpt.rendered` for end times. Alternative: regex-only (accept around 10-20% rows missing end time, mark `needs_review`). Default in this spec: LLM + cache.
- **Bounding-box guardrail in build**, if a Nominatim result is wildly off (e.g., Omaha, AR), I auto-set `needs_review: true` and exclude it from the map. Operator can fix via `overrides/addresses.yaml`. Default in this spec: yes, guard.
- **`personal.yaml` privacy**, gitignored or committed? If gitignored, the deployed site won't have your tags/ratings unless you also commit the merged `deals.json`. Recommend committing both (it's your repo, you control visibility).
