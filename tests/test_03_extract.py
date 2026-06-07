"""Tests for 03_extract_times orchestrator."""
from pathlib import Path

import yaml

from sources._common import SourceRecord, Window


def test_extract_main_fills_end_times_from_regex(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data").mkdir()
    rec = SourceRecord(
        source="growomaha", source_record_id="x", source_url="x", name="X",
        record_modified_at="2026-01-01T00:00:00Z", kind="happy_hour",
        raw_text="Monday-Friday 3-6 PM",
        pre_extracted_windows=[Window(day="mon", start="15:00")],
    )
    with open("data/parsed.yaml", "w") as f:
        yaml.safe_dump([rec.to_dict()], f)

    from scripts import _extract_main
    _extract_main.main()
    with open("data/extracted.yaml") as f:
        extracted = yaml.safe_load(f)
    assert extracted[0]["pre_extracted_windows"][0]["end"] == "18:00"
    assert extracted[0].get("extraction_source") == "regex"
