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
