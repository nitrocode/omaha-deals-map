"""Tests for the photo discovery module."""
from unittest.mock import MagicMock

from scripts._lib.photo_finder import (
    Photo,
    _is_public_url,
    fetch_extratags,
    fetch_og_image,
    fetch_wikidata_image,
    find_photo,
)


def _mock_session(responses_by_url):
    """Build a MagicMock session whose .get(url, ...) returns the matching
    response from a dict keyed by URL substring."""
    sess = MagicMock()

    def fake_get(url, **kw):
        for sub, response in responses_by_url.items():
            if sub in url:
                return response
        raise AssertionError(f"unexpected URL: {url}")

    sess.get = MagicMock(side_effect=fake_get)
    return sess


def _force_public_dns(monkeypatch):
    """Pretend every hostname resolves to a public address so the SSRF
    check doesn't block tests that use synthetic hostnames."""
    import scripts._lib.photo_finder as pf
    monkeypatch.setattr(pf.socket, "getaddrinfo",
                        lambda h, p: [(0, 0, 0, "", ("93.184.216.34", 0))])


def _resp(status=200, json_data=None, content=b""):
    r = MagicMock()
    r.status_code = status
    r.json = MagicMock(return_value=json_data or [])
    r.content = content
    r.raise_for_status = MagicMock()
    return r


def test_fetch_extratags_returns_empty_when_no_match():
    session = _mock_session({"nominatim": _resp(json_data=[])})
    assert fetch_extratags("Ghost Bar", 41.25, -95.93, session=session) == {}


def test_fetch_extratags_rejects_far_away_match():
    """A Nominatim hit with the same name but different coords is a
    different place; don't trust its tags."""
    session = _mock_session({"nominatim": _resp(json_data=[{
        "lat": "45.00", "lon": "-93.00",  # St. Paul-ish, not Omaha
        "extratags": {"image": "https://example.com/wrong.jpg"},
    }])})
    assert fetch_extratags("Some Bar", 41.25, -95.93, session=session) == {}


def test_fetch_extratags_returns_tags_when_close():
    session = _mock_session({"nominatim": _resp(json_data=[{
        "lat": "41.251", "lon": "-95.931",
        "extratags": {"website": "https://example.com",
                      "image": "https://example.com/a.jpg"},
    }])})
    tags = fetch_extratags("Some Bar", 41.25, -95.93, session=session)
    assert tags["image"] == "https://example.com/a.jpg"
    assert tags["website"] == "https://example.com"


def test_fetch_wikidata_image_resolves_p18_filename_to_commons_url():
    session = _mock_session({"wikidata.org": _resp(json_data={
        "entities": {"Q123": {"claims": {"P18": [{
            "mainsnak": {"datavalue": {"value": "Cool Bar.jpg"}},
        }]}}},
    })})
    url = fetch_wikidata_image("Q123", session=session)
    assert url is not None
    assert "Cool%20Bar.jpg" in url
    assert "commons.wikimedia.org" in url


def test_fetch_wikidata_image_returns_none_when_no_p18():
    session = _mock_session({"wikidata.org": _resp(json_data={
        "entities": {"Q123": {"claims": {}}},
    })})
    assert fetch_wikidata_image("Q123", session=session) is None


def test_fetch_og_image_extracts_from_meta_tag(monkeypatch):
    _force_public_dns(monkeypatch)
    html = (
        b'<html><head>'
        b'<meta property="og:image" content="https://example.com/a.jpg">'
        b'</head></html>'
    )
    session = _mock_session({"example.com": _resp(content=html)})
    assert fetch_og_image("https://example.com", session=session) == \
        "https://example.com/a.jpg"


def test_fetch_og_image_falls_back_to_twitter_image(monkeypatch):
    _force_public_dns(monkeypatch)
    html = (
        b'<html><head>'
        b'<meta name="twitter:image" content="https://example.com/tw.jpg">'
        b'</head></html>'
    )
    session = _mock_session({"example.com": _resp(content=html)})
    assert fetch_og_image("https://example.com", session=session) == \
        "https://example.com/tw.jpg"


