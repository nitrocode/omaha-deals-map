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
