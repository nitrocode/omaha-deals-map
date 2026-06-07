"""Tests for scripts._lib.io."""
import os
from pathlib import Path

import pytest

from scripts._lib.io import atomic_write, read_json, read_yaml, write_json, write_yaml


def test_write_and_read_yaml_round_trip(tmp_path):
    p = tmp_path / "x.yaml"
    write_yaml(p, {"a": [1, 2, 3], "b": "hi"})
    assert read_yaml(p) == {"a": [1, 2, 3], "b": "hi"}


def test_read_yaml_missing_returns_default():
    assert read_yaml(Path("/nonexistent"), default={}) == {}


def test_atomic_write_does_not_corrupt_on_partial_failure(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    p.write_text("original")

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(os, "rename", boom)
    with pytest.raises(OSError):
        atomic_write(p, "new contents")
    assert p.read_text() == "original"


def test_write_json_pretty(tmp_path):
    p = tmp_path / "x.json"
    write_json(p, {"a": 1})
    assert p.read_text() == '{\n  "a": 1\n}\n'


def test_read_json_round_trip_and_default(tmp_path):
    p = tmp_path / "x.json"
    write_json(p, {"a": 1})
    assert read_json(p) == {"a": 1}
    assert read_json(Path("/nonexistent"), default=[]) == []
