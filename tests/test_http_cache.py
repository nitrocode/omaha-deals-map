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


def test_200_with_unchanged_body_sha_reports_unchanged(tmp_path, monkeypatch):
    cache_path = tmp_path / "http_cache.yaml"
    sha = hashlib.sha256(b"hello").hexdigest()
    cache_path.write_text(f"https://x/y:\n  body_sha: {sha}\n")
    client = CachedHttpClient(cache_path=cache_path)
    resp = make_response(text="hello")
    monkeypatch.setattr(client._session, "request", lambda *a, **kw: resp)
    r = client.get("https://x/y")
    assert r.changed is False
