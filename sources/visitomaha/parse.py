"""Convert VisitomahaPayload into SourceRecord rows."""
from __future__ import annotations

from sources._common import SourceRecord
from sources.visitomaha.fetch import VisitomahaPayload


def _date_only(ts: str | None) -> str | None:
    return ts.split("T", 1)[0] if ts else None


def parse(payload: VisitomahaPayload) -> list[SourceRecord]:
    out = []
    for rec in payload.records:
        listings = rec.get("listings") or []
        venue = listings[0] if listings else None
        name = (venue["title"] if venue and "title" in venue else rec.get("title", "")).strip()
        out.append(SourceRecord(
            source="visitomaha",
            source_record_id=str(rec.get("recid", rec.get("_id", ""))),
            source_url="https://www.visitomaha.com" + rec.get("url", ""),
            name=name,
            record_modified_at=rec.get("updated", ""),
            kind="special",
            raw_text=rec.get("description", ""),
            external_link=rec.get("offerlink"),
            title=rec.get("title"),
            description=rec.get("description"),
            valid_from=_date_only(rec.get("poststart")),
            valid_until=_date_only(rec.get("postend")),
            lat=(venue or {}).get("latitude"),
            lng=(venue or {}).get("longitude"),
        ))
    return out
