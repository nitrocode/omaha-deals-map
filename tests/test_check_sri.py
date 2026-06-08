"""Tests for the check_sri CLI wrapper around scripts/_lib/sri.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_sri
from scripts._lib.sri import SriRef


SAMPLE_HTML = """<!DOCTYPE html><html><head>
<link rel="stylesheet" href="https://cdn.example/style.css"
  integrity="sha384-AAAA" crossorigin="">
<script src="https://cdn.example/lib.js"
  integrity="sha384-BBBB" crossorigin=""></script>
</head><body></body></html>"""


def _fake_verify_factory(result_map):
    """result_map: {url -> (ok, actual_hash) | Exception}"""
    def fake(ref, *, fetch=None):
        v = result_map[ref.url]
        if isinstance(v, Exception):
            raise v
        return v
    return fake


def test_main_returns_2_when_no_paths(capsys):
    assert check_sri.main([]) == 2
    assert "usage" in capsys.readouterr().err


def test_main_reports_ok_when_all_match(tmp_path, monkeypatch, capsys):
    f = tmp_path / "page.html"
    f.write_text(SAMPLE_HTML)
    monkeypatch.setattr(check_sri, "verify_sri",
        _fake_verify_factory({
            "https://cdn.example/style.css": (True, "AAAA"),
            "https://cdn.example/lib.js": (True, "BBBB"),
        }))
    assert check_sri.main([str(f)]) == 0
    assert "OK" in capsys.readouterr().out


def test_main_reports_failures_when_hash_mismatches(tmp_path, monkeypatch, capsys):
    f = tmp_path / "page.html"
    f.write_text(SAMPLE_HTML)
    monkeypatch.setattr(check_sri, "verify_sri",
        _fake_verify_factory({
            "https://cdn.example/style.css": (True, "AAAA"),
            "https://cdn.example/lib.js": (False, "ACTUAL"),
        }))
    rc = check_sri.main([str(f)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "1 SRI mismatch" in out
    assert "actual:   sha384-ACTUAL" in out


def test_main_handles_network_errors_as_failures(tmp_path, monkeypatch, capsys):
    f = tmp_path / "page.html"
    f.write_text(SAMPLE_HTML)
    monkeypatch.setattr(check_sri, "verify_sri",
        _fake_verify_factory({
            "https://cdn.example/style.css": RuntimeError("timeout"),
            "https://cdn.example/lib.js": (True, "BBBB"),
        }))
    rc = check_sri.main([str(f)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "timeout" in err


def test_main_skips_nonexistent_paths(tmp_path, monkeypatch, capsys):
    # No verify_sri calls should happen for a non-file.
    monkeypatch.setattr(check_sri, "verify_sri",
        lambda *a, **k: pytest.fail("should not be called"))
    rc = check_sri.main([str(tmp_path / "does-not-exist.html")])
    assert rc == 0
    err = capsys.readouterr().err
    assert "skip (not a file)" in err


def test_check_file_returns_empty_list_when_no_sri(tmp_path):
    f = tmp_path / "no-sri.html"
    f.write_text("<html><body>nothing here</body></html>")
    assert check_sri.check_file(f) == []
