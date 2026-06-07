"""Tests for growomaha.fetch."""
import json
from unittest.mock import MagicMock

from sources.growomaha.fetch import GrowomahaPayload, fetch


def test_fetch_paginates_until_no_records(fixtures_dir):
    pages = {
        p: json.loads((fixtures_dir / "growomaha" / f"page{p}.json").read_text())
        for p in (1, 2, 3)
    }
    taxonomies = {
        "day-of-week": json.loads((fixtures_dir / "growomaha" / "day_of_week.json").read_text()),
        "time-slots": json.loads((fixtures_dir / "growomaha" / "time_slots.json").read_text()),
        "cities": json.loads((fixtures_dir / "growomaha" / "cities.json").read_text()),
        "features": json.loads((fixtures_dir / "growomaha" / "features.json").read_text()),
    }

    def fake_get(url):
        resp = MagicMock()
        resp.status_code = 200
        if "/happy-hour" in url:
            page = int(url.split("&page=")[1].split("&")[0])
            body = pages.get(page, [])
        else:
            tax = url.rsplit("/", 1)[-1].split("?")[0]
            body = taxonomies[tax]
        resp.body = json.dumps(body).encode()
        resp.changed = True
        return resp

    client = MagicMock()
    client.get = fake_get
    payload = fetch(client=client)

    assert isinstance(payload, GrowomahaPayload)
    assert len(payload.records) >= 200
    assert payload.day_of_week[161] == "mon"


def test_get_json_retries_on_non_json_body():
    """The WP REST host occasionally serves a HTML interstitial or empty
    body with a 200 status. The fetcher should retry instead of failing
    the whole scrape."""
    from sources.growomaha.fetch import _get_json

    sleeps: list[float] = []
    attempts = 0

    def fake_get(url):
        nonlocal attempts
        attempts += 1
        resp = MagicMock()
        resp.status_code = 200
        # First two attempts get an HTML interstitial; third succeeds.
        if attempts < 3:
            resp.body = b"<html>Just a moment...</html>"
        else:
            resp.body = b'[{"id": 1, "name": "ok"}]'
        return resp

    client = MagicMock()
    client.get = fake_get
    result = _get_json(client, "http://x/y", sleep_fn=sleeps.append)
    assert result == [{"id": 1, "name": "ok"}]
    assert attempts == 3
    assert sleeps == [1.5, 3.0]  # backoff applied between attempts 1->2 and 2->3


def test_get_json_raises_after_exhausting_retries():
    import pytest

    from sources.growomaha.fetch import _get_json

    client = MagicMock()
    client.get = MagicMock(return_value=MagicMock(status_code=200, body=b""))
    with pytest.raises(RuntimeError, match="growomaha returned non-JSON"):
        _get_json(client, "http://x/y", sleep_fn=lambda _: None)
    assert client.get.call_count == 3
