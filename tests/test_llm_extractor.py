"""Tests for the LLM extractor (mocked Anthropic client)."""
from unittest.mock import MagicMock

from scripts._lib.llm_extractor import extract_with_llm


def test_extract_with_llm_returns_end_time_and_caches(tmp_path):
    cache_path = tmp_path / "llm_cache.yaml"
    fake = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text='{"end_time": "18:00", "is_reverse_hh": false}')]
    fake.messages.create.return_value = msg

    r = extract_with_llm("Mon-Fri 3-6 PM", start_hint="15:00",
                         cache_path=cache_path, client=fake)
    assert r.end == "18:00" and r.is_reverse is False

    fake.messages.create.reset_mock()
    r2 = extract_with_llm("Mon-Fri 3-6 PM", start_hint="15:00",
                          cache_path=cache_path, client=fake)
    assert r2.end == "18:00"
    fake.messages.create.assert_not_called()


def test_extract_with_llm_handles_malformed_json(tmp_path):
    cache_path = tmp_path / "llm_cache.yaml"
    fake = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text="i'm not json")]
    fake.messages.create.return_value = msg
    r = extract_with_llm("whatever", start_hint="15:00",
                         cache_path=cache_path, client=fake)
    assert r.end is None
