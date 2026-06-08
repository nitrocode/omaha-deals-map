"""Extract window end times from free-form deal prose."""
from __future__ import annotations

import re
from dataclasses import dataclass

RANGE_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*[-–]\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
    re.IGNORECASE,
)
TO_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s+to\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)",
    re.IGNORECASE,
)
UNTIL_RE = re.compile(r"until\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.IGNORECASE)
# "X PM - close" / "X-close", until close-of-business. Use 23:59 as a stable
# end sentinel so windows still render in the UI; the raw_text still shows
# "close" for the curious user.
CLOSE_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*[-–to]+\s*close",
    re.IGNORECASE,
)
# "open to X PM" / "open - X PM" / "from open to X", the venue runs the deal
# from doors-open until a specific time. We only recover the end (start is
# unknown). Accept either a dash or the word "to" as the separator.
OPEN_TO_RE = re.compile(
    r"open\s*(?:[-–]|\s+to)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
    re.IGNORECASE,
)
# "all day [DAY]", full-day deal. End at 23:59 so windows still render.
ALL_DAY_RE = re.compile(r"\ball\s*day\b", re.IGNORECASE)
REVERSE_RE = re.compile(r"reverse", re.IGNORECASE)


@dataclass
class ExtractResult:
    end: str | None
    confidence: str  # high | medium | none
    is_reverse: bool = False


def _to_24h(h: int, m: int, ampm: str | None) -> str:
    ampm = (ampm or "pm").lower()
    if ampm == "am":
        h = 0 if h == 12 else h
    else:
        h = 12 if h == 12 else h + 12
    return f"{h:02d}:{m:02d}"


def _parse(m: re.Match):
    h1, m1, ap1, h2, m2, ap2 = m.groups()
    ap1 = ap1 or ap2
    return _to_24h(int(h1), int(m1 or 0), ap1), _to_24h(int(h2), int(m2 or 0), ap2)


def extract_end_time(text: str, *, start_hint: str | None = None) -> ExtractResult:
    is_reverse = bool(REVERSE_RE.search(text))
    for rx in (RANGE_RE, TO_RE):
        m = rx.search(text)
        if m:
            _, end = _parse(m)
            return ExtractResult(end=end, confidence="high", is_reverse=is_reverse)
    m = UNTIL_RE.search(text)
    if m:
        h, mm, ap = m.groups()
        return ExtractResult(end=_to_24h(int(h), int(mm or 0), ap),
                             confidence="medium", is_reverse=is_reverse)
    if CLOSE_RE.search(text):
        # "until close" is genuinely open-ended. 23:59 keeps the window
        # renderable and the day-tab counts honest.
        return ExtractResult(end="23:59", confidence="medium", is_reverse=is_reverse)
    m = OPEN_TO_RE.search(text)
    if m:
        h, mm, ap = m.groups()
        # No am/pm hint and the hour reads like an evening number (1-11)
        # is overwhelmingly PM for happy-hour context, default accordingly.
        return ExtractResult(end=_to_24h(int(h), int(mm or 0), ap),
                             confidence="medium", is_reverse=is_reverse)
    if ALL_DAY_RE.search(text):
        return ExtractResult(end="23:59", confidence="medium", is_reverse=is_reverse)
    return ExtractResult(end=None, confidence="none", is_reverse=is_reverse)
