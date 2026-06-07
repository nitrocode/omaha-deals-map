"""Tests for bigdealsmedia.fetch."""
from unittest.mock import MagicMock

from sources.bigdealsmedia.fetch import BigDealsPayload, fetch


def test_fetch_returns_html_payload(fixtures_dir):
    raw = (fixtures_dir / "bigdealsmedia" / "restaurants.html").read_bytes()
    client = MagicMock()
    client.get = lambda url: type("R", (), {"body": raw, "status_code": 200})()
    payload = fetch(client=client)
    assert isinstance(payload, BigDealsPayload)
    assert payload.html.startswith(b"<")
    assert payload.fetched_at
