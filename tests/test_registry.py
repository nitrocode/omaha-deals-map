"""Tests for sources._registry."""
import pytest

from sources._registry import ActiveSources, load_active_sources


def test_load_active_sources_returns_list_in_yaml_order():
    s = load_active_sources()
    assert isinstance(s, ActiveSources)
    assert s.names == ["growomaha", "visitomaha", "bigdealsmedia"]


def test_load_active_sources_rejects_unknown_name(tmp_path, monkeypatch):
    bad = tmp_path / "registry.yaml"
    bad.write_text("sources:\n  - nonexistent_source\n")
    monkeypatch.setattr("sources._registry.REGISTRY_PATH", bad)
    with pytest.raises(ImportError):
        load_active_sources()
