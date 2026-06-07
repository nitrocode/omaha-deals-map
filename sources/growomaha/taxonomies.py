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
            continue  # skip oddballs like the slug "11"
    return out
