"""Convert a GrowomahaPayload into SourceRecord rows."""
from __future__ import annotations

import html
import re

from sources._common import SourceRecord, Window, slugify
from sources.growomaha.fetch import GrowomahaPayload

HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip(s: str) -> str:
    # Normalize curly quotes to ASCII to match slugify convention in _common.py
    return html.unescape(HTML_TAG_RE.sub("", s)).replace("’", "'").strip()


def _earliest(slot_ids, time_slots) -> str | None:
    times = sorted(time_slots[t] for t in slot_ids if t in time_slots)
    return times[0] if times else None


def parse(payload: GrowomahaPayload) -> list[SourceRecord]:
    out = []
    for rec in payload.records:
        name = _strip(rec["title"]["rendered"])
        slug = rec.get("slug") or slugify(name)
        modified = rec.get("modified_gmt", "")
        if modified and not modified.endswith("Z"):
            modified += "Z"
        day_ids = rec.get("day-of-week", [])
        slot_ids = rec.get("time-slots", [])
        days = [payload.day_of_week[d] for d in day_ids if d in payload.day_of_week]
        start = _earliest(slot_ids, payload.time_slots)
        windows = [Window(day=d, start=start) for d in days if start]
        out.append(SourceRecord(
            source="growomaha",
            source_record_id=slug,
            source_url=rec.get("link", ""),
            name=name,
            record_modified_at=modified,
            kind="happy_hour",
            raw_text=_strip(rec.get("excerpt", {}).get("rendered", "")),
            pre_extracted_windows=windows,
        ))
    return out
