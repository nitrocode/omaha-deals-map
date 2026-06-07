# Omaha Deals Map

Mobile-first map of Omaha-area restaurant happy hours, specials, and vouchers.

**Live:** https://nitrocode.github.io/omaha-deals-map/

## What's on the map

| Kind | Source | Shape |
|---|---|---|
| Happy hour | growomaha.com | Weekly recurring (day-of-week, time window) |
| Special | visitomaha.com | Date-range coupon |
| Voucher | omaha.bigdealsmedia.net | Pre-paid discount (Groupon-style) |

Updated weekly by GitHub Actions; you can also rescrape locally any time.

## Run locally

```bash
make install                       # one-time
export ANTHROPIC_API_KEY=...       # optional, for LLM end-time extraction fallback
export MAPBOX_TOKEN=...            # optional, geocoder fallback when Nominatim misses
make all                           # fetch + parse + extract + geocode + build
make serve                         # serve site/ at http://localhost:8000
```

**Caching is comprehensive.** Re-running `make all` only hits the network for content that's actually changed:

| Cache | File | Survives across runs? |
|---|---|---|
| HTTP body + ETag/Last-Modified | `data/http_cache.yaml` | yes (per-URL) |
| Per-source raw snapshots | `data/raw/<source>/latest.pickle` | yes (gitignored binary) |
| Geocode name -> lat/lng | `data/geocode_cache.yaml` | yes |
| LLM end-time extractions | `data/llm_cache.yaml` | yes (when ANTHROPIC_API_KEY is set) |

Use `make rebuild` to force every cache miss.

Individual stages: `make scrape`, `make parse`, `make extract`, `make geocode`, `make build`. `make rebuild` forces every stage to bypass caches.

## Add a source

1. Create `sources/<name>/__init__.py`, `fetch.py`, `parse.py`.
2. Implement `fetch(client=None, cache_path=None) -> SomePayload` and `parse(payload) -> list[SourceRecord]`.
3. Add the name to `sources/registry.yaml`.
4. Add a fixture + parser test in `tests/` (capture via curl into `tests/fixtures/<name>/`).
5. Run `make all`.

## Override files

Edit these YAML files in `data/overrides/` and rerun `make build`:

- `addresses.yaml` hand-fixes bad geocodes by restaurant id, e.g. `blue-sky-patio: {address: "1234 X", lat: 41.25, lng: -95.93}`.
- `categories.yaml` assigns cuisine + neighborhood per restaurant id.
- `personal.yaml` holds your tags/ratings/notes (gitignored; stays local).
- `merges.yaml` declares "these source-record ids are the same restaurant" so deals merge into one map pin.

## Find records that need attention

```bash
make review
```

Prints any restaurant where geocoding or time extraction failed, with the override file you'd edit to fix it.

## Pipeline stages

```
01_fetch -> raw/<source>/latest.pickle
02_parse -> parsed.yaml
03_extract_times -> extracted.yaml      (regex first, Claude Haiku fallback if ANTHROPIC_API_KEY set)
04_geocode -> geocoded.yaml             (Nominatim, 1 req/sec, override + cache)
05_build  -> deals.json (and site/data.json)
```

Caches (`data/http_cache.yaml`, `data/llm_cache.yaml`, `data/geocode_cache.yaml`) make repeated runs near-instant.

## Troubleshooting

- **`make review` shows lots of needs_review entries.** Usually Nominatim couldn't find a confident match. Fix in `data/overrides/addresses.yaml`.
- **CI scrape fails on `ANTHROPIC_API_KEY`.** Set the secret at https://github.com/nitrocode/omaha-deals-map/settings/secrets/actions/new. The pipeline works without it (regex-only extraction); you'll just see more `needs_review` entries.
- **Site shows nothing.** Open browser console. If `data.json: 404`, the Pages build hasn't run yet; push any change to `data/deals.json`, `site/`, or run the `Deploy GitHub Pages` workflow manually.

## Design

See `docs/superpowers/specs/2026-06-06-omaha-deals-map-design.md` and `docs/superpowers/plans/2026-06-06-omaha-deals-map.md`.
