"""Tests for the fetch orchestrator."""
from dataclasses import dataclass, field
from unittest.mock import patch


@dataclass
class _FakePayload:
    records: list = field(default_factory=list)


def test_main_calls_fetch_for_each_registered_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    called = []

    class FakeMod:
        def __init__(self, n):
            self.n = n

        def fetch(self, client=None, cache_path=None):
            called.append(self.n)
            return _FakePayload(records=[{"id": 1}])

    active = type("X", (), {
        "names": ["growomaha", "visitomaha"],
        "modules": [FakeMod("growomaha"), FakeMod("visitomaha")],
    })

    from scripts import _fetch_main
    with patch("scripts._fetch_main.load_active_sources", return_value=active):
        _fetch_main.main()
    assert called == ["growomaha", "visitomaha"]
