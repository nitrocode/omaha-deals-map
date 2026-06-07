"""Shared types for source modules."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

VALID_KINDS = {"happy_hour", "special", "voucher"}
VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
VALID_WINDOW_TYPES = {"happy_hour", "reverse_hh"}
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def slugify(name: str) -> str:
    s = (name
         .replace("&amp;", "&").replace("&#038;", "&")
         .replace("&#8217;", "'").replace("&apos;", "'"))
    s = s.lower()
    # Remove apostrophes outright so "Addy's" -> "addys" (not "addy-s")
    s = s.replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


@dataclass
class Window:
    day: str
    start: str
    end: str | None = None
    type: str = "happy_hour"  # or "reverse_hh"

    def __post_init__(self):
        if self.day not in VALID_DAYS:
            raise ValueError(f"invalid day: {self.day!r}")
        if self.type not in VALID_WINDOW_TYPES:
            raise ValueError(
                f"invalid window type: {self.type!r}; expected one of {VALID_WINDOW_TYPES}"
            )
        if not TIME_RE.match(self.start):
            raise ValueError(f"invalid start time {self.start!r}; expected HH:MM 24h")
        if self.end is not None:
            if not TIME_RE.match(self.end):
                raise ValueError(f"invalid end time {self.end!r}; expected HH:MM 24h")
            # HH:MM 24h strings sort lexicographically; overnight windows are not supported
            if self.end <= self.start:
                raise ValueError(
                    f"window end {self.end} must be after start {self.start}"
                )


@dataclass
class SourceRecord:
    source: str
    source_record_id: str
    source_url: str
    name: str
    record_modified_at: str
    kind: str
    raw_text: str = ""
    external_link: str | None = None
    pre_extracted_windows: list[Window] = field(default_factory=list)
    valid_from: str | None = None
    valid_until: str | None = None
    title: str | None = None
    description: str | None = None
    original_price: float | None = None
    sale_price: float | None = None
    savings: float | None = None
    category: str | None = None
    lat: float | None = None
    lng: float | None = None

    def __post_init__(self):
        if self.kind not in VALID_KINDS:
            raise ValueError(f"invalid kind: {self.kind!r}; expected one of {VALID_KINDS}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SourceRecord:
        windows = [Window(**w) for w in d.get("pre_extracted_windows", []) or []]
        d2 = {**d, "pre_extracted_windows": windows}
        return cls(**d2)
