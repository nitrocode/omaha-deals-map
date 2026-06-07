# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Personal project (`nitrocode/omaha-deals-map`). Multi-source Python scraping pipeline that emits `data/deals.json`, consumed by a static Leaflet site deployed via GitHub Pages.

Live: https://nitrocode.github.io/omaha-deals-map/
Design: `docs/superpowers/specs/2026-06-06-omaha-deals-map-design.md`
Plan:   `docs/superpowers/plans/2026-06-06-omaha-deals-map.md`

## Pipeline shape

Five numbered stages in `scripts/`, each split into two files:

- `<NN>_<name>.py`, CLI entry point. **Keep this stub small.** Just argparse + `sys.exit(main(...))`.
- `_<name>_main.py`, the real logic. Importable, mockable, tested directly.

Order: `01_fetch → 02_parse → 03_extract_times → 04_geocode → 05_build`. Run all via `make all`; individually via `make scrape | parse | extract | geocode | build`; with caches bypassed via `make rebuild`.

## Adding a source

Sources are plug-in modules under `sources/<name>/`:

- `__init__.py` re-exports `fetch` and `parse`.
- `fetch.py` exports `fetch(client, cache_path) -> SomePayload` (dataclass).
- `parse.py` exports `parse(payload) -> list[SourceRecord]`.

Then add the name to `sources/registry.yaml` and a fixture-based test (use `tests/fixtures/<name>/` for captured payloads).

`SourceRecord` and `Window` live in `sources/_common.py`. `kind` is one of `happy_hour | special | voucher`. Days are `mon..sun` (lowercase, 3-char). Times are `HH:MM` 24h.

## Caching (three layers)

| Cache | File | Survives across runs? |
|---|---|---|
| HTTP body + ETag/Last-Modified | `data/http_cache.yaml` | yes |
| Per-source raw payload | `data/raw/<source>/latest.pickle` | yes (gitignored, regenerable) |
| Geocode name to lat/lng | `data/geocode_cache.yaml` | yes |

`make all` is offline-safe for unchanged content. `make rebuild` forces every cache miss.

## Tests

Fast suite (default): `pytest -q -m "not slow"`, no network, runs in <1s.
Live integration: `pytest -m slow`, hits real APIs (growomaha, visitomaha, bigdealsmedia, Photon, the SRI gate). Add the `pytestmark = pytest.mark.slow` line to any new test that touches the network.

## SRI hashes, compute, never fabricate

This was a real bug shipped on this repo. **Every** `<link>`/`<script>` integrity attribute in `site/*.html` is verified by `scripts/check_sri.py` (used by pre-commit + CI). To get a correct hash:

```bash
curl -sL <url> | openssl dgst -sha384 -binary | openssl base64 -A
```

Use sha384, not sha256. Cross-verify against cdnjs when reasonable.

## Geocoder chain (`scripts/_geocode_main.py`)

Order: `override -> source-provided lat/lng -> name cache -> Nominatim -> Photon`.

`_is_plausible_match` in `_geocode_main.py` is a **load-bearing** strict-token-overlap guard against Photon's fuzzy false positives ("Nick's Quorum" matched "Fairfield Inn" before this check existed). Don't relax the 5-char threshold without understanding why it's there.

## Time format invariant

Storage everywhere = `HH:MM` 24h. Display in the UI = 12h via `formatTime12()` in `site/app.js`. Tests assert 24h. Never mix the two.

## Gitignored, never commit

- `data/raw/` (binary pickles, regenerable)
- `data/overrides/personal.yaml` (your tags/ratings/notes, private)
- `.venv/`, `__pycache__/`, `*.egg-info/`

## Commits

Conventional Commits with `Refs: omaha-deals-map` trailer. Working directly on `main` is the convention (personal repo, no PR gate). Pre-commit (`pre-commit install` once) runs ruff + the fast pytest suite + SRI verification on every commit.

## Pre-commit setup (one-time)

```bash
pip install -e ".[dev]"
pre-commit install
```

After that, hooks fire automatically on `git commit`. CI runs the same checks.
