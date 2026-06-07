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
