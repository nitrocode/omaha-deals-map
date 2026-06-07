# Omaha Deals Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mobile-first GitHub Pages site that shows Omaha-area restaurant deals (happy hours, specials, vouchers) on a per-day map, sourced from 3 sites and refreshable via a one-command rescrape.

**Architecture:** Multi-source Python pipeline (`fetch -> parse -> extract -> geocode -> build`) emits a single `data/deals.json` consumed by a Leaflet static site. Editable files are YAML, browser bundle is JSON. Caching at HTTP, per-record, and per-stage layers keeps rescrapes cheap.

**Tech Stack:** Python 3.11+, `requests`, `beautifulsoup4`, `pyyaml`, `pytest`, `anthropic` (LLM fallback), `ruff` (lint), Leaflet 1.9 + OSM tiles, GitHub Actions for CI + scheduled scrape + Pages deploy.

**Spec reference:** `docs/superpowers/specs/2026-06-06-omaha-deals-map-design.md`

**Conventions for every task:**
- TDD: write failing test, verify FAIL, implement, verify PASS, commit.
- Conventional Commits with `Refs: omaha-deals-map` trailer.
- Run `pytest -q` (whole suite) before each commit.
- Files use 4-space indent, ~100 col soft limit.
- No em-dashes (per user CLAUDE.md).

---

## Phase 1: Project scaffold

### Task 1: Python project skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `Makefile`
- Create: `README.md`
- Create: `sources/__init__.py` (empty)
- Create: `scripts/__init__.py` (empty)
- Create: `scripts/_lib/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Create: `data/.gitkeep`, `data/raw/.gitkeep`, `data/overrides/.gitkeep`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "omaha-deals-map"
version = "0.1.0"
description = "Mobile-first map of Omaha restaurant happy hours, specials, and vouchers."
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31",
    "beautifulsoup4>=4.12",
    "pyyaml>=6.0",
    "anthropic>=0.40",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "ruff>=0.6",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
ignore = ["E501"]  # line length handled by formatter
```

- [ ] **Step 2: Write `.python-version`**

```
3.11.9
```

- [ ] **Step 3: Write `Makefile`**

```makefile
.PHONY: install scrape parse extract geocode build all serve test lint review rebuild clean

install:
	pip install -e ".[dev]"

scrape:
	python scripts/01_fetch.py

parse:
	python scripts/02_parse.py

extract:
	python scripts/03_extract_times.py

geocode:
	python scripts/04_geocode.py

build:
	python scripts/05_build.py

all: scrape parse extract geocode build

rebuild:
	python scripts/01_fetch.py --force
	python scripts/02_parse.py --force
	python scripts/03_extract_times.py --force
	python scripts/04_geocode.py --force
	python scripts/05_build.py --force

serve:
	cd site && python -m http.server 8000

test:
	pytest -q

lint:
	ruff check .

review:
	python scripts/review_queue.py

clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ */__pycache__ */*/__pycache__
```

- [ ] **Step 4: Write `README.md`**

Skeleton; expanded in Task 32.

```markdown
# Omaha Deals Map

Mobile-first map of Omaha-area restaurant happy hours, specials, and vouchers.

Live: https://nitrocode.github.io/omaha-deals-map/

See `docs/superpowers/specs/2026-06-06-omaha-deals-map-design.md` for the full design.
```

- [ ] **Step 5: Create empty `__init__.py` files + data/ stubs**

```bash
touch sources/__init__.py scripts/__init__.py scripts/_lib/__init__.py tests/__init__.py
mkdir -p data/raw data/overrides
touch data/.gitkeep data/raw/.gitkeep data/overrides/.gitkeep
```

- [ ] **Step 6: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures."""
from pathlib import Path
import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_data_dir(tmp_path) -> Path:
    """Isolated data/ directory for tests that read or write to it."""
    d = tmp_path / "data"
    (d / "raw").mkdir(parents=True)
    (d / "overrides").mkdir(parents=True)
    return d
```

- [ ] **Step 7: Verify the skeleton installs**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q       # should report "0 tests collected" without errors
ruff check .    # should pass
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .python-version Makefile README.md sources/ scripts/ tests/ data/
git commit -m "chore: scaffold python project structure

Refs: omaha-deals-map"
```

---

### Task 2: SourceRecord data model

**Files:**
- Create: `sources/_common.py`
- Create: `tests/test_common.py`

- [ ] **Step 1: Write `tests/test_common.py`**

```python
"""Tests for SourceRecord and shared helpers."""
import pytest
from sources._common import SourceRecord, slugify, Window


def test_slugify_basic():
    assert slugify("Blue Sky Patio") == "blue-sky-patio"


def test_slugify_strips_punctuation_and_entities():
    assert slugify("Addy's Sports Bar & Grill") == "addys-sports-bar-grill"
    assert slugify("72 Table & Tap") == "72-table-tap"


def test_slugify_collapses_whitespace():
    assert slugify("  Hello   World  ") == "hello-world"


def test_source_record_round_trip():
    r = SourceRecord(
        source="growomaha",
        source_record_id="blue-sky-patio",
        source_url="https://example.com/x",
        name="Blue Sky Patio",
        record_modified_at="2026-05-08T16:00:57Z",
        kind="happy_hour",
        raw_text="Mon-Fri 3-6 PM",
        external_link="http://bit.ly/x",
        pre_extracted_windows=[Window(day="mon", start="15:00")],
    )
    d = r.to_dict()
    assert d["source"] == "growomaha"
    assert d["pre_extracted_windows"][0]["day"] == "mon"
    r2 = SourceRecord.from_dict(d)
    assert r2 == r


def test_source_record_rejects_invalid_kind():
    with pytest.raises(ValueError):
        SourceRecord(
            source="x", source_record_id="x", source_url="x", name="x",
            record_modified_at="x", kind="nope", raw_text="",
        )


def test_window_validates_day_and_time_format():
    Window(day="mon", start="15:00", end="18:00")
    with pytest.raises(ValueError):
        Window(day="MON", start="15:00")
    with pytest.raises(ValueError):
        Window(day="mon", start="3pm")
```

- [ ] **Step 2: Run, expect ImportError**

```bash
pytest tests/test_common.py -v
```

- [ ] **Step 3: Implement `sources/_common.py`**

```python
"""Shared types for source modules."""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from typing import Any

VALID_KINDS = {"happy_hour", "special", "voucher"}
VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def slugify(name: str) -> str:
    s = (name
         .replace("&amp;", "&").replace("&#038;", "&")
         .replace("&#8217;", "'").replace("&apos;", "'"))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


@dataclass
class Window:
    day: str
    start: str
    end: str | None = None
    type: str = "happy_hour"  # or "reverse_hh"

    def __post_init__(self):
        if self.day not in VALID_DAYS:
            raise ValueError(f"invalid day: {self.day!r}")
        if not TIME_RE.match(self.start):
            raise ValueError(f"invalid start time {self.start!r}; expected HH:MM 24h")
        if self.end is not None and not TIME_RE.match(self.end):
            raise ValueError(f"invalid end time {self.end!r}; expected HH:MM 24h")


@dataclass
class SourceRecord:
    source: str
    source_record_id: str
    source_url: str
    name: str
    record_modified_at: str
    kind: str
    raw_text: str = ""
    external_link: str | None = None
    pre_extracted_windows: list[Window] = field(default_factory=list)
    valid_from: str | None = None
    valid_until: str | None = None
    title: str | None = None
    description: str | None = None
    original_price: float | None = None
    sale_price: float | None = None
    savings: float | None = None
    category: str | None = None
    lat: float | None = None
    lng: float | None = None

    def __post_init__(self):
        if self.kind not in VALID_KINDS:
            raise ValueError(f"invalid kind: {self.kind!r}; expected one of {VALID_KINDS}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SourceRecord:
        windows = [Window(**w) for w in d.get("pre_extracted_windows", []) or []]
        d2 = {**d, "pre_extracted_windows": windows}
        return cls(**d2)
```

- [ ] **Step 4: Run, expect PASS**

```bash
pytest tests/test_common.py -v
```

- [ ] **Step 5: Commit**

```bash
git add sources/_common.py tests/test_common.py
git commit -m "feat(common): add SourceRecord, Window, slugify

Refs: omaha-deals-map"
```

---

### Task 3: Source registry loader

**Files:**
- Create: `sources/registry.yaml`
- Create: `sources/_registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Write `sources/registry.yaml`**

```yaml
sources:
  - growomaha
  - visitomaha
  - bigdealsmedia
```

- [ ] **Step 2: Write the failing test**

```python
"""Tests for sources._registry."""
import pytest
from sources._registry import load_active_sources, ActiveSources


def test_load_active_sources_returns_list_in_yaml_order():
    s = load_active_sources()
    assert isinstance(s, ActiveSources)
    assert s.names == ["growomaha", "visitomaha", "bigdealsmedia"]


def test_load_active_sources_rejects_unknown_name(tmp_path, monkeypatch):
    bad = tmp_path / "registry.yaml"
    bad.write_text("sources:\n  - nonexistent_source\n")
    monkeypatch.setattr("sources._registry.REGISTRY_PATH", bad)
    with pytest.raises(ImportError):
        load_active_sources()
```

- [ ] **Step 3: Run, expect ImportError**

- [ ] **Step 4: Implement `sources/_registry.py`**

```python
"""Discover active source modules from sources/registry.yaml."""
from __future__ import annotations
import importlib
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
import yaml

REGISTRY_PATH = Path(__file__).parent / "registry.yaml"


@dataclass
class ActiveSources:
    names: list[str]
    modules: list[ModuleType]


def load_active_sources() -> ActiveSources:
    data = yaml.safe_load(REGISTRY_PATH.read_text())
    names = list(data.get("sources", []))
    modules = []
    for name in names:
        try:
            mod = importlib.import_module(f"sources.{name}")
        except ImportError as e:
            raise ImportError(f"sources/{name}/ not found or broken: {e}") from e
        for required in ("fetch", "parse"):
            if not hasattr(mod, required):
                raise ImportError(f"sources.{name} missing required attr: {required}()")
        modules.append(mod)
    return ActiveSources(names=names, modules=modules)
```

- [ ] **Step 5: Add placeholder source packages**

```bash
for s in growomaha visitomaha bigdealsmedia; do
    mkdir -p sources/$s
    cat > sources/$s/__init__.py <<EOF
"""${s} source module. Implemented in later tasks."""
from .fetch import fetch  # noqa: F401
from .parse import parse  # noqa: F401
EOF
    printf 'def fetch(*a, **kw):\n    raise NotImplementedError("%s.fetch")\n' "$s" \
      > sources/$s/fetch.py
    printf 'def parse(*a, **kw):\n    raise NotImplementedError("%s.parse")\n' "$s" \
      > sources/$s/parse.py
done
```

- [ ] **Step 6: Run, expect PASS**

- [ ] **Step 7: Commit**

```bash
git add sources/
git commit -m "feat(registry): active-source loader with placeholder modules

Refs: omaha-deals-map"
```

---

## Phase 2: Shared helpers

### Task 4: HTTP cache helper

**Files:**
- Create: `scripts/_lib/http_cache.py`
- Create: `tests/test_http_cache.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for scripts._lib.http_cache."""
import hashlib
from unittest.mock import MagicMock
import pytest
from scripts._lib.http_cache import CachedHttpClient


def make_response(status=200, text="hello", headers=None):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.content = text.encode()
    r.headers = headers or {}
    return r


