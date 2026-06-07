"""Tests for visitomaha.fetch."""
from unittest.mock import MagicMock

from sources.visitomaha.fetch import VisitomahaPayload, fetch


def test_fetch_returns_records_count_and_url(fixtures_dir):
    raw = (fixtures_dir / "visitomaha" / "offers.json").read_bytes()
    client = MagicMock()
    client.get = lambda url: type("R", (), {"body": raw, "status_code": 200})()
    payload = fetch(client=client)
    assert isinstance(payload, VisitomahaPayload)
    assert payload.total_count >= 1
    assert len(payload.records) >= 1
    assert payload.source_url.startswith("https://www.visitomaha.com/")
