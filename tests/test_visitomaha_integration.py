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
