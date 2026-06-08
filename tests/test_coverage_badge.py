"""Tests for the coverage-badge JSON renderer."""
from __future__ import annotations

import json

import pytest

from scripts import coverage_badge


def _write_coverage_xml(path, rate: float) -> None:
    path.write_text(
        f'<?xml version="1.0"?><coverage line-rate="{rate}"></coverage>'
    )


@pytest.mark.parametrize("pct, expected_color", [
    (95, "brightgreen"),
    (90, "brightgreen"),
    (89, "green"),
    (80, "green"),
    (79, "yellowgreen"),
    (70, "yellowgreen"),
    (65, "yellow"),
    (60, "yellow"),
    (55, "orange"),
    (50, "orange"),
    (40, "red"),
    (0, "red"),
])
def test_color_for_matches_shields_bands(pct, expected_color):
    assert coverage_badge._color_for(pct) == expected_color


def test_render_writes_shields_endpoint_json(tmp_path):
    inp = tmp_path / "coverage.xml"
    out = tmp_path / "badge.json"
    _write_coverage_xml(inp, 0.8523)
    rc = coverage_badge.render(inp, out)
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload == {
        "schemaVersion": 1,
        "label": "coverage",
        "message": "85%",
        "color": "green",
    }


def test_render_creates_parent_dirs(tmp_path):
    inp = tmp_path / "coverage.xml"
    out = tmp_path / "nested" / "dir" / "badge.json"
    _write_coverage_xml(inp, 0.7)
    coverage_badge.render(inp, out)
    assert out.is_file()


def test_render_returns_1_when_input_missing(tmp_path, capsys):
    out = tmp_path / "badge.json"
    rc = coverage_badge.render(tmp_path / "missing.xml", out)
    assert rc == 1
    assert "not found" in capsys.readouterr().err
    assert not out.exists()


def test_main_uses_default_paths_when_no_args(tmp_path, monkeypatch):
    """main(argv) should fall back to coverage.xml + .github/badges/coverage.json
    when only argv[0] is provided."""
    monkeypatch.chdir(tmp_path)
    _write_coverage_xml(tmp_path / "coverage.xml", 0.9)
    rc = coverage_badge.main(["coverage_badge.py"])
    assert rc == 0
    assert (tmp_path / ".github" / "badges" / "coverage.json").is_file()


def test_main_honors_positional_args(tmp_path):
    inp = tmp_path / "in.xml"
    out = tmp_path / "out.json"
    _write_coverage_xml(inp, 0.5)
    rc = coverage_badge.main(["coverage_badge.py", str(inp), str(out)])
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["message"] == "50%"
    assert payload["color"] == "orange"


def test_render_handles_zero_coverage(tmp_path):
    inp = tmp_path / "coverage.xml"
    out = tmp_path / "badge.json"
    _write_coverage_xml(inp, 0.0)
    coverage_badge.render(inp, out)
    payload = json.loads(out.read_text())
    assert payload == {
        "schemaVersion": 1,
        "label": "coverage",
        "message": "0%",
        "color": "red",
    }
