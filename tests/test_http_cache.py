"""Tests for scripts._lib.http_cache."""
import hashlib
from unittest.mock import MagicMock

from scripts._lib.http_cache import CachedHttpClient


def make_response(status=200, text="hello", headers=None):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.content = text.encode()
    r.headers = headers or {}
    return r


def test_first_fetch_stores_etag_and_body_sha(tmp_path, monkeypatch):
    cache_path = tmp_path / "http_cache.yaml"
    client = CachedHttpClient(cache_path=cache_path)
    resp = make_response(headers={"ETag": "abc", "Last-Modified": "Mon"})
    monkeypatch.setattr(client._session, "request", lambda *a, **kw: resp)

    r = client.get("https://x/y")
    assert r.changed is True
    assert r.status_code == 200
    assert r.body == b"hello"

    import yaml
    cache = yaml.safe_load(cache_path.read_text())
    entry = cache["https://x/y"]
    assert entry["etag"] == "abc"
    assert entry["body_sha"] == hashlib.sha256(b"hello").hexdigest()


def test_second_fetch_sends_if_none_match_and_handles_304(tmp_path, monkeypatch):
    cache_path = tmp_path / "http_cache.yaml"
    cache_path.write_text(
        "https://x/y:\n  etag: abc\n  last_modified: Mon\n  body_sha: deadbeef\n"
    )
    client = CachedHttpClient(cache_path=cache_path)
    sent_headers = {}

    def fake_request(method, url, headers=None, **kw):
        sent_headers.update(headers or {})
        return make_response(status=304, text="")

    monkeypatch.setattr(client._session, "request", fake_request)
    r = client.get("https://x/y")
    assert sent_headers["If-None-Match"] == "abc"
    assert sent_headers["If-Modified-Since"] == "Mon"
    assert r.changed is False


def test_retry_adapter_is_wired_with_expected_status_forcelist(tmp_path):
    """Confirm transient 5xx / 429 trigger retries, not immediate failure.

    Why: the weekly scrape crashed when growomaha's WP REST API returned a
    momentary non-JSON page. urllib3 retries flatten those transient errors
    before they reach our exception handler.
    """
    client = CachedHttpClient(cache_path=tmp_path / "http_cache.yaml")
    adapter = client._session.get_adapter("https://example.com/")
    retry = adapter.max_retries
    assert retry.total == CachedHttpClient.RETRY_TOTAL
    assert set(CachedHttpClient.RETRY_STATUSES).issubset(set(retry.status_forcelist))
    assert "GET" in retry.allowed_methods


def test_retries_can_be_disabled_for_tests(tmp_path):
    client = CachedHttpClient(cache_path=tmp_path / "http_cache.yaml", retries=0)
    adapter = client._session.get_adapter("https://example.com/")
    assert adapter.max_retries.total == 0


def test_200_with_unchanged_body_sha_reports_unchanged(tmp_path, monkeypatch):
    cache_path = tmp_path / "http_cache.yaml"
    sha = hashlib.sha256(b"hello").hexdigest()
    cache_path.write_text(f"https://x/y:\n  body_sha: {sha}\n")
    client = CachedHttpClient(cache_path=cache_path)
    resp = make_response(text="hello")
    monkeypatch.setattr(client._session, "request", lambda *a, **kw: resp)
    r = client.get("https://x/y")
    assert r.changed is False
