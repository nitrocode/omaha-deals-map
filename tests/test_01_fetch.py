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


def _make_active(modules_by_name):
    return type("X", (), {
        "names": list(modules_by_name.keys()),
        "modules": list(modules_by_name.values()),
    })


class _GoodMod:
    def __init__(self, n):
        self.records = n

    def fetch(self, client=None, cache_path=None):
        return _FakePayload(records=[{"id": i} for i in range(self.records)])


class _FlakyMod:
    def fetch(self, client=None, cache_path=None):
        raise RuntimeError("Expecting value: line 1 column 1 (char 0)")


def test_partial_failure_returns_zero_so_downstream_stages_run(tmp_path, monkeypatch, capsys):
    """The original CI failure: one source throws, the script exits 1, and
    `bash -e` kills parse/extract/build. Mixed outcomes should still let the
    rest of the pipeline run with whatever data we got."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    active = _make_active({"flaky": _FlakyMod(), "good": _GoodMod(5)})

    from scripts import _fetch_main
    with patch("scripts._fetch_main.load_active_sources", return_value=active):
        rc = _fetch_main.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "partial" in out
    assert "flaky" in out


def test_all_failures_returns_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    active = _make_active({"a": _FlakyMod(), "b": _FlakyMod()})
    from scripts import _fetch_main
    with patch("scripts._fetch_main.load_active_sources", return_value=active):
        rc = _fetch_main.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "ABORT" in out


@dataclass
class _OpaquePayload:
    html: bytes = b"<html>...</html>"


class _OpaqueMod:
    """Simulates a source whose payload is HTML/bytes without a records list;
    the real record count is only known after parse runs."""
    def fetch(self, client=None, cache_path=None):
        return _OpaquePayload()


def test_opaque_payload_does_not_falsely_warn(tmp_path, monkeypatch, capsys):
    """Regression: bigdealsmedia returns HTML (no .records on the payload),
    and the previous fetch logic wrongly tagged it as 'WARN 0 records' even
    when parse later extracted 7 venues."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    active = _make_active({"opaque": _OpaqueMod()})
    from scripts import _fetch_main
    with patch("scripts._fetch_main.load_active_sources", return_value=active):
        rc = _fetch_main.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "WARN" not in out
    assert "records counted at parse stage" in out

    import yaml
    summary = yaml.safe_load((tmp_path / "data/fetch_summary.yaml").read_text())
    assert summary["opaque"]["records"] is None
    assert summary["opaque"]["stale_data_warning"] is False


def test_zero_records_warns_but_succeeds(tmp_path, monkeypatch, capsys):
    """A source that fetches successfully but produces zero records (likely
    a selector drift) should warn loudly, not silently report success."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    active = _make_active({"empty": _GoodMod(0), "good": _GoodMod(3)})
    from scripts import _fetch_main
    with patch("scripts._fetch_main.load_active_sources", return_value=active):
        rc = _fetch_main.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "WARN 0 records" in out

    import yaml
    summary = yaml.safe_load((tmp_path / "data/fetch_summary.yaml").read_text())
    assert summary["empty"]["stale_data_warning"] is True
    assert summary["good"]["stale_data_warning"] is False