def test_first_fetch_stores_etag_and_body_sha(tmp_path, monkeypatch):
    cache_path = tmp_path / "http_cache.yaml"
    client = CachedHttpClient(cache_path=cache_path)
    resp = make_response(headers={"ETag": "abc", "Last-Modified": "Mon"})
    monkeypatch.setattr(client._session, "request", lambda *a, **kw: resp)

    r = client.get("https://x/y")
    assert r.changed is True
    assert r.status_code == 200
    assert r.body == b"hello"

    import yaml
    cache = yaml.safe_load(cache_path.read_text())
    entry = cache["https://x/y"]
    assert entry["etag"] == "abc"
    assert entry["body_sha"] == hashlib.sha256(b"hello").hexdigest()


def test_second_fetch_sends_if_none_match_and_handles_304(tmp_path, monkeypatch):
    cache_path = tmp_path / "http_cache.yaml"
    client = CachedHttpClient(cache_path=cache_path)
    cache_path.write_text("https://x/y:\n  etag: abc\n  last_modified: Mon\n  body_sha: deadbeef\n")
    # Re-init to pick up seeded cache
    client = CachedHttpClient(cache_path=cache_path)
    sent_headers = {}

    def fake_request(method, url, headers=None, **kw):
        sent_headers.update(headers or {})
        return make_response(status=304, text="")

    monkeypatch.setattr(client._session, "request", fake_request)
    r = client.get("https://x/y")
    assert sent_headers["If-None-Match"] == "abc"
    assert sent_headers["If-Modified-Since"] == "Mon"
    assert r.changed is False


def test_200_with_unchanged_body_sha_reports_unchanged(tmp_path, monkeypatch):
    cache_path = tmp_path / "http_cache.yaml"
    sha = hashlib.sha256(b"hello").hexdigest()
    cache_path.write_text(f"https://x/y:\n  body_sha: {sha}\n")
    client = CachedHttpClient(cache_path=cache_path)
    resp = make_response(text="hello")
    monkeypatch.setattr(client._session, "request", lambda *a, **kw: resp)
    r = client.get("https://x/y")
    assert r.changed is False
