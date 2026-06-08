"""Tests for the operator review queue CLI."""
from __future__ import annotations

import json

from scripts import review_queue


def _write_bundle(tmp_path, restaurants):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "deals.json").write_text(json.dumps({"restaurants": restaurants}))


def test_main_reports_nothing_to_review(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_bundle(tmp_path, [{"id": "ok", "name": "OK", "needs_review": False, "deals": []}])
    rc = review_queue.main()
    assert rc == 0
    assert "No restaurants" in capsys.readouterr().out


def test_main_lists_flagged_restaurants(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_bundle(tmp_path, [
        {"id": "ok-1", "name": "OK 1", "needs_review": False, "deals": []},
        {
            "id": "flagged",
            "name": "Needs Help",
            "needs_review": True,
            "address": "",
            "geocode_confidence": "low",
            "deals": [{"kind": "happy_hour"}],
        },
    ])
    rc = review_queue.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 restaurants need review" in out
    assert "flagged" in out
    assert "Needs Help" in out
    assert "(missing)" in out  # blank address rendered explicitly
    assert "happy_hour" in out
    assert "Fix via" in out
