"""Convert BigDealsPayload SSR HTML into voucher SourceRecord rows.

The bigdealsmedia listing markup uses BEM-ish classes:
  a.products__item[data-business]    -> one card
    .price__old                      -> original price ($NN.NN)
    .price__new                      -> sale price ($NN.NN)

We dedup by slug because a small number of cards can repeat in the SSR
output (e.g. featured slots).
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from sources._common import SourceRecord, slugify
from sources.bigdealsmedia.fetch import BigDealsPayload

_PRICE_RE = re.compile(r"\$\s*(\d+(?:\.\d{2})?)")


def _price(text: str | None) -> float | None:
    if not text:
        return None
    m = _PRICE_RE.search(text)
    return float(m.group(1)) if m else None


def parse(payload: BigDealsPayload) -> list[SourceRecord]:
    soup = BeautifulSoup(payload.html, "html.parser")
    out: list[SourceRecord] = []
    seen: set[str] = set()

    for card in soup.select("a.products__item"):
        name = (card.get("data-business") or "").strip()
        if not name:
            info = card.select_one(".product__info p")
            name = info.get_text(strip=True) if info else ""
        if not name:
            continue
        name = name[:120]

        old_el = card.select_one(".price__old")
        new_el = card.select_one(".price__new")
        original = _price(old_el.get_text() if old_el else None)
        sale = _price(new_el.get_text() if new_el else None)
        if original is None or sale is None:
            continue

        slug = slugify(name)
        if not slug or slug in seen:
            continue
        seen.add(slug)

        out.append(SourceRecord(
            source="bigdealsmedia",
            source_record_id=slug,
            source_url=payload.source_url,
            name=name,
            record_modified_at=payload.fetched_at,
            kind="voucher",
            original_price=original,
            sale_price=sale,
            savings=round(original - sale, 2),
            category="restaurants",
            external_link=card.get("href"),
        ))

    return out