def test_fetch_og_image_rewrites_http_to_https_to_avoid_mixed_content(monkeypatch):
    """Browsers block <img src=http://...> on an HTTPS page. We rewrite
    optimistically; if HTTPS doesn't serve the same asset, the browser
    just shows a broken image (no worse than the alternative)."""
    _force_public_dns(monkeypatch)
    html = (
        b'<html><head>'
        b'<meta property="og:image" content="http://example.com/a.jpg">'
        b'</head></html>'
    )
    session = _mock_session({"example.com": _resp(content=html)})
    assert fetch_og_image("https://example.com", session=session) == \
        "https://example.com/a.jpg"


def test_fetch_og_image_returns_none_on_no_meta(monkeypatch):
    _force_public_dns(monkeypatch)
    html = b"<html><head><title>no og</title></head></html>"
    session = _mock_session({"example.com": _resp(content=html)})
    assert fetch_og_image("https://example.com", session=session) is None


def test_find_photo_prefers_osm_over_wikidata_over_og(monkeypatch):
    _force_public_dns(monkeypatch)
    session = _mock_session({
        "nominatim": _resp(json_data=[{
            "lat": "41.25", "lon": "-95.93",
            "extratags": {
                "image": "https://osm.example.com/photo.jpg",
                "wikidata": "Q123",
                "website": "https://venue.example.com",
            },
        }]),
    })
    photo = find_photo("Cool Bar", 41.25, -95.93, session=session,
                       sleep_fn=lambda _: None)
    assert photo == Photo(url="https://osm.example.com/photo.jpg",
                          source="osm",
                          attribution="© OpenStreetMap contributors")


def test_find_photo_falls_through_to_wikidata_when_no_osm_image(monkeypatch):
    _force_public_dns(monkeypatch)
    session = _mock_session({
        "nominatim": _resp(json_data=[{
            "lat": "41.25", "lon": "-95.93",
            "extratags": {"wikidata": "Q777",
                          "website": "https://venue.example.com"},
        }]),
        "wikidata.org": _resp(json_data={
            "entities": {"Q777": {"claims": {"P18": [{
                "mainsnak": {"datavalue": {"value": "Notable Bar.jpg"}},
            }]}}},
        }),
    })
    photo = find_photo("Notable Bar", 41.25, -95.93, session=session,
                       sleep_fn=lambda _: None)
    assert photo is not None
    assert photo.source == "wikidata"
    assert "Notable" in photo.url


def test_find_photo_falls_through_to_og_when_osm_and_wikidata_absent(monkeypatch):
    _force_public_dns(monkeypatch)
    html = b'<meta property="og:image" content="https://venue.example.com/hero.jpg">'
    session = _mock_session({
        "nominatim": _resp(json_data=[{
            "lat": "41.25", "lon": "-95.93",
            "extratags": {"website": "https://venue.example.com"},
        }]),
        "venue.example.com": _resp(content=html),
    })
    photo = find_photo("Plain Bar", 41.25, -95.93, session=session,
                       sleep_fn=lambda _: None)
    assert photo == Photo(url="https://venue.example.com/hero.jpg",
                          source="og",
                          attribution="https://venue.example.com")


def test_find_photo_returns_none_when_no_coords():
    assert find_photo("Anywhere", None, None) is None
    assert find_photo("Anywhere", 41.25, None) is None


def test_find_photo_returns_none_when_no_sources_have_anything():
    session = _mock_session({
        "nominatim": _resp(json_data=[{
            "lat": "41.25", "lon": "-95.93", "extratags": {},
        }]),
    })
    assert find_photo("Nowhere", 41.25, -95.93, session=session,
                      sleep_fn=lambda _: None) is None


def test_is_public_url_rejects_non_http_schemes():
    assert not _is_public_url("file:///etc/passwd")
    assert not _is_public_url("gopher://example.com/")
    assert not _is_public_url("ftp://example.com/")
    assert not _is_public_url("javascript:alert(1)")
    assert not _is_public_url("")