```

- [ ] **Step 2: Run, expect ImportError**

- [ ] **Step 3: Implement `scripts/_lib/http_cache.py`**

```python
"""HTTP client that uses ETag / Last-Modified / body-SHA to skip unchanged content."""
from __future__ import annotations
import hashlib
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
        if self.cache_path.exists():
            return yaml.safe_load(self.cache_path.read_text()) or {}
        return {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(yaml.safe_dump(self._cache, sort_keys=True))

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
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/http_cache.py tests/test_http_cache.py
git commit -m "feat(cache): CachedHttpClient with ETag/Last-Modified/body-SHA

Refs: omaha-deals-map"
```

---

### Task 5: YAML/JSON I/O helpers

**Files:**
- Create: `scripts/_lib/io.py`
- Create: `tests/test_io.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for scripts._lib.io."""
import os
from pathlib import Path
import pytest
from scripts._lib.io import read_yaml, write_yaml, read_json, write_json, atomic_write


def test_write_and_read_yaml_round_trip(tmp_path):
    p = tmp_path / "x.yaml"
    write_yaml(p, {"a": [1, 2, 3], "b": "hi"})
    assert read_yaml(p) == {"a": [1, 2, 3], "b": "hi"}


def test_read_yaml_missing_returns_default():
    assert read_yaml(Path("/nonexistent"), default={}) == {}


def test_atomic_write_does_not_corrupt_on_partial_failure(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text("original")
    def boom(*a, **kw): raise OSError("disk full")
    monkeypatch.setattr(os, "rename", boom)
    with pytest.raises(OSError):
        atomic_write(p, "new contents")
    assert p.read_text() == "original"


def test_write_json_pretty(tmp_path):
    p = tmp_path / "x.json"
    write_json(p, {"a": 1})
    assert p.read_text() == '{\n  "a": 1\n}\n'
```

- [ ] **Step 2: Run, expect ImportError**

- [ ] **Step 3: Implement `scripts/_lib/io.py`**

```python
"""YAML/JSON read+write with atomic semantics."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any
import yaml


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.rename(tmp, path)


def read_yaml(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return yaml.safe_load(path.read_text())


def write_yaml(path: Path, data: Any) -> None:
    atomic_write(path, yaml.safe_dump(data, sort_keys=False))


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, data: Any) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add scripts/_lib/io.py tests/test_io.py
git commit -m "feat(io): atomic YAML/JSON read+write helpers

Refs: omaha-deals-map"
```

---

## Phase 3: growomaha source

### Task 6: growomaha taxonomy resolver

**Files:**
- Create: `sources/growomaha/taxonomies.py`
- Create: `tests/fixtures/growomaha/*.json`
- Create: `tests/test_growomaha_taxonomies.py`

- [ ] **Step 1: Capture fixtures**

```bash
mkdir -p tests/fixtures/growomaha
for tax in day-of-week time-slots cities features; do
  curl -sS "https://growomaha.com/wp-json/wp/v2/$tax?per_page=100" \
    > tests/fixtures/growomaha/${tax//-/_}.json
done
```

- [ ] **Step 2: Write the failing test**

```python
"""Tests for growomaha.taxonomies."""
import json
import pytest
from sources.growomaha.taxonomies import (
    parse_day_of_week, parse_time_slots, time_slot_to_24h,
)


@pytest.fixture
def dow_raw(fixtures_dir):
    return json.loads((fixtures_dir / "growomaha" / "day_of_week.json").read_text())


@pytest.fixture
def ts_raw(fixtures_dir):
    return json.loads((fixtures_dir / "growomaha" / "time_slots.json").read_text())


def test_parse_day_of_week_maps_ids_to_short_codes(dow_raw):
    m = parse_day_of_week(dow_raw)
    assert m[161] == "mon"
    assert m[147] == "tue"
    assert m[141] == "fri"


def test_time_slot_to_24h_handles_slugs():
    assert time_slot_to_24h("300pm") == "15:00"
    assert time_slot_to_24h("1030am") == "10:30"
    assert time_slot_to_24h("1200pm") == "12:00"
    assert time_slot_to_24h("1200am") == "00:00"
    assert time_slot_to_24h("100am") == "01:00"


def test_time_slot_to_24h_rejects_garbage():
    with pytest.raises(ValueError):
        time_slot_to_24h("9999xx")
    with pytest.raises(ValueError):
        time_slot_to_24h("")


def test_parse_time_slots_returns_id_to_24h_map(ts_raw):
    m = parse_time_slots(ts_raw)
    pm3 = [k for k, v in m.items() if v == "15:00"]
    assert len(pm3) >= 1
```

- [ ] **Step 3: Run, expect ImportError**

- [ ] **Step 4: Implement `sources/growomaha/taxonomies.py`**

```python
"""Taxonomy lookups for growomaha WP REST API."""
from __future__ import annotations
import re

DAY_NAME_TO_CODE = {
    "monday": "mon", "tuesday": "tue", "wednesday": "wed",
    "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun",
}
SLOT_RE = re.compile(r"^(\d{1,2})(\d{2})(am|pm)$")


def parse_day_of_week(records: list[dict]) -> dict[int, str]:
    out = {}
    for r in records:
        name = r["name"].strip().lower()
        if name in DAY_NAME_TO_CODE:
            out[r["id"]] = DAY_NAME_TO_CODE[name]
    return out


def time_slot_to_24h(slug: str) -> str:
    m = SLOT_RE.match(slug.lower())
    if not m:
        raise ValueError(f"bad time slot slug: {slug!r}")
    hh, mm, ampm = m.group(1), m.group(2), m.group(3)
    h = int(hh)
    if not (0 <= int(mm) < 60) or not (1 <= h <= 12):
        raise ValueError(f"bad time slot slug: {slug!r}")
    if ampm == "am":
        h = 0 if h == 12 else h
    else:
        h = 12 if h == 12 else h + 12
    return f"{h:02d}:{mm}"


def parse_time_slots(records: list[dict]) -> dict[int, str]:
    out = {}
    for r in records:
        try:
            out[r["id"]] = time_slot_to_24h(r["slug"])
        except ValueError:
            continue
    return out
```

- [ ] **Step 5: Run + commit**

```bash
pytest tests/test_growomaha_taxonomies.py -v
git add sources/growomaha/taxonomies.py tests/fixtures/growomaha/ tests/test_growomaha_taxonomies.py
git commit -m "feat(growomaha): taxonomy ID-to-label resolver

Refs: omaha-deals-map"
```

---

### Task 7: growomaha fetch

**Files:**
- Modify: `sources/growomaha/fetch.py`
- Create: `tests/fixtures/growomaha/page{1,2,3}.json`
- Create: `tests/test_growomaha_fetch.py`

- [ ] **Step 1: Capture page fixtures**

```bash
for p in 1 2 3; do
  curl -sS "https://growomaha.com/wp-json/wp/v2/happy-hour?per_page=100&page=$p" \
    > tests/fixtures/growomaha/page${p}.json
done
```

- [ ] **Step 2: Write the failing test**

```python
"""Tests for growomaha.fetch."""
import json
from unittest.mock import MagicMock
import pytest
from sources.growomaha.fetch import fetch, GrowomahaPayload


def test_fetch_paginates_until_no_records(fixtures_dir):
    pages = {p: json.loads((fixtures_dir / "growomaha" / f"page{p}.json").read_text())
             for p in (1, 2, 3)}
    taxonomies = {
        "day-of-week": json.loads((fixtures_dir / "growomaha" / "day_of_week.json").read_text()),
        "time-slots":  json.loads((fixtures_dir / "growomaha" / "time_slots.json").read_text()),
        "cities":      json.loads((fixtures_dir / "growomaha" / "cities.json").read_text()),
        "features":    json.loads((fixtures_dir / "growomaha" / "features.json").read_text()),
    }

    def fake_get(url):
        resp = MagicMock()
        resp.status_code = 200
        if "/happy-hour" in url:
            page = int(url.split("page=")[1].split("&")[0])
            body = pages.get(page, [])
        else:
            tax = url.rsplit("/", 1)[-1].split("?")[0]
            body = taxonomies[tax]
        resp.body = json.dumps(body).encode()
        resp.changed = True
        return resp

    client = MagicMock(); client.get = fake_get
    payload = fetch(client=client)
    assert isinstance(payload, GrowomahaPayload)
    assert len(payload.records) >= 200
    assert payload.day_of_week[161] == "mon"
```

- [ ] **Step 3: Run, expect failure**

- [ ] **Step 4: Implement `sources/growomaha/fetch.py`**

```python
"""growomaha REST API fetcher."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from scripts._lib.http_cache import CachedHttpClient
from sources.growomaha.taxonomies import parse_day_of_week, parse_time_slots

BASE = "https://growomaha.com/wp-json/wp/v2"
PER_PAGE = 100


@dataclass
class GrowomahaPayload:
    records: list[dict]
    day_of_week: dict[int, str]
    time_slots: dict[int, str]
    cities: dict[int, str]
    features: dict[int, str]


def _fetch_taxonomy(client, name: str) -> list[dict]:
    resp = client.get(f"{BASE}/{name}?per_page=100")
    return json.loads(resp.body)


def fetch(client: CachedHttpClient | None = None,
          cache_path: Path | None = None) -> GrowomahaPayload:
    if client is None:
        client = CachedHttpClient(cache_path or Path("data/http_cache.yaml"))
    records: list[dict] = []
    page = 1
    while True:
        resp = client.get(f"{BASE}/happy-hour?per_page={PER_PAGE}&page={page}")
        try:
            body = json.loads(resp.body)
        except json.JSONDecodeError:
            break
        if not isinstance(body, list) or len(body) == 0:
            break
        records.extend(body)
        if len(body) < PER_PAGE:
            break
        page += 1

    return GrowomahaPayload(
        records=records,
        day_of_week=parse_day_of_week(_fetch_taxonomy(client, "day-of-week")),
        time_slots=parse_time_slots(_fetch_taxonomy(client, "time-slots")),
        cities={r["id"]: r["name"] for r in _fetch_taxonomy(client, "cities")},
        features={r["id"]: r["name"] for r in _fetch_taxonomy(client, "features")},
    )
```

- [ ] **Step 5: Run + commit**

```bash
pytest tests/test_growomaha_fetch.py -v
git add sources/growomaha/fetch.py tests/fixtures/growomaha/page*.json tests/test_growomaha_fetch.py
git commit -m "feat(growomaha): paginated REST fetch + taxonomy wiring

Refs: omaha-deals-map"
```

---

### Task 8: growomaha parse

**Files:**
- Modify: `sources/growomaha/parse.py`
- Create: `tests/test_growomaha_parse.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for growomaha.parse."""
from sources.growomaha.fetch import GrowomahaPayload
from sources.growomaha.parse import parse


SAMPLE = {
    "id": 12345, "slug": "blue-sky-patio",
    "title": {"rendered": "Blue Sky Patio"},
    "link": "https://growomaha.com/happy-hour/blue-sky-patio/",
    "modified_gmt": "2026-05-08T16:00:57",
    "excerpt": {"rendered": "<p>Monday-Friday from 3-6 PM</p>"},
    "content": {"rendered": "<p>Monday-Friday from 3-6 PM. $5 wells.</p>"},
    "day-of-week": [161, 147, 148, 146, 141],
    "time-slots": [168, 169],
    "cities": [143],
}


def _payload(rec):
    return GrowomahaPayload(
        records=[rec],
        day_of_week={161: "mon", 147: "tue", 148: "wed", 146: "thu",
                     141: "fri", 144: "sat", 145: "sun"},
        time_slots={168: "15:00", 169: "15:30"},
        cities={143: "Omaha"}, features={},
    )


def test_parse_emits_source_record_with_pre_extracted_windows():
    records = parse(_payload(SAMPLE))
    r = records[0]
    assert r.source == "growomaha" and r.source_record_id == "blue-sky-patio"
    assert r.kind == "happy_hour"
    assert r.record_modified_at == "2026-05-08T16:00:57Z"
    starts = {w.day: w.start for w in r.pre_extracted_windows}
    assert starts == {"mon": "15:00", "tue": "15:00", "wed": "15:00",
                      "thu": "15:00", "fri": "15:00"}


def test_parse_strips_html_entities_in_name():
    rec = {**SAMPLE, "title": {"rendered": "Addy&#8217;s Sports Bar"}}
    assert parse(_payload(rec))[0].name == "Addy's Sports Bar"


def test_parse_excerpt_used_as_raw_text():
    assert "Monday-Friday from 3-6 PM" in parse(_payload(SAMPLE))[0].raw_text
```

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: Implement `sources/growomaha/parse.py`**

```python
"""Convert a GrowomahaPayload into SourceRecord rows."""
from __future__ import annotations
import re
import html
from sources._common import SourceRecord, Window, slugify
from sources.growomaha.fetch import GrowomahaPayload

HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip(s: str) -> str:
    return html.unescape(HTML_TAG_RE.sub("", s)).strip()


def _earliest(slot_ids, time_slots) -> str | None:
    times = sorted(time_slots[t] for t in slot_ids if t in time_slots)
    return times[0] if times else None


def parse(payload: GrowomahaPayload) -> list[SourceRecord]:
    out = []
    for rec in payload.records:
        name = _strip(rec["title"]["rendered"])
        slug = rec.get("slug") or slugify(name)
        modified = rec.get("modified_gmt", "")
        if modified and not modified.endswith("Z"):
            modified += "Z"
        day_ids = rec.get("day-of-week", [])
        slot_ids = rec.get("time-slots", [])
        days = [payload.day_of_week[d] for d in day_ids if d in payload.day_of_week]
        start = _earliest(slot_ids, payload.time_slots)
        windows = [Window(day=d, start=start) for d in days if start]
        out.append(SourceRecord(
            source="growomaha",
            source_record_id=slug,
            source_url=rec.get("link", ""),
            name=name,
            record_modified_at=modified,
            kind="happy_hour",
            raw_text=_strip(rec.get("excerpt", {}).get("rendered", "")),
            pre_extracted_windows=windows,
        ))
    return out
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_growomaha_parse.py -v
git add sources/growomaha/parse.py tests/test_growomaha_parse.py
git commit -m "feat(growomaha): parse WP records into SourceRecords

Refs: omaha-deals-map"
```

---

### Task 9: growomaha integration smoke

**Files:**
- Create: `tests/test_growomaha_integration.py`

- [ ] **Step 1: Register `slow` marker in `pyproject.toml`**

Under `[tool.pytest.ini_options]` add:

```toml
markers = [
    "slow: tests that hit live external services",
]
```

- [ ] **Step 2: Write the test**

```python
"""Live integration test for growomaha."""
import pytest
from scripts._lib.http_cache import CachedHttpClient
from sources.growomaha.fetch import fetch
from sources.growomaha.parse import parse

pytestmark = pytest.mark.slow


def test_live_fetch_parses_at_least_200_records(tmp_path):
    client = CachedHttpClient(cache_path=tmp_path / "http_cache.yaml")
    payload = fetch(client=client)
    records = parse(payload)
    assert len(records) >= 200
    with_window = sum(1 for r in records if r.pre_extracted_windows)
    assert with_window / len(records) >= 0.8
```

- [ ] **Step 3: Run + commit**

```bash
pytest -m slow tests/test_growomaha_integration.py -v
git add tests/test_growomaha_integration.py pyproject.toml
git commit -m "test(growomaha): live integration smoke (slow marker)

Refs: omaha-deals-map"
```

---

## Phase 4: visitomaha source

### Task 10: visitomaha fetch

**Files:**
- Modify: `sources/visitomaha/fetch.py`
- Create: `tests/fixtures/visitomaha/offers.json`
- Create: `tests/test_visitomaha_fetch.py`

- [ ] **Step 1: Capture fixture**

```bash
mkdir -p tests/fixtures/visitomaha
curl -sS 'https://www.visitomaha.com/includes/rest_v2/plugins_offers_offers/find/?json=%7B%22filter%22%3A%7B%22%24and%22%3A%5B%7B%22categories.categoryid%22%3A%7B%22%24in%22%3A%5B1%2C3%2C4%2C9%2C2%2C7%5D%7D%7D%2C%7B%22filter_tags%22%3A%7B%22%24in%22%3A%5B%22site_primary%22%5D%7D%7D%5D%7D%2C%22options%22%3A%7B%22limit%22%3A100%2C%22skip%22%3A0%2C%22count%22%3Atrue%7D%7D&token=7d890807f6e33bbfee82427523fda90c' \
  > tests/fixtures/visitomaha/offers.json
```

- [ ] **Step 2: Write the failing test**

```python
"""Tests for visitomaha.fetch."""
from unittest.mock import MagicMock
from sources.visitomaha.fetch import fetch, VisitomahaPayload


def test_fetch_returns_records_count_and_url(fixtures_dir):
    raw = (fixtures_dir / "visitomaha" / "offers.json").read_bytes()
    client = MagicMock()
    client.get = lambda url: type("R", (), {"body": raw, "status_code": 200})()
    payload = fetch(client=client)
    assert isinstance(payload, VisitomahaPayload)
    assert payload.total_count >= 1
    assert len(payload.records) >= 1
    assert payload.source_url.startswith("https://www.visitomaha.com/")
```

- [ ] **Step 3: Run, expect failure**

- [ ] **Step 4: Implement `sources/visitomaha/fetch.py`**

```python
"""visitomaha REST API fetcher."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from scripts._lib.http_cache import CachedHttpClient

_QUERY = {
    "filter": {
        "$and": [
            {"categories.categoryid": {"$in": [1, 3, 4, 9, 2, 7]}},
            {"filter_tags": {"$in": ["site_primary"]}},
        ]
    },
    "options": {"limit": 100, "skip": 0, "count": True,
                "sort": {"qualityScore": -1, "title_sort": 1}},
}
_TOKEN = "7d890807f6e33bbfee82427523fda90c"
_URL = (
    "https://www.visitomaha.com/includes/rest_v2/plugins_offers_offers/find/"
    f"?json={quote(json.dumps(_QUERY, separators=(',', ':')))}"
    f"&token={_TOKEN}"
)


@dataclass
class VisitomahaPayload:
    records: list[dict]
    total_count: int
    source_url: str


def fetch(client: CachedHttpClient | None = None,
          cache_path: Path | None = None) -> VisitomahaPayload:
    if client is None:
        client = CachedHttpClient(cache_path or Path("data/http_cache.yaml"))
    resp = client.get(_URL)
    body = json.loads(resp.body)
    docs = body["docs"]
    return VisitomahaPayload(
        records=docs["docs"],
        total_count=docs.get("count", len(docs["docs"])),
        source_url=_URL,
    )
```

- [ ] **Step 5: Run + commit**

```bash
pytest tests/test_visitomaha_fetch.py -v
git add sources/visitomaha/fetch.py tests/fixtures/visitomaha/ tests/test_visitomaha_fetch.py
git commit -m "feat(visitomaha): REST offers fetcher

Refs: omaha-deals-map"
```

---

### Task 11: visitomaha parse

**Files:**
- Modify: `sources/visitomaha/parse.py`
- Create: `tests/test_visitomaha_parse.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for visitomaha.parse."""
from sources.visitomaha.fetch import VisitomahaPayload
from sources.visitomaha.parse import parse


SAMPLE = {
    "_id": "abc", "recid": "1628",
    "title": "$3 off Bike Share",
    "description": "Use promo VISITOMA26.",
    "poststart": "2024-01-02T05:00:00.000Z",
    "postend":   "2027-01-01T04:59:59.000Z",
    "updated":   "2026-06-04T12:30:37.643Z",
    "offerlink": "https://heartlandbikeshare.org",
    "url": "/coupon/heartland/1628/",
    "listings": [{"latitude": 41.26, "longitude": -95.93, "title": "Heartland Bike Share"}],
}


def test_parse_emits_special_record():
    p = VisitomahaPayload(records=[SAMPLE], total_count=1, source_url="https://x")
    r = parse(p)[0]
    assert r.kind == "special" and r.source == "visitomaha"
    assert r.source_record_id == "1628"
    assert r.valid_from == "2024-01-02" and r.valid_until == "2027-01-01"
    assert r.lat == 41.26 and r.lng == -95.93
    assert r.name == "Heartland Bike Share"


def test_parse_falls_back_to_title_when_listings_empty():
    rec = {**SAMPLE, "listings": []}
    r = parse(VisitomahaPayload(records=[rec], total_count=1, source_url=""))[0]
    assert r.name == rec["title"]
    assert r.lat is None
```

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: Implement `sources/visitomaha/parse.py`**

```python
"""Convert VisitomahaPayload into SourceRecord rows."""
from __future__ import annotations
from sources._common import SourceRecord
from sources.visitomaha.fetch import VisitomahaPayload


def _date_only(ts: str | None) -> str | None:
    return ts.split("T", 1)[0] if ts else None


def parse(payload: VisitomahaPayload) -> list[SourceRecord]:
    out = []
    for rec in payload.records:
        listings = rec.get("listings") or []
        venue = listings[0] if listings else None
        name = (venue["title"] if venue and "title" in venue else rec.get("title", "")).strip()
        out.append(SourceRecord(
            source="visitomaha",
            source_record_id=str(rec.get("recid", rec.get("_id", ""))),
            source_url="https://www.visitomaha.com" + rec.get("url", ""),
            name=name,
            record_modified_at=rec.get("updated", ""),
            kind="special",
            raw_text=rec.get("description", ""),
            external_link=rec.get("offerlink"),
            title=rec.get("title"),
            description=rec.get("description"),
            valid_from=_date_only(rec.get("poststart")),
            valid_until=_date_only(rec.get("postend")),
            lat=(venue or {}).get("latitude"),
            lng=(venue or {}).get("longitude"),
        ))
    return out
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_visitomaha_parse.py -v
git add sources/visitomaha/parse.py tests/test_visitomaha_parse.py
git commit -m "feat(visitomaha): parse offers into 'special' SourceRecords

Refs: omaha-deals-map"
```

---

### Task 12: visitomaha integration smoke

**Files:**
- Create: `tests/test_visitomaha_integration.py`

- [ ] **Step 1: Write + run + commit**

```python
"""Live integration test for visitomaha."""
import pytest
from scripts._lib.http_cache import CachedHttpClient
from sources.visitomaha.fetch import fetch
from sources.visitomaha.parse import parse

pytestmark = pytest.mark.slow


def test_live_fetch_parses(tmp_path):
    client = CachedHttpClient(cache_path=tmp_path / "http_cache.yaml")
    records = parse(fetch(client=client))
    assert len(records) >= 1
    assert all(r.kind == "special" for r in records)
```

```bash
pytest -m slow tests/test_visitomaha_integration.py -v
git add tests/test_visitomaha_integration.py
git commit -m "test(visitomaha): live integration smoke

Refs: omaha-deals-map"
```

---

## Phase 5: bigdealsmedia source

### Task 13: bigdealsmedia fetch

**Files:**
- Modify: `sources/bigdealsmedia/fetch.py`
- Create: `tests/fixtures/bigdealsmedia/restaurants.html`
- Create: `tests/test_bigdealsmedia_fetch.py`

- [ ] **Step 1: Capture fixture**

```bash
mkdir -p tests/fixtures/bigdealsmedia
curl -sS "https://omaha.bigdealsmedia.net/category/restaurants" \
  > tests/fixtures/bigdealsmedia/restaurants.html
```

- [ ] **Step 2: Write the failing test**

```python
"""Tests for bigdealsmedia.fetch."""
from unittest.mock import MagicMock
from sources.bigdealsmedia.fetch import fetch, BigDealsPayload


def test_fetch_returns_html_payload(fixtures_dir):
    raw = (fixtures_dir / "bigdealsmedia" / "restaurants.html").read_bytes()
    client = MagicMock()
    client.get = lambda url: type("R", (), {"body": raw, "status_code": 200})()
    payload = fetch(client=client)
    assert isinstance(payload, BigDealsPayload)
    assert payload.html.startswith(b"<")
    assert payload.fetched_at
```

- [ ] **Step 3: Run, expect failure**

- [ ] **Step 4: Implement `sources/bigdealsmedia/fetch.py`**

```python
"""bigdealsmedia HTML fetcher (SSR)."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from scripts._lib.http_cache import CachedHttpClient

_URL = "https://omaha.bigdealsmedia.net/category/restaurants"


@dataclass
class BigDealsPayload:
    html: bytes
    source_url: str
    fetched_at: str


def fetch(client: CachedHttpClient | None = None,
          cache_path: Path | None = None) -> BigDealsPayload:
    if client is None:
        client = CachedHttpClient(cache_path or Path("data/http_cache.yaml"))
    resp = client.get(_URL)
    return BigDealsPayload(
        html=resp.body,
        source_url=_URL,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
```

- [ ] **Step 5: Run + commit**

```bash
pytest tests/test_bigdealsmedia_fetch.py -v
git add sources/bigdealsmedia/fetch.py tests/fixtures/bigdealsmedia/ tests/test_bigdealsmedia_fetch.py
git commit -m "feat(bigdealsmedia): SSR HTML fetcher

Refs: omaha-deals-map"
```

---

### Task 14: bigdealsmedia parse

**Files:**
- Modify: `sources/bigdealsmedia/parse.py`
- Create: `tests/test_bigdealsmedia_parse.py`

The site renders SSR HTML before its SPA hydrates. Each restaurant card has a name and a price block. The selectors below may need adjustment after you inspect the actual fixture; the tests pin behavior, not specific selectors.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for bigdealsmedia.parse."""
import pytest
from sources.bigdealsmedia.fetch import BigDealsPayload
from sources.bigdealsmedia.parse import parse


def test_parse_extracts_at_least_one_voucher(fixtures_dir):
    html = (fixtures_dir / "bigdealsmedia" / "restaurants.html").read_bytes()
    p = BigDealsPayload(html=html, source_url="https://x", fetched_at="2026-06-06T00:00:00Z")
    records = parse(p)
    assert len(records) >= 1
    r = records[0]
    assert r.source == "bigdealsmedia"
    assert r.kind == "voucher"
    assert r.original_price is not None and r.sale_price is not None
    assert r.savings == pytest.approx(r.original_price - r.sale_price, abs=0.01)
    assert r.name


def test_parse_skips_non_priced_cards(fixtures_dir):
    html = (fixtures_dir / "bigdealsmedia" / "restaurants.html").read_bytes()
    records = parse(BigDealsPayload(html=html, source_url="https://x", fetched_at="2026-06-06T00:00:00Z"))
    names = {r.name.lower() for r in records}
    assert "sign in" not in names and "sign up" not in names and "cart" not in names
```

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: Implement `sources/bigdealsmedia/parse.py`**

```python
"""Convert bigdealsmedia HTML into SourceRecord rows."""
from __future__ import annotations
import re
from bs4 import BeautifulSoup
from sources._common import SourceRecord, slugify
from sources.bigdealsmedia.fetch import BigDealsPayload

PRICE_RE = re.compile(r"\$(\d+(?:\.\d{2})?)")


def _extract_prices(text: str):
    matches = [float(m) for m in PRICE_RE.findall(text)]
    if len(matches) < 2:
        return None, None, None
    original, sale = matches[0], matches[1]
    if original <= sale:
        return None, None, None
    return original, sale, round(original - sale, 2)


def parse(payload: BigDealsPayload) -> list[SourceRecord]:
    soup = BeautifulSoup(payload.html, "html.parser")
    out = []
    seen = set()
    for card in soup.select("[class*='product'], [class*='deal']"):
        text = card.get_text(separator=" ", strip=True)
        original, sale, savings = _extract_prices(text)
        if not original:
            continue
        name_el = card.select_one("h1, h2, h3, h4, h5, .title, .name, [class*='title']")
        name = name_el.get_text(strip=True) if name_el else text.split("$", 1)[0].strip()
        if not name or len(name) > 120:
            continue
        sid = slugify(name)
        if sid in seen:
            continue
        seen.add(sid)
        out.append(SourceRecord(
            source="bigdealsmedia",
            source_record_id=sid,
            source_url=payload.source_url,
            name=name,
            record_modified_at=payload.fetched_at,
            kind="voucher",
            raw_text=text[:500],
            original_price=original,
            sale_price=sale,
            savings=savings,
            category="restaurants",
        ))
    return out
```

- [ ] **Step 4: Run, iterate selectors until PASS**

Open `tests/fixtures/bigdealsmedia/restaurants.html` and check the actual class names around the price blocks. Adjust `card.select(...)` if the test extracts 0.

- [ ] **Step 5: Commit**

```bash
git add sources/bigdealsmedia/parse.py tests/test_bigdealsmedia_parse.py
git commit -m "feat(bigdealsmedia): parse SSR HTML into voucher SourceRecords

Refs: omaha-deals-map"
```

---

### Task 15: bigdealsmedia integration smoke

**Files:**
- Create: `tests/test_bigdealsmedia_integration.py`

- [ ] **Step 1: Write + run + commit**

```python
"""Live integration test for bigdealsmedia."""
import pytest
from scripts._lib.http_cache import CachedHttpClient
from sources.bigdealsmedia.fetch import fetch
from sources.bigdealsmedia.parse import parse

pytestmark = pytest.mark.slow


def test_live_fetch_parses(tmp_path):
    client = CachedHttpClient(cache_path=tmp_path / "http_cache.yaml")
    records = parse(fetch(client=client))
    assert len(records) >= 5
    assert all(r.kind == "voucher" for r in records)
```

```bash
pytest -m slow tests/test_bigdealsmedia_integration.py -v
git add tests/test_bigdealsmedia_integration.py
git commit -m "test(bigdealsmedia): live integration smoke

Refs: omaha-deals-map"
```

---

## Phase 6: Pipeline scripts

### Task 16: `01_fetch.py` orchestrator

**Files:**
- Create: `scripts/_fetch_main.py`
- Create: `scripts/01_fetch.py`
- Create: `tests/test_01_fetch.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the fetch orchestrator."""
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_main_calls_fetch_for_each_registered_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    called = []

    class FakeMod:
        def __init__(self, n): self.n = n
        def fetch(self, client=None, cache_path=None):
            called.append(self.n)
            r = MagicMock()
            r.records = [{"id": 1}]
            return r

    active = type("X", (), {
        "names": ["growomaha", "visitomaha"],
        "modules": [FakeMod("growomaha"), FakeMod("visitomaha")],
    })

    from scripts import _fetch_main
    with patch("scripts._fetch_main.load_active_sources", return_value=active):
        _fetch_main.main()
    assert called == ["growomaha", "visitomaha"]
```

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: Implement `scripts/_fetch_main.py`**

```python
"""01_fetch entry point factored for testability."""
from __future__ import annotations
import argparse
import pickle
from datetime import datetime, timezone
from pathlib import Path
from scripts._lib.http_cache import CachedHttpClient
from scripts._lib.io import write_yaml
from sources._registry import load_active_sources


def main(force: bool = False) -> int:
    raw_dir = Path("data/raw"); raw_dir.mkdir(parents=True, exist_ok=True)
    cache_path = Path("data/http_cache.yaml")
    client = CachedHttpClient(cache_path=cache_path)

    summary = {}
    active = load_active_sources()
    for name, mod in zip(active.names, active.modules):
        print(f"[fetch] {name}...", flush=True)
        src_dir = raw_dir / name; src_dir.mkdir(exist_ok=True)
        try:
            payload = mod.fetch(client=client, cache_path=cache_path)
        except Exception as e:
            print(f"[fetch] {name} FAILED: {e}")
            summary[name] = {"ok": False, "error": str(e)}
            continue
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snap = src_dir / f"{ts}.pickle"
        snap.write_bytes(pickle.dumps(payload))
        latest = src_dir / "latest.pickle"
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.symlink_to(snap.name)
        n = len(getattr(payload, "records", []))
        summary[name] = {"ok": True, "snapshot": str(snap), "records": n}
        print(f"[fetch] {name}: {n} records")

    write_yaml(Path("data/fetch_summary.yaml"), summary)
    bad = [n for n, v in summary.items() if not v["ok"]]
    return 1 if bad and not force else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    raise SystemExit(main(force=ap.parse_args().force))
```

```python
# scripts/01_fetch.py
import argparse, sys
from scripts._fetch_main import main
ap = argparse.ArgumentParser(); ap.add_argument("--force", action="store_true")
sys.exit(main(force=ap.parse_args().force))
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_01_fetch.py -v
git add scripts/_fetch_main.py scripts/01_fetch.py tests/test_01_fetch.py
git commit -m "feat(pipeline): 01_fetch orchestrator with per-source snapshots

Refs: omaha-deals-map"
```

---

### Task 17: `02_parse.py` orchestrator

**Files:**
- Create: `scripts/_parse_main.py`
- Create: `scripts/02_parse.py`
- Create: `tests/test_02_parse.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for parse orchestrator."""
import pickle
from pathlib import Path
from unittest.mock import patch
from sources._common import SourceRecord


def test_parse_concatenates_all_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/raw/foo").mkdir(parents=True)
    Path("data/raw/foo/latest.pickle").write_bytes(pickle.dumps({"x": 1}))
    Path("data/raw/bar").mkdir()
    Path("data/raw/bar/latest.pickle").write_bytes(pickle.dumps({"y": 2}))

    class FakeMod:
        def __init__(self, n): self.n = n
        def parse(self, p):
            return [SourceRecord(
                source=self.n, source_record_id=f"{self.n}-1",
                source_url="x", name=f"{self.n} R",
                record_modified_at="2026-01-01T00:00:00Z", kind="happy_hour",
            )]

    active = type("X", (), {"names": ["foo", "bar"],
                            "modules": [FakeMod("foo"), FakeMod("bar")]})

    from scripts import _parse_main
    with patch("scripts._parse_main.load_active_sources", return_value=active):
        _parse_main.main()

    import yaml
    parsed = yaml.safe_load(Path("data/parsed.yaml").read_text())
    assert len(parsed) == 2
    assert {r["source"] for r in parsed} == {"foo", "bar"}
```

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: Implement `scripts/_parse_main.py`**

```python
"""Pipeline stage 2: parse latest snapshots into a unified parsed.yaml."""
from __future__ import annotations
import argparse
import pickle
from pathlib import Path
from scripts._lib.io import read_yaml, write_yaml
from sources._registry import load_active_sources


def main(force: bool = False) -> int:
    active = load_active_sources()
    out = []
    for name, mod in zip(active.names, active.modules):
        snap = Path(f"data/raw/{name}/latest.pickle")
        if not snap.exists():
            print(f"[parse] {name}: no snapshot, skipping")
            continue
        records = mod.parse(pickle.loads(snap.read_bytes()))
        print(f"[parse] {name}: {len(records)} records")
        out.extend(r.to_dict() for r in records)

    prior = read_yaml(Path("data/parsed.yaml"), default=[])
    if prior and not force and len(out) < len(prior) * 0.5:
        print(f"[parse] ABORT: new count {len(out)} < 50% of prior {len(prior)}; use --force")
        return 2
    write_yaml(Path("data/parsed.yaml"), out)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--force", action="store_true")
    raise SystemExit(main(force=ap.parse_args().force))
```

```python
# scripts/02_parse.py
import argparse, sys
from scripts._parse_main import main
ap = argparse.ArgumentParser(); ap.add_argument("--force", action="store_true")
sys.exit(main(force=ap.parse_args().force))
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_02_parse.py -v
git add scripts/_parse_main.py scripts/02_parse.py tests/test_02_parse.py
git commit -m "feat(pipeline): 02_parse with shrink guard

Refs: omaha-deals-map"
```

---

### Task 18: `03_extract_times.py` regex layer

**Files:**
- Create: `scripts/_lib/time_extractor.py`
- Create: `tests/test_time_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for time-window regex extractor."""
import pytest
from scripts._lib.time_extractor import extract_end_time, ExtractResult


@pytest.mark.parametrize("text, start, expected_end", [
    ("Monday-Friday from 3-6 PM", "15:00", "18:00"),
    ("Mon-Fri 3 - 6 PM", "15:00", "18:00"),
    ("4-6 PM", "16:00", "18:00"),
    ("from 4:30-6 PM", "16:30", "18:00"),
    ("11AM-5PM", "11:00", "17:00"),
    ("3pm to 6pm", "15:00", "18:00"),
])
def test_extract_end_time_matches_simple_ranges(text, start, expected_end):
    r = extract_end_time(text, start_hint=start)
    assert r.end == expected_end
    assert r.confidence == "high"


def test_extract_end_time_handles_until():
    r = extract_end_time("Happy Hour deals until 7 PM daily", start_hint="15:00")
    assert r.end == "19:00"


def test_extract_end_time_returns_none_when_no_match():
    r = extract_end_time("Daily, see menu for details", start_hint="15:00")
    assert r.end is None
    assert r.confidence == "none"


def test_reverse_hh_detection():
    r = extract_end_time("Reverse HH Friday 9-11 PM", start_hint="21:00")
    assert r.is_reverse is True
    assert r.end == "23:00"
```

- [ ] **Step 2: Run, expect ImportError**

- [ ] **Step 3: Implement `scripts/_lib/time_extractor.py`**

```python
"""Extract window end times from free-form deal prose."""
from __future__ import annotations
import re
from dataclasses import dataclass

RANGE_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*[-–]\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
    re.IGNORECASE,
)
TO_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s+to\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
    re.IGNORECASE,
)
UNTIL_RE = re.compile(r"until\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.IGNORECASE)
REVERSE_RE = re.compile(r"reverse", re.IGNORECASE)


@dataclass
class ExtractResult:
    end: str | None
    confidence: str  # high | medium | none
    is_reverse: bool = False


def _to_24h(h: int, m: int, ampm: str | None) -> str:
    ampm = (ampm or "pm").lower()
    if ampm == "am":
        h = 0 if h == 12 else h
    else:
        h = 12 if h == 12 else h + 12
    return f"{h:02d}:{m:02d}"


def _parse(m: re.Match):
    h1, m1, ap1, h2, m2, ap2 = m.groups()
    ap1 = ap1 or ap2
    return _to_24h(int(h1), int(m1 or 0), ap1), _to_24h(int(h2), int(m2 or 0), ap2)


def extract_end_time(text: str, *, start_hint: str | None = None) -> ExtractResult:
    is_reverse = bool(REVERSE_RE.search(text))
    for rx in (RANGE_RE, TO_RE):
        m = rx.search(text)
        if m:
            _, end = _parse(m)
            return ExtractResult(end=end, confidence="high", is_reverse=is_reverse)
    m = UNTIL_RE.search(text)
    if m:
        h, mm, ap = m.groups()
        return ExtractResult(end=_to_24h(int(h), int(mm or 0), ap),
                             confidence="medium", is_reverse=is_reverse)
    return ExtractResult(end=None, confidence="none", is_reverse=is_reverse)
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_time_extractor.py -v
git add scripts/_lib/time_extractor.py tests/test_time_extractor.py
git commit -m "feat(extractor): regex-based end-time extraction with reverse-HH

Refs: omaha-deals-map"
```

---

### Task 19: `03_extract_times.py` LLM fallback + cache

**Files:**
- Create: `scripts/_lib/llm_extractor.py`
- Create: `scripts/_extract_main.py`
- Create: `scripts/03_extract_times.py`
- Create: `tests/test_llm_extractor.py`
- Create: `tests/test_03_extract.py`

Token cost: ~$0.04 first run for the growomaha set, $0 thereafter (cached by SHA).

- [ ] **Step 1: Write the failing test for the LLM wrapper**

```python
"""Tests for the LLM extractor (mocked Anthropic client)."""
from unittest.mock import MagicMock
from scripts._lib.llm_extractor import extract_with_llm


def test_extract_with_llm_returns_end_time_and_caches(tmp_path):
    cache_path = tmp_path / "llm_cache.yaml"
    fake = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text='{"end_time": "18:00", "is_reverse_hh": false}')]
    fake.messages.create.return_value = msg

    r = extract_with_llm("Mon-Fri 3-6 PM", start_hint="15:00",
                         cache_path=cache_path, client=fake)
    assert r.end == "18:00" and r.is_reverse is False

    fake.messages.create.reset_mock()
    r2 = extract_with_llm("Mon-Fri 3-6 PM", start_hint="15:00",
                          cache_path=cache_path, client=fake)
    assert r2.end == "18:00"
    fake.messages.create.assert_not_called()


def test_extract_with_llm_handles_malformed_json(tmp_path):
    cache_path = tmp_path / "llm_cache.yaml"
    fake = MagicMock()
    msg = MagicMock(); msg.content = [MagicMock(text="i'm not json")]
    fake.messages.create.return_value = msg
    r = extract_with_llm("whatever", start_hint="15:00",
                         cache_path=cache_path, client=fake)
    assert r.end is None
```

- [ ] **Step 2: Run, expect ImportError**

- [ ] **Step 3: Implement `scripts/_lib/llm_extractor.py`**

```python
"""LLM fallback for end-time extraction. Cached by SHA(text)."""
from __future__ import annotations
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import yaml

MODEL = "claude-haiku-4-5-20251001"
SYSTEM_PROMPT = """You parse Omaha happy-hour deal text into structured end times.
Return ONLY a JSON object on one line with these keys:
  end_time: "HH:MM" 24h format, or null if you can't tell
  is_reverse_hh: true if the window is a reverse / late-night happy hour, else false
Do not include any other text."""


@dataclass
class LlmResult:
    end: str | None
    is_reverse: bool


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {} if path.exists() else {}


def _save(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cache, sort_keys=True))


def extract_with_llm(text: str, *, start_hint: str | None,
                     cache_path: Path, client=None) -> LlmResult:
    key = hashlib.sha256(f"{start_hint}|{text}".encode()).hexdigest()
    cache = _load(cache_path)
    if key in cache:
        c = cache[key]
        return LlmResult(end=c.get("end"), is_reverse=c.get("is_reverse", False))

    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    msg = client.messages.create(
        model=MODEL, max_tokens=80, system=SYSTEM_PROMPT,
        messages=[{"role": "user",
                   "content": f"Start time hint: {start_hint or 'unknown'}\n\nText:\n{text}"}],
    )
    raw = msg.content[0].text.strip()
    try:
        data = json.loads(raw)
        end = data.get("end_time")
        is_reverse = bool(data.get("is_reverse_hh", False))
    except (json.JSONDecodeError, KeyError):
        end, is_reverse = None, False

    cache[key] = {"end": end, "is_reverse": is_reverse}
    _save(cache_path, cache)
    return LlmResult(end=end, is_reverse=is_reverse)
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_llm_extractor.py -v
git add scripts/_lib/llm_extractor.py tests/test_llm_extractor.py
git commit -m "feat(llm): cached Claude Haiku end-time extractor

Refs: omaha-deals-map"
```

- [ ] **Step 5: Write the failing test for the extract orchestrator**

```python
"""Tests for 03_extract_times orchestrator."""
import yaml
from pathlib import Path
from sources._common import SourceRecord, Window


def test_extract_main_fills_end_times_from_regex(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data").mkdir()
    rec = SourceRecord(
        source="growomaha", source_record_id="x", source_url="x", name="X",
        record_modified_at="2026-01-01T00:00:00Z", kind="happy_hour",
        raw_text="Monday-Friday 3-6 PM",
        pre_extracted_windows=[Window(day="mon", start="15:00")],
    )
    yaml.safe_dump([rec.to_dict()], open("data/parsed.yaml", "w"))

    from scripts import _extract_main
    _extract_main.main()
    extracted = yaml.safe_load(open("data/extracted.yaml"))
    assert extracted[0]["pre_extracted_windows"][0]["end"] == "18:00"
    assert extracted[0].get("extraction_source") == "regex"
```

- [ ] **Step 6: Implement `scripts/_extract_main.py`**

```python
"""Pipeline stage 3: fill in window end times via regex, then LLM."""
from __future__ import annotations
import argparse
from pathlib import Path
from scripts._lib.io import read_yaml, write_yaml
from scripts._lib.time_extractor import extract_end_time


def main(force: bool = False) -> int:
    parsed = read_yaml(Path("data/parsed.yaml"), default=[])
    cache_path = Path("data/llm_cache.yaml")
    out = []
    for rec in parsed:
        if rec["kind"] != "happy_hour":
            rec["extraction_source"] = "n/a"
            out.append(rec); continue

        wins = rec.get("pre_extracted_windows") or []
        if wins and all(w.get("end") for w in wins):
            rec["extraction_source"] = "source_taxonomy"
            out.append(rec); continue

        text = rec.get("raw_text", "")
        start_hint = wins[0]["start"] if wins else None
        result = extract_end_time(text, start_hint=start_hint)

        if result.end is None and text:
            try:
                from scripts._lib.llm_extractor import extract_with_llm
                llm = extract_with_llm(text, start_hint=start_hint, cache_path=cache_path)
                if llm.end:
                    result = type(result)(end=llm.end, confidence="medium",
                                          is_reverse=llm.is_reverse)
            except (ImportError, KeyError):
                pass

        if result.end:
            for w in wins:
                w["end"] = result.end
                if result.is_reverse:
                    w["type"] = "reverse_hh"
            rec["extraction_source"] = "regex" if result.confidence == "high" else "llm"
            rec["needs_review"] = False
        else:
            rec["needs_review"] = True
            rec["extraction_source"] = "none"
        out.append(rec)

    write_yaml(Path("data/extracted.yaml"), out)
    print(f"[extract] {len(out)} records | needs_review: {sum(1 for r in out if r.get('needs_review'))}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--force", action="store_true")
    raise SystemExit(main(force=ap.parse_args().force))
```

```python
# scripts/03_extract_times.py
import argparse, sys
from scripts._extract_main import main
ap = argparse.ArgumentParser(); ap.add_argument("--force", action="store_true")
sys.exit(main(force=ap.parse_args().force))
```

- [ ] **Step 7: Run + commit**

```bash
pytest tests/test_03_extract.py -v
git add scripts/_extract_main.py scripts/03_extract_times.py tests/test_03_extract.py
git commit -m "feat(pipeline): 03_extract_times with regex + LLM fallback

Refs: omaha-deals-map"
```

---

### Task 20: `04_geocode.py`

**Files:**
- Create: `scripts/_geocode_main.py`
- Create: `scripts/04_geocode.py`
- Create: `tests/test_04_geocode.py`

Nominatim usage policy: max 1 req/sec, unique UA with contact info, cache results.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for geocode stage."""
import yaml
from pathlib import Path


def test_geocode_uses_override_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    yaml.safe_dump([{
        "source": "x", "source_record_id": "blue-sky", "kind": "happy_hour",
        "name": "Blue Sky", "source_url": "", "record_modified_at": ""
    }], open("data/extracted.yaml", "w"))
    yaml.safe_dump({"blue-sky": {"address": "1 Main St", "lat": 41.0, "lng": -95.0}},
                   open("data/overrides/addresses.yaml", "w"))

    from scripts import _geocode_main
    _geocode_main.main(geocoder=lambda n: None)
    out = yaml.safe_load(open("data/geocoded.yaml"))
    assert out[0]["lat"] == 41.0
    assert out[0]["address"] == "1 Main St"


def test_geocode_falls_back_to_geocoder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True)
    yaml.safe_dump([
        {"source": "x", "source_record_id": "a", "kind": "happy_hour",
         "name": "Place A", "source_url": "", "record_modified_at": ""},
        {"source": "x", "source_record_id": "b", "kind": "happy_hour",
         "name": "Place B", "source_url": "", "record_modified_at": ""},
    ], open("data/extracted.yaml", "w"))

    calls = []
    def geocoder(name):
        calls.append(name)
        return {"address": f"{name} addr", "lat": 41.25, "lng": -95.93,
                "category": "amenity"}

    from scripts import _geocode_main
    _geocode_main.main(geocoder=geocoder)
    assert calls == ["Place A", "Place B"]
    out = yaml.safe_load(open("data/geocoded.yaml"))
    assert all(r["geocode_confidence"] == "high" for r in out)
```

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: Implement `scripts/_geocode_main.py`**

```python
"""Pipeline stage 4: address + lat/lng via Nominatim w/ override + cache."""
from __future__ import annotations
import argparse
import time
from pathlib import Path
from typing import Callable
import requests
from scripts._lib.io import read_yaml, write_yaml

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "omaha-deals-map/0.1 (+https://github.com/nitrocode/omaha-deals-map)"
OMAHA_BBOX = (-96.4, 41.0, -95.5, 41.5)


def _nominatim(name: str) -> dict | None:
    time.sleep(1.0)
    r = requests.get(NOMINATIM_URL,
        params={"q": f"{name}, Omaha, NE", "format": "json", "limit": 1,
                "addressdetails": 1, "countrycodes": "us"},
        headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    results = r.json()
    if not results: return None
    top = results[0]
    return {"address": top.get("display_name", ""),
            "lat": float(top["lat"]), "lng": float(top["lon"]),
            "category": top.get("class", "")}


def _confidence(lat: float, lng: float, category: str) -> str:
    lng_min, lat_min, lng_max, lat_max = OMAHA_BBOX
    in_bbox = lng_min <= lng <= lng_max and lat_min <= lat <= lat_max
    if category in {"amenity", "shop", "leisure", "tourism"} and in_bbox:
        return "high"
    if in_bbox:
        return "medium"
    return "low"


def main(geocoder: Callable[[str], dict | None] | None = None) -> int:
    extracted = read_yaml(Path("data/extracted.yaml"), default=[])
    overrides = read_yaml(Path("data/overrides/addresses.yaml"), default={}) or {}
    cache = read_yaml(Path("data/geocode_cache.yaml"), default={}) or {}
    geocoder = geocoder or _nominatim

    out = []
    for rec in extracted:
        rid, name = rec["source_record_id"], rec["name"]
        if rid in overrides:
            o = overrides[rid]
            rec.update({"address": o["address"], "lat": o["lat"], "lng": o["lng"],
                        "geocode_confidence": "high", "geocode_source": "override"})
            out.append(rec); continue
        if rec.get("lat") is not None and rec.get("lng") is not None:
            rec["geocode_confidence"] = _confidence(rec["lat"], rec["lng"], "")
            rec["geocode_source"] = "source"; rec.setdefault("address", "")
            out.append(rec); continue
        if name in cache:
            rec.update({**cache[name], "geocode_source": "cache"})
            out.append(rec); continue
        try:
            hit = geocoder(name)
        except Exception as e:
            print(f"[geocode] {name}: {e}"); hit = None
        if hit:
            conf = _confidence(hit["lat"], hit["lng"], hit.get("category", ""))
            cache[name] = {**hit, "geocode_confidence": conf}
            rec.update({**hit, "geocode_confidence": conf, "geocode_source": "nominatim"})
            if conf == "low":
                rec["needs_review"] = True
        else:
            rec["needs_review"] = True; rec["geocode_confidence"] = "none"
        out.append(rec)

    write_yaml(Path("data/geocoded.yaml"), out)
    write_yaml(Path("data/geocode_cache.yaml"), cache)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--force", action="store_true")
    raise SystemExit(main())
```

```python
# scripts/04_geocode.py
import sys
from scripts._geocode_main import main
sys.exit(main())
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_04_geocode.py -v
git add scripts/_geocode_main.py scripts/04_geocode.py tests/test_04_geocode.py
git commit -m "feat(pipeline): 04_geocode with override + cache + Nominatim

Refs: omaha-deals-map"
```

---

### Task 21: `05_build.py`

**Files:**
- Create: `scripts/_build_main.py`
- Create: `scripts/05_build.py`
- Create: `tests/test_05_build.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for build stage."""
import json
import yaml
from pathlib import Path


SAMPLE = [
    {
        "source": "growomaha", "source_record_id": "blue-sky", "source_url": "u",
        "name": "Blue Sky Patio", "kind": "happy_hour", "raw_text": "Mon 3-6",
        "record_modified_at": "2026-01-01T00:00:00Z",
        "pre_extracted_windows": [{"day": "mon", "start": "15:00", "end": "18:00",
                                    "type": "happy_hour"}],
        "address": "1 Main", "lat": 41.25, "lng": -95.93,
        "geocode_confidence": "high",
    },
    {
        "source": "visitomaha", "source_record_id": "blue-sky", "source_url": "u2",
        "name": "Blue Sky Patio", "kind": "special", "raw_text": "",
        "record_modified_at": "2026-01-01T00:00:00Z",
        "title": "10% off", "valid_from": "2026-01-01", "valid_until": "2026-12-31",
        "address": "1 Main", "lat": 41.25, "lng": -95.93,
        "geocode_confidence": "high",
    },
]


def test_build_merges_same_restaurant_across_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True); Path("site").mkdir()
    yaml.safe_dump(SAMPLE, open("data/geocoded.yaml", "w"))
    yaml.safe_dump({}, open("data/overrides/categories.yaml", "w"))

    from scripts import _build_main
    _build_main.main()

    bundle = json.loads(open("data/deals.json").read_text())
    rests = bundle["restaurants"]
    assert len(rests) == 1
    assert len(rests[0]["deals"]) == 2
    assert {d["kind"] for d in rests[0]["deals"]} == {"happy_hour", "special"}
    assert json.loads(open("site/data.json").read_text()) == bundle


def test_build_applies_category_overrides(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/overrides").mkdir(parents=True); Path("site").mkdir()
    yaml.safe_dump([SAMPLE[0]], open("data/geocoded.yaml", "w"))
    yaml.safe_dump({"blue-sky": {"cuisine": ["american"], "neighborhood": "Aksarben"}},
                   open("data/overrides/categories.yaml", "w"))
    from scripts import _build_main
    _build_main.main()
    bundle = json.loads(open("data/deals.json").read_text())
    r = bundle["restaurants"][0]
    assert r["cuisine"] == ["american"] and r["neighborhood"] == "Aksarben"
```

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: Implement `scripts/_build_main.py`**

```python
"""Pipeline stage 5: merge by restaurant identity, apply overrides, emit deals.json."""
from __future__ import annotations
import argparse
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from scripts._lib.io import read_yaml, write_json

SCHEMA_VERSION = "1.0"


def _merge_key(rec: dict, merges: dict) -> str:
    rid = rec["source_record_id"]
    return merges.get(f"{rec['source']}:{rid}", rid)


def _deal(rec: dict) -> dict:
    base = {"kind": rec["kind"], "source": rec["source"],
            "source_url": rec["source_url"], "raw_text": rec.get("raw_text", "")}
    if (lk := rec.get("external_link")):
        base["external_link"] = lk
    if rec["kind"] == "happy_hour":
        base["windows"] = rec.get("pre_extracted_windows") or []
        base["highlights"] = rec.get("highlights", [])
    elif rec["kind"] == "special":
        base.update({"title": rec.get("title"), "description": rec.get("description"),
                     "valid_from": rec.get("valid_from"), "valid_until": rec.get("valid_until")})
    elif rec["kind"] == "voucher":
        base.update({"title": rec.get("title"),
                     "original_price": rec.get("original_price"),
                     "sale_price": rec.get("sale_price"),
                     "savings": rec.get("savings"), "category": rec.get("category")})
    return base


def main() -> int:
    geocoded = read_yaml(Path("data/geocoded.yaml"), default=[])
    categories = read_yaml(Path("data/overrides/categories.yaml"), default={}) or {}
    personal = read_yaml(Path("data/overrides/personal.yaml"), default={}) or {}
    merges = read_yaml(Path("data/overrides/merges.yaml"), default={}) or {}

    by_id: dict[str, list[dict]] = defaultdict(list)
    for rec in geocoded:
        by_id[_merge_key(rec, merges)].append(rec)

    summary = {}
    restaurants = []
    for rid, recs in sorted(by_id.items()):
        first = recs[0]
        restaurants.append({
            "id": rid, "name": first["name"],
            "address": first.get("address", ""),
            "lat": first.get("lat"), "lng": first.get("lng"),
            "geocode_confidence": first.get("geocode_confidence", "none"),
            "cuisine": categories.get(rid, {}).get("cuisine", []),
            "neighborhood": categories.get(rid, {}).get("neighborhood"),
            "personal": personal.get(rid, {}),
            "deals": [_deal(r) for r in recs],
            "needs_review": any(r.get("needs_review", False) for r in recs),
        })
        for r in recs:
            summary.setdefault(r["source"], {"count": 0})["count"] += 1

    bundle = {
        "schema_version": SCHEMA_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "sources": [{"name": k, **v} for k, v in summary.items()],
        "restaurants": restaurants,
    }
    out_path = Path("data/deals.json")
    write_json(out_path, bundle)
    Path("site").mkdir(exist_ok=True)
    shutil.copyfile(out_path, "site/data.json")
    print(f"[build] {len(restaurants)} restaurants, "
          f"{sum(len(r['deals']) for r in restaurants)} deals")
    print(f"[build] needs_review: {sum(1 for r in restaurants if r['needs_review'])}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--force", action="store_true")
    raise SystemExit(main())
```

```python
# scripts/05_build.py
import sys
from scripts._build_main import main
sys.exit(main())
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_05_build.py -v
git add scripts/_build_main.py scripts/05_build.py tests/test_05_build.py
git commit -m "feat(pipeline): 05_build merges sources, applies overrides, emits deals.json

Refs: omaha-deals-map"
```

---

## Phase 7: Static site

### Task 22: site/index.html

**Files:**
- Modify: `site/index.html` (replace placeholder)

- [ ] **Step 1: Replace contents**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#2c5aa0">
<title>Omaha Deals Map</title>
<link rel="stylesheet"
  href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
  crossorigin="">
<link rel="stylesheet" href="styles.css">
</head>
<body>
<header class="app-bar">
  <h1>Omaha Deals</h1>
  <button id="filter-btn" aria-label="Filters">filters</button>
</header>
<nav class="day-tabs" id="day-tabs" aria-label="Day of week">
  <button data-day="mon">M</button>
  <button data-day="tue">T</button>
  <button data-day="wed">W</button>
  <button data-day="thu">T</button>
  <button data-day="fri">F</button>
  <button data-day="sat">S</button>
  <button data-day="sun">S</button>
</nav>
<main id="map" aria-label="Map"></main>
<aside id="filter-sheet" class="sheet hidden" aria-hidden="true">
  <h2>Filters</h2>
  <fieldset>
    <legend>Show deals</legend>
    <label><input type="checkbox" data-kind="happy_hour" checked> Happy hours</label>
    <label><input type="checkbox" data-kind="special"> Specials</label>
    <label><input type="checkbox" data-kind="voucher"> Vouchers</label>
  </fieldset>
  <label><input type="checkbox" id="now-only"> Active now</label>
  <label><input type="checkbox" id="favorites-only"> Favorites only</label>
  <button id="close-filter">Done</button>
</aside>
<aside id="venue-sheet" class="sheet hidden" aria-hidden="true"></aside>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
  integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
  crossorigin=""></script>
<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add site/index.html
git commit -m "feat(site): mobile-first HTML scaffold with day tabs + filter sheet

Refs: omaha-deals-map"
```

---

### Task 23: site/styles.css

**Files:**
- Create: `site/styles.css`

- [ ] **Step 1: Write**

```css
:root {
    --bg: #f5f5f5;
    --primary: #2c5aa0;
    --primary-fg: #fff;
    --card-bg: #fff;
    --border: #ddd;
    --text: #222;
    font-family: system-ui, -apple-system, sans-serif;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; height: 100%; background: var(--bg); color: var(--text); }
body { display: grid; grid-template-rows: auto auto 1fr; }
.app-bar {
    background: var(--primary); color: var(--primary-fg);
    padding: env(safe-area-inset-top, 0) 1rem .75rem;
    display: flex; justify-content: space-between; align-items: center;
}
.app-bar h1 { font-size: 1.1rem; margin: 0; }
.app-bar button { background: transparent; border: 0; color: inherit; font-size: 1rem; cursor: pointer; }
.day-tabs {
    display: grid; grid-template-columns: repeat(7, 1fr); background: var(--card-bg);
    border-bottom: 1px solid var(--border);
}
.day-tabs button {
    background: none; border: 0; padding: .75rem 0; font-weight: 600;
    cursor: pointer; color: var(--text);
}
.day-tabs button.active { background: var(--primary); color: var(--primary-fg); }
#map { min-height: 50vh; height: 100%; }
.sheet {
    position: fixed; left: 0; right: 0; bottom: 0;
    background: var(--card-bg); padding: 1rem 1rem calc(1rem + env(safe-area-inset-bottom));
    border-top: 1px solid var(--border); max-height: 70vh; overflow: auto;
    box-shadow: 0 -4px 12px rgba(0,0,0,.1); z-index: 1000;
}
.sheet.hidden { display: none; }
.sheet fieldset { border: 0; padding: 0; margin: 0 0 1rem; }
.sheet label { display: block; padding: .5rem 0; }
.venue-deal { padding: .5rem 0; border-bottom: 1px solid var(--border); }
.venue-deal:last-child { border: 0; }
.venue-deal .kind {
    display: inline-block; background: var(--primary); color: #fff;
    padding: .1em .5em; border-radius: 3px; font-size: .75rem; margin-right: .5rem;
}
@media (min-width: 768px) {
    body { max-width: 60rem; margin: 0 auto; box-shadow: 0 0 16px rgba(0,0,0,.1); }
}
```

- [ ] **Step 2: Commit**

```bash
git add site/styles.css
git commit -m "style(site): mobile-first responsive layout

Refs: omaha-deals-map"
```

---

### Task 24: site/app.js

**Files:**
- Create: `site/app.js`

- [ ] **Step 1: Write**

```javascript
const JS_DAY = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

const state = {
    data: null,
    selectedDay: JS_DAY[new Date().getDay()],
    kinds: new Set(["happy_hour"]),
    nowOnly: false,
    favoritesOnly: false,
    markers: [],
    map: null,
};

async function loadData() {
    const r = await fetch("data.json", { cache: "no-cache" });
    if (!r.ok) throw new Error(`data.json: HTTP ${r.status}`);
    return r.json();
}

function initMap() {
    state.map = L.map("map", { center: [41.2565, -95.9345], zoom: 12 });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap contributors",
        maxZoom: 19,
    }).addTo(state.map);
}

function isActiveNow(w) {
    const now = new Date();
    if (JS_DAY[now.getDay()] !== w.day) return false;
    const cur = now.getHours() * 60 + now.getMinutes();
    const [sh, sm] = w.start.split(":").map(Number);
    const [eh, em] = (w.end || "23:59").split(":").map(Number);
    return cur >= sh * 60 + sm && cur <= eh * 60 + em;
}

function matchesFilters(r) {
    if (state.favoritesOnly) {
        const tags = r.personal?.tags || [];
        if (!tags.includes("favorite")) return false;
    }
    return r.deals.some(d => {
        if (!state.kinds.has(d.kind)) return false;
        if (d.kind === "happy_hour") {
            const wins = (d.windows || []).filter(w => w.day === state.selectedDay);
            if (wins.length === 0) return false;
            if (state.nowOnly && !wins.some(isActiveNow)) return false;
        }
        return true;
    });
}

function clearMarkers() {
    state.markers.forEach(m => state.map.removeLayer(m));
    state.markers = [];
}

function render() {
    if (!state.map || !state.data) return;
    clearMarkers();
    for (const r of state.data.restaurants) {
        if (r.lat == null || r.lng == null) continue;
        if (!matchesFilters(r)) continue;
        const marker = L.marker([r.lat, r.lng]).addTo(state.map);
        marker.on("click", () => showVenue(r));
        state.markers.push(marker);
    }
}

function escapeHtml(s) {
    return String(s).replace(/[<>&"]/g, c =>
        ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "\"": "&quot;" }[c]));
}

function renderDeal(d) {
    if (d.kind === "happy_hour") {
        const wins = (d.windows || [])
            .filter(w => w.day === state.selectedDay)
            .map(w => `${w.start}${w.end ? '-' + w.end : ''}${w.type === 'reverse_hh' ? ' (reverse)' : ''}`)
            .join(", ");
        return `<div class="venue-deal"><span class="kind">happy hour</span>${wins}</div>`;
    }
    if (d.kind === "special") {
        return `<div class="venue-deal"><span class="kind">special</span>${escapeHtml(d.title || "")}
                <br><small>${d.valid_from} to ${d.valid_until}</small></div>`;
    }
    if (d.kind === "voucher") {
        return `<div class="venue-deal"><span class="kind">voucher</span>${escapeHtml(d.title || "")}
                <br><small>$${d.original_price} to $${d.sale_price} (save $${d.savings})</small></div>`;
    }
    return "";
}

function showVenue(r) {
    const sheet = document.getElementById("venue-sheet");
    sheet.innerHTML = `
        <h2>${escapeHtml(r.name)}</h2>
        <p>${escapeHtml(r.address || "")}</p>
        ${(r.deals || []).map(renderDeal).join("")}
        <p><a target="_blank"
              href="https://www.google.com/maps/search/${encodeURIComponent(r.name + " Omaha NE")}">
              Open in Google Maps</a></p>
        ${r.personal?.notes ? `<p><em>${escapeHtml(r.personal.notes)}</em></p>` : ""}
        <button onclick="document.getElementById('venue-sheet').classList.add('hidden')">Close</button>
    `;
    sheet.classList.remove("hidden");
}

function wireControls() {
    document.querySelectorAll(".day-tabs button").forEach(btn => {
        btn.addEventListener("click", () => {
            state.selectedDay = btn.dataset.day;
            document.querySelectorAll(".day-tabs button").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            render();
        });
        if (btn.dataset.day === state.selectedDay) btn.classList.add("active");
    });
    document.getElementById("filter-btn").addEventListener("click", () => {
        document.getElementById("filter-sheet").classList.toggle("hidden");
    });
    document.getElementById("close-filter").addEventListener("click", () => {
        document.getElementById("filter-sheet").classList.add("hidden");
    });
    document.querySelectorAll("[data-kind]").forEach(cb => {
        cb.addEventListener("change", () => {
            if (cb.checked) state.kinds.add(cb.dataset.kind);
            else state.kinds.delete(cb.dataset.kind);
            render();
        });
    });
    document.getElementById("now-only").addEventListener("change", e => {
        state.nowOnly = e.target.checked; render();
    });
    document.getElementById("favorites-only").addEventListener("change", e => {
        state.favoritesOnly = e.target.checked; render();
    });
}

(async function () {
    initMap();
    wireControls();
    try {
        state.data = await loadData();
        render();
    } catch (e) {
        console.error(e);
        document.getElementById("map").innerHTML = `<p>Could not load data: ${escapeHtml(e.message)}</p>`;
    }
})();
```

- [ ] **Step 2: Add placeholder `site/data.json`**

```bash
printf '%s\n' '{"schema_version":"1.0","built_at":"2026-06-06T00:00:00Z","sources":[],"restaurants":[]}' > site/data.json
```

- [ ] **Step 3: Manual smoke test**

```bash
make serve
# Visit http://localhost:8000 ; map renders (empty), filter UI works.
```

- [ ] **Step 4: Commit**

```bash
git add site/app.js site/data.json
git commit -m "feat(site): Leaflet map, day tabs, filters, venue sheet

Refs: omaha-deals-map"
```

---

### Task 25: review_queue helper

**Files:**
- Create: `scripts/review_queue.py`

- [ ] **Step 1: Implement**

```python
"""Print restaurants flagged needs_review so the operator can fix overrides."""
from __future__ import annotations
import json
from pathlib import Path


def main() -> int:
    bundle = json.loads(Path("data/deals.json").read_text())
    flagged = [r for r in bundle["restaurants"] if r.get("needs_review")]
    if not flagged:
        print("No restaurants need review.")
        return 0
    print(f"{len(flagged)} restaurants need review:\n")
    for r in flagged:
        print(f"- {r['id']}  ({r['name']})")
        print(f"  address: {r.get('address') or '(missing)'}")
        print(f"  geocode_confidence: {r.get('geocode_confidence')}")
        print(f"  deals: {[d['kind'] for d in r['deals']]}")
        print()
    print("Fix via data/overrides/addresses.yaml or data/overrides/categories.yaml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Commit**

```bash
git add scripts/review_queue.py
git commit -m "feat(review): CLI to list records flagged needs_review

Refs: omaha-deals-map"
```

---

## Phase 8: CI / scheduled scrape

### Task 26: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Look up the latest setup-python SHA**

```bash
gh api repos/actions/setup-python/releases/latest --jq '.tag_name'
# then resolve the tag to a commit SHA:
gh api repos/actions/setup-python/git/refs/tags/<tag> --jq '.object.sha'
```

- [ ] **Step 2: Write `.github/workflows/ci.yml`** (paste real SHAs)

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3
      - uses: actions/setup-python@PASTE_SHA_HERE # vX.Y.Z
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -q -m "not slow"
```

- [ ] **Step 3: Commit + verify**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: pytest + ruff on PR and main push

Refs: omaha-deals-map"
git push origin main
gh run watch -R nitrocode/omaha-deals-map
```

---

### Task 27: Pages deploy runs build first

**Files:**
- Modify: `.github/workflows/pages.yml`

- [ ] **Step 1: Replace `pages.yml`**

```yaml
name: Deploy GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - 'site/**'
      - 'data/deals.json'
      - 'scripts/05_build.py'
      - '.github/workflows/pages.yml'
  workflow_dispatch:
  workflow_run:
    workflows: ["Weekly scrape"]
    types: [completed]

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3
      - uses: actions/setup-python@PASTE_SHA_HERE # vX.Y.Z
        with:
          python-version: '3.11'
      - run: pip install -e .
      - run: python scripts/05_build.py
      - uses: actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d # v6.0.0
      - uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5.0.0
        with:
          path: site
      - id: deployment
        uses: actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128 # v5.0.0
```

- [ ] **Step 2: Commit + verify**

```bash
git add .github/workflows/pages.yml
git commit -m "ci(pages): run 05_build.py before deploying

Refs: omaha-deals-map"
git push origin main
gh run watch -R nitrocode/omaha-deals-map
curl -sI https://nitrocode.github.io/omaha-deals-map/  # expect 200
```

---

### Task 28: Weekly scrape

**Files:**
- Create: `.github/workflows/scrape.yml`

- [ ] **Step 1: Add `ANTHROPIC_API_KEY` repo secret (manual)**

https://github.com/nitrocode/omaha-deals-map/settings/secrets/actions/new

- [ ] **Step 2: Write**

```yaml
name: Weekly scrape

on:
  schedule:
    - cron: '0 12 * * 1'  # Mondays 12:00 UTC
  workflow_dispatch:

permissions:
  contents: write

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3
      - uses: actions/setup-python@PASTE_SHA_HERE
        with:
          python-version: '3.11'
      - run: pip install -e .
      - env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python scripts/01_fetch.py
          python scripts/02_parse.py
          python scripts/03_extract_times.py
          python scripts/04_geocode.py
          python scripts/05_build.py
      - name: Commit changes
        env:
          RUN: ${{ github.run_number }}
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/
          if ! git diff --cached --quiet; then
            git commit -m "chore(data): weekly scrape $RUN

Refs: omaha-deals-map"
            git push
          else
            echo "No data changes this run."
          fi
```

- [ ] **Step 3: Commit + trigger**

```bash
git add .github/workflows/scrape.yml
git commit -m "ci(scrape): weekly cron with anthropic secret

Refs: omaha-deals-map"
git push origin main
gh workflow run scrape.yml -R nitrocode/omaha-deals-map
gh run watch -R nitrocode/omaha-deals-map
```

---

## Phase 9: End-to-end

### Task 29: First real scrape and review

- [ ] **Step 1: Run the full pipeline locally**

```bash
export ANTHROPIC_API_KEY=$(op read "op://Employee/Anthropic API Key/password")
make all
```

Expected: terminal output ends with build summary like "200+ restaurants, 200+ deals, needs_review: N".

- [ ] **Step 2: Inspect review queue**

```bash
make review
```

- [ ] **Step 3: For each flagged restaurant, hand-fix `data/overrides/addresses.yaml`**

Schema:

```yaml
some-restaurant-id:
  address: "1234 Real St, Omaha, NE 68102"
  lat: 41.2565
  lng: -95.9345
```

Rebuild and re-check until `make review` reports "No restaurants need review."

- [ ] **Step 4: Commit + push**

```bash
git add data/
git commit -m "data: initial scrape with manual address overrides

Refs: omaha-deals-map"
git push origin main
```

- [ ] **Step 5: Visit the live site**

```
https://nitrocode.github.io/omaha-deals-map/
```

Expected: restaurants appear as markers, day tabs filter, filter sheet works, marker tap shows venue info.

---

### Task 30: Seed cuisine + neighborhood

- [ ] **Step 1: Generate a starter file**

```bash
python -c "
import json, yaml
b = json.load(open('data/deals.json'))
out = {r['id']: {'cuisine': [], 'neighborhood': None} for r in b['restaurants']}
yaml.safe_dump(out, open('data/overrides/categories.yaml', 'w'), sort_keys=True)
print(f'wrote {len(out)} stubs')
"
```

- [ ] **Step 2: Fill in values for restaurants you know**

```yaml
blue-sky-patio:
  cuisine: [american, sports_bar]
  neighborhood: Aksarben
```

- [ ] **Step 3: Rebuild + commit**

```bash
make build
git add data/
git commit -m "data: seed categories.yaml with cuisine + neighborhood

Refs: omaha-deals-map"
git push origin main
```

---

### Task 31: Personal overlay (gitignored)

- [ ] **Step 1: Create `data/overrides/personal.yaml`** (already gitignored)

```yaml
blue-sky-patio:
  tags: [favorite, date_spot]
  rating: 5
  notes: "Patio after work."
```

- [ ] **Step 2: Rebuild locally + verify in browser**

```bash
make build
make serve
```

Visit http://localhost:8000 with "Favorites only" toggled. The deployed site won't have personal notes because CI doesn't have personal.yaml.

---

### Task 32: README finalization

- [ ] **Step 1: Replace `README.md`**

```markdown
# Omaha Deals Map

Mobile-first map of Omaha-area restaurant happy hours, specials, and vouchers.

Live: https://nitrocode.github.io/omaha-deals-map/

## What's on the map

| Kind | Source | Shape |
|---|---|---|
| Happy hour | growomaha.com | Weekly recurring (day-of-week, time window) |
| Special | visitomaha.com | Date-range coupon |
| Voucher | omaha.bigdealsmedia.net | Pre-paid discount (Groupon-style) |

Updated weekly by GitHub Actions.

## Run locally

```bash
make install
ANTHROPIC_API_KEY=... make all
make serve  # localhost:8000
```

## Add a source

1. Create `sources/<name>/__init__.py`, `fetch.py`, `parse.py`.
2. Implement `fetch(client, cache_path) -> Payload` and `parse(payload) -> list[SourceRecord]`.
3. Add the name to `sources/registry.yaml`.
4. Add a fixture + parser test in `tests/`.
5. Run `make all`.

## Override files

- `data/overrides/addresses.yaml` hand-fixes bad geocodes.
- `data/overrides/categories.yaml` assigns cuisine + neighborhood.
- `data/overrides/personal.yaml` holds your tags/ratings/notes (gitignored).
- `data/overrides/merges.yaml` declares "these IDs are the same restaurant."

## Troubleshooting

- `make review` shows many needs_review entries: usually Nominatim couldn't find a confident match. Fix in `addresses.yaml`.
- CI scrape fails on `ANTHROPIC_API_KEY`: set the secret at https://github.com/nitrocode/omaha-deals-map/settings/secrets/actions
- Site shows nothing: open browser console; if `data.json: 404`, the build workflow didn't run; trigger it manually.

## Design

See `docs/superpowers/specs/2026-06-06-omaha-deals-map-design.md`.
```

- [ ] **Step 2: Commit + push**

```bash
git add README.md
git commit -m "docs: expand README with source table, add-source guide, troubleshooting

Refs: omaha-deals-map"
git push origin main
```

---

## Self-review (run after completing all tasks)

- [ ] Every restaurant in `data/deals.json` has lat/lng or `needs_review: true`.
- [ ] `pytest -q` is green (excluding `-m slow`).
- [ ] `make all` from a fresh clone produces the same `data/deals.json` (modulo timestamps).
- [ ] Live site loads in <2s on mobile, map markers render, day tabs work.
- [ ] Weekly scrape workflow has run at least once and committed cleanly.
- [ ] `personal.yaml` is excluded from git per `.gitignore`.

---

## Spec coverage map

| Spec section | Implementing tasks |
|---|---|
| Goal | All |
| v1 sources | 6-15 |
| Source-specific notes | 6, 8, 11, 14 |
| Data model | 2 (SourceRecord), 21 (deals.json) |
| Repo layout | 1 |
| Pipeline stages 01-05 | 16, 17, 18-19, 20, 21 |
| Caching (HTTP, per-record, content) | 4, 19, 20 |
| Mobile UX | 22, 23, 24 |
| Error handling | 17 (shrink guard), 19/20 (failure -> needs_review) |
| Testing | TDD pattern throughout; integration smoke per source |
| CI / scheduled | 26, 27, 28 |
| Token cost | inline in Task 19; ~$0.04 first run |
| Deferred (v2+) | not implemented |
