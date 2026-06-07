"""Tests for parse orchestrator."""
import pickle
from pathlib import Path
from unittest.mock import patch

import yaml

from sources._common import SourceRecord


def test_parse_concatenates_all_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data/raw/foo").mkdir(parents=True)
    Path("data/raw/foo/latest.pickle").write_bytes(pickle.dumps({"x": 1}))
    Path("data/raw/bar").mkdir()
    Path("data/raw/bar/latest.pickle").write_bytes(pickle.dumps({"y": 2}))

    class FakeMod:
        def __init__(self, n):
            self.n = n

        def parse(self, p):
            return [SourceRecord(
                source=self.n,
                source_record_id=f"{self.n}-1",
                source_url="x",
                name=f"{self.n} R",
                record_modified_at="2026-01-01T00:00:00Z",
                kind="happy_hour",
            )]

    active = type("X", (), {"names": ["foo", "bar"],
                            "modules": [FakeMod("foo"), FakeMod("bar")]})

    from scripts import _parse_main
    with patch("scripts._parse_main.load_active_sources", return_value=active):
        _parse_main.main()

    parsed = yaml.safe_load(Path("data/parsed.yaml").read_text())
    assert len(parsed) == 2
    assert {r["source"] for r in parsed} == {"foo", "bar"}
