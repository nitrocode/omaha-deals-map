"""Tests for venue_meta: parses socials + canonical URL from venue HTML."""
from __future__ import annotations

from scripts._lib import venue_meta

# ---- find_socials -----------------------------------------------------------

def test_find_socials_handles_empty_inputs():
    assert venue_meta.find_socials("") == {}
    assert venue_meta.find_socials("<html><body></body></html>") == {}


def test_find_socials_picks_each_platform_once():
    html = """
    <html><body>
      <a href="https://www.facebook.com/somecafe">FB</a>
      <a href="https://instagram.com/somecafe">IG</a>
      <a href="https://twitter.com/somecafe">TW</a>
      <a href="https://x.com/somecafe">X</a>  <!-- second twitter, ignored -->
      <a href="https://www.tiktok.com/@somecafe">TT</a>
      <a href="https://youtube.com/@somecafe">YT</a>
      <a href="https://threads.net/@somecafe">TH</a>
    </body></html>
    """
    s = venue_meta.find_socials(html)
    assert s == {
        "facebook":  "https://www.facebook.com/somecafe",
        "instagram": "https://instagram.com/somecafe",
        "twitter":   "https://twitter.com/somecafe",  # first match wins
        "tiktok":    "https://www.tiktok.com/@somecafe",
        "youtube":   "https://youtube.com/@somecafe",
        "threads":   "https://threads.net/@somecafe",
    }


def test_find_socials_skips_share_links():
    """Sharer URLs include the venue's page as a query param; they aren't
    the venue's own profile."""
    html = """<a href="https://www.facebook.com/sharer/sharer.php?u=https://somecafe.com">Share</a>
              <a href="https://twitter.com/intent/tweet?text=hi">Tweet</a>
              <a href="https://www.facebook.com/somecafe">Real FB</a>"""
    s = venue_meta.find_socials(html)
    assert s == {"facebook": "https://www.facebook.com/somecafe"}


def test_find_socials_strips_query_and_trailing_slash():
    html = '<a href="https://instagram.com/somecafe/?utm_source=footer">IG</a>'
    assert venue_meta.find_socials(html) == {"instagram": "https://instagram.com/somecafe"}


def test_find_socials_rejects_bare_domain():
    """A link to 'facebook.com' (no path) isn't a venue profile."""
    html = '<a href="https://facebook.com">FB</a>'
    assert venue_meta.find_socials(html) == {}


def test_find_socials_handles_mobile_subdomains():
    html = """<a href="https://m.facebook.com/cafe">m</a>
              <a href="https://mobile.twitter.com/cafe">tw</a>"""
    s = venue_meta.find_socials(html)
    assert s["facebook"].startswith("https://m.facebook.com/")
    assert s["twitter"].startswith("https://mobile.twitter.com/")


# ---- find_canonical_url -----------------------------------------------------

def test_canonical_url_prefers_link_rel_canonical():
    html = """<html><head>
      <link rel="canonical" href="https://example.com/canonical">
      <meta property="og:url" content="https://example.com/og">
    </head></html>"""
    assert venue_meta.find_canonical_url(html) == "https://example.com/canonical"


def test_canonical_url_falls_back_to_og_url():
    html = '<html><head><meta property="og:url" content="https://example.com/og"></head></html>'
    assert venue_meta.find_canonical_url(html) == "https://example.com/og"


def test_canonical_url_returns_none_when_missing():
    assert venue_meta.find_canonical_url("<html></html>") is None
    assert venue_meta.find_canonical_url("") is None


def test_canonical_url_rejects_relative_urls():
    html = '<html><head><link rel="canonical" href="/just/path"></head></html>'
    assert venue_meta.find_canonical_url(html) is None


# ---- fetch_venue_meta (mocked) ----------------------------------------------

class _FakeResp:
    def __init__(self, status=200, headers=None, text=""):
        self.status_code = status
        self.headers = headers or {"Content-Type": "text/html"}
        self.text = text


class _FakeSession:
    def __init__(self, responses):
        # responses can be a single resp or list-of-resps (for redirects)
        self._responses = responses if isinstance(responses, list) else [responses]
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._responses.pop(0)


def test_fetch_venue_meta_rejects_non_public_url():
    # _is_public_url blocks RFC1918 -- localhost should fail without any
    # network call.
    assert venue_meta.fetch_venue_meta("http://127.0.0.1/", session=None) is None


def test_fetch_venue_meta_returns_socials_and_canonical(monkeypatch):
    html = """<html><head>
      <link rel="canonical" href="https://example.com/">
    </head><body>
      <a href="https://facebook.com/foo">FB</a>
      <a href="https://instagram.com/foo">IG</a>
    </body></html>"""
    sess = _FakeSession(_FakeResp(status=200, text=html))
    # Force the SSRF guard to accept example.com so the test is hermetic.
    monkeypatch.setattr(venue_meta, "_is_public_url", lambda u: True)
    meta = venue_meta.fetch_venue_meta("https://example.com/", session=sess)
    assert meta == {
        "socials": {
            "facebook": "https://facebook.com/foo",
            "instagram": "https://instagram.com/foo",
        },
        "canonical_url": "https://example.com/",
    }


def test_fetch_venue_meta_follows_safe_redirects(monkeypatch):
    redirect = _FakeResp(status=301, headers={"Location": "https://example.com/final"})
    final = _FakeResp(status=200, text="<html><body>"
                                       "<a href='https://instagram.com/x'>IG</a></body></html>")
    sess = _FakeSession([redirect, final])
    monkeypatch.setattr(venue_meta, "_is_public_url", lambda u: True)
    meta = venue_meta.fetch_venue_meta("https://example.com/start", session=sess)
    assert meta["socials"] == {"instagram": "https://instagram.com/x"}
    # Confirm we re-validated the Location: hop went through public-URL check
    assert sess.calls[1][0] == "https://example.com/final"


def test_fetch_venue_meta_aborts_on_redirect_to_private_address(monkeypatch):
    redirect = _FakeResp(status=302, headers={"Location": "http://10.0.0.5/"})
    sess = _FakeSession([redirect])
    # Allow the FIRST host, reject the redirect target. This mirrors the
    # real SSRF concern: an open redirect at a public host bouncing into
    # RFC1918 space.
    monkeypatch.setattr(venue_meta, "_is_public_url",
                        lambda u: not u.startswith("http://10."))
    assert venue_meta.fetch_venue_meta("https://example.com/", session=sess) is None


def test_fetch_venue_meta_returns_none_on_4xx(monkeypatch):
    sess = _FakeSession(_FakeResp(status=404))
    monkeypatch.setattr(venue_meta, "_is_public_url", lambda u: True)
    assert venue_meta.fetch_venue_meta("https://example.com/", session=sess) is None


def test_fetch_venue_meta_returns_none_on_non_html(monkeypatch):
    sess = _FakeSession(_FakeResp(headers={"Content-Type": "application/pdf"},
                                   status=200))
    monkeypatch.setattr(venue_meta, "_is_public_url", lambda u: True)
    assert venue_meta.fetch_venue_meta("https://example.com/", session=sess) is None


def test_fetch_venue_meta_swallows_network_errors(monkeypatch):
    import requests as _requests

    class _BoomSession:
        def get(self, *a, **kw):
            raise _requests.ConnectionError("timeout")
    monkeypatch.setattr(venue_meta, "_is_public_url", lambda u: True)
    assert venue_meta.fetch_venue_meta("https://example.com/", session=_BoomSession()) is None
