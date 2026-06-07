---
name: add-source
description: Scaffold a new data source for the Omaha Deals Map pipeline. Creates sources/<name>/ with fetch.py + parse.py + __init__.py, registers it in sources/registry.yaml, and seeds a fixture-based test. Use when adding a new website to scrape.
---

# add-source

Scaffolds a new source plug-in for this repo's multi-source pipeline.

Usage: `/add-source <name>` where `<name>` is a lowercase identifier (no
spaces, no hyphens, e.g. `ohmyomaha`, `npdodge`, `reddit_omaha`).

## What to do

1. **Validate the name.** Must match `^[a-z][a-z0-9_]*$`. If it doesn't, ask
   the user for a corrected name.

2. **Confirm it doesn't already exist.** `sources/<name>/` must not be a
   directory. If it is, ask whether to abort or extend the existing module.

3. **Ask three clarifying questions** before scaffolding (use AskUserQuestion):

   - **Source URL** (where to fetch from). Free text. If the user has an API
     URL, use it; otherwise an HTML listing page.
   - **Deal kind**, one of: `happy_hour` (weekly recurring windows),
     `special` (date-range coupon), `voucher` (Groupon-style pre-paid).
   - **Response format**, one of: `JSON API` (parse with `json.loads`),
     `HTML page` (parse with `BeautifulSoup`).

4. **Capture a fixture** so the parse test can run offline:

   ```bash
   mkdir -p tests/fixtures/<name>
   curl -sS -A "Mozilla/5.0" "<URL>" > tests/fixtures/<name>/sample.{json,html}
   ```

   Use `.json` for JSON APIs, `.html` for HTML pages. If `curl` fails or returns
   <1KB, stop and surface the error.

5. **Write the four code files**:

   `sources/<name>/__init__.py`:
   ```python
   """<name> source module."""
   from .fetch import fetch  # noqa: F401
   from .parse import parse  # noqa: F401
   ```

   `sources/<name>/fetch.py`:
   ```python
   """<name> fetcher."""
   from __future__ import annotations

   from dataclasses import dataclass
   from datetime import datetime, UTC
   from pathlib import Path

   from scripts._lib.http_cache import CachedHttpClient

   _URL = "<URL>"


   @dataclass
   class <Name>Payload:
       <records or html field>: <list[dict] | bytes>
       source_url: str
       fetched_at: str


   def fetch(client: CachedHttpClient | None = None,
             cache_path: Path | None = None) -> <Name>Payload:
       if client is None:
           client = CachedHttpClient(cache_path or Path("data/http_cache.yaml"))
       resp = client.get(_URL)
       return <Name>Payload(
           ...=resp.body,
           source_url=_URL,
           fetched_at=datetime.now(UTC).isoformat(),
       )
   ```

   Use `records: list[dict]` for JSON APIs and `html: bytes` for HTML pages.
   `<Name>` is PascalCase of `<name>`.

   `sources/<name>/parse.py`:
   ```python
   """Convert <Name>Payload into SourceRecord rows."""
   from __future__ import annotations

   from sources._common import SourceRecord
   from sources.<name>.fetch import <Name>Payload


   def parse(payload: <Name>Payload) -> list[SourceRecord]:
       # TODO: implement the actual parse logic. See sources/visitomaha/parse.py
       # for a JSON example or sources/bigdealsmedia/parse.py for an HTML example.
       return []
   ```

   `tests/test_<name>_fetch.py`:
   ```python
   """Tests for <name>.fetch."""
   from unittest.mock import MagicMock

   from sources.<name>.fetch import fetch, <Name>Payload


   def test_fetch_returns_payload(fixtures_dir):
       raw = (fixtures_dir / "<name>" / "sample.<ext>").read_bytes()
       client = MagicMock()
       client.get = lambda url: type("R", (), {"body": raw, "status_code": 200})()
       payload = fetch(client=client)
       assert isinstance(payload, <Name>Payload)
   ```

6. **Register the source** in `sources/registry.yaml`. Append `  - <name>`
   to the `sources:` list. Preserve existing order.

7. **Verify**: `source .venv/bin/activate && pytest -q -m "not slow" && ruff check .`
   Both must pass. If ruff complains about import order, run `ruff check --fix .`.

8. **Commit** (don't push, the user controls pushes):
   ```
   feat(<name>): scaffold new source module

   Refs: omaha-deals-map
   ```

9. **Report back** with the next step:

   > The `<name>` source is scaffolded. To finish wiring it up, implement
   > `sources/<name>/parse.py` to convert the payload into SourceRecord rows
   > (see sources/visitomaha/parse.py or sources/bigdealsmedia/parse.py as
   > examples). Then add a parse test against the captured fixture.

## Notes

- Do NOT add LLM extraction or geocoding logic to the source. Those live in
  `scripts/_extract_main.py` and `scripts/_geocode_main.py` respectively.
- If the deal kind is `happy_hour` and the source provides structured day +
  time data (like growomaha's WP taxonomies), populate `pre_extracted_windows`
  on each `SourceRecord` so the extractor only needs to fill in end times.
- If `kind=special`, set `valid_from` and `valid_until` from the source.
- If `kind=voucher`, set `original_price`, `sale_price`, `savings`, `category`.
