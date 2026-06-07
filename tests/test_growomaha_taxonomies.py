"""Tests for growomaha.taxonomies."""
import json

import pytest

from sources.growomaha.taxonomies import (
    parse_day_of_week,
    parse_time_slots,
    time_slot_to_24h,
)


@pytest.fixture
def dow_raw(fixtures_dir):
    return json.loads((fixtures_dir / "growomaha" / "day_of_week.json").read_text())


@pytest.fixture
def ts_raw(fixtures_dir):
    return json.loads((fixtures_dir / "growomaha" / "time_slots.json").read_text())


def test_parse_day_of_week_maps_ids_to_short_codes(dow_raw):
    m = parse_day_of_week(dow_raw)
    # Confirmed IDs from spec: Mon=161, Tue=147, Wed=148, Thu=146, Fri=141, Sat=144, Sun=145
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
