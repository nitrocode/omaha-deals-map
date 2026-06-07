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