def test_is_public_url_rejects_loopback_and_private_v4(monkeypatch):
    """A malicious OSM website tag could point at localhost or RFC1918.
    Resolution is mocked so this test doesn't hit DNS."""
    import scripts._lib.photo_finder as pf
    cases = [
        ("http://127.0.0.1/admin", "127.0.0.1"),
        ("http://localhost/", "127.0.0.1"),
        ("http://10.0.0.1/", "10.0.0.1"),
        ("http://192.168.1.1/", "192.168.1.1"),
        ("http://172.16.0.1/", "172.16.0.1"),
        ("http://169.254.169.254/latest/meta-data/", "169.254.169.254"),  # AWS metadata
        ("http://0.0.0.0/", "0.0.0.0"),
    ]
    for url, ip in cases:
        monkeypatch.setattr(pf.socket, "getaddrinfo",
                            lambda host, port, _ip=ip: [(0, 0, 0, "", (_ip, 0))])
        assert not _is_public_url(url), f"should block {url}"


def test_is_public_url_rejects_ipv6_loopback_and_link_local(monkeypatch):
    import scripts._lib.photo_finder as pf
    for ip in ["::1", "fe80::1", "fc00::1", "::"]:
        monkeypatch.setattr(pf.socket, "getaddrinfo",
                            lambda host, port, _ip=ip: [(0, 0, 0, "", (_ip, 0))])
        assert not _is_public_url("http://example.com/"), f"should block {ip}"


def test_is_public_url_accepts_normal_public_host(monkeypatch):
    import scripts._lib.photo_finder as pf
    monkeypatch.setattr(pf.socket, "getaddrinfo",
                        lambda host, port: [(0, 0, 0, "", ("93.184.216.34", 0))])
    assert _is_public_url("https://www.example.com/")


def test_is_public_url_fails_closed_on_dns_failure(monkeypatch):
    import scripts._lib.photo_finder as pf

    def boom(*a, **kw):
        raise pf.socket.gaierror("no such host")
    monkeypatch.setattr(pf.socket, "getaddrinfo", boom)
    assert not _is_public_url("https://nonexistent.tld/")


def test_fetch_og_image_blocks_redirect_into_private_ip(monkeypatch):
    """An open redirect at a public host could bounce us into RFC1918;
    the per-hop revalidation must catch it."""
    import scripts._lib.photo_finder as pf

    # The initial URL resolves to a public address; the redirect target
    # resolves to RFC1918.
    def resolve(host, port):
        if host == "evil.example.com":
            return [(0, 0, 0, "", ("93.184.216.34", 0))]
        if host == "10.0.0.1":
            return [(0, 0, 0, "", ("10.0.0.1", 0))]
        raise pf.socket.gaierror("unknown")
    monkeypatch.setattr(pf.socket, "getaddrinfo", resolve)

    session = MagicMock()
    session.get = MagicMock(return_value=MagicMock(
        status_code=302,
        headers={"Location": "http://10.0.0.1/admin"},
        content=b"",
        raise_for_status=lambda: None,
    ))
    assert fetch_og_image("http://evil.example.com/", session=session) is None
    # We should have called .get exactly once (the redirect to a private
    # address is rejected without following).
    assert session.get.call_count == 1


def test_fetch_og_image_only_returns_https_results(monkeypatch):
    """Even if a site's og:image is plain http, the cached output should
    be https so the user's browser doesn't either silently block mixed
    content OR fetch from a malicious http endpoint."""
    import scripts._lib.photo_finder as pf
    monkeypatch.setattr(pf.socket, "getaddrinfo",
                        lambda h, p: [(0, 0, 0, "", ("93.184.216.34", 0))])
    html = b'<meta property="og:image" content="http://example.com/a.jpg">'
    session = _mock_session({"example.com": _resp(content=html)})
    # The function rewrites http -> https; assert the output reflects that.
    assert fetch_og_image("https://example.com/", session=session) == \
        "https://example.com/a.jpg"


def test_find_photo_continues_on_og_fetch_exception():
    """A venue's website might 500 or hang; that should fall through to
    'no photo' instead of crashing the whole pipeline."""
    session = MagicMock()
    nominatim_resp = _resp(json_data=[{
        "lat": "41.25", "lon": "-95.93",
        "extratags": {"website": "https://broken.example.com"},
    }])

    def fake_get(url, **kw):
        if "nominatim" in url:
            return nominatim_resp
        raise ConnectionError("simulated venue site down")

    session.get = MagicMock(side_effect=fake_get)
    assert find_photo("Broken", 41.25, -95.93, session=session,
                      sleep_fn=lambda _: None) is None
