"""Tests for scripts._lib.sri (SRI parsing + verification)."""
from pathlib import Path

import pytest

from scripts._lib.sri import SriRef, compute_hash, parse_sri_tags, verify_sri

# Known reference vector: sha256("hello") in base64.
HELLO_SHA256_B64 = "LPJNul+wow4m6DsqxbninhsWHlwfp0JecwQzYpOLmCQ="
HELLO_SHA384_B64 = "WeF0h3dEjGnea4ANejO7+5/xtGPkQ1TDVTvNucZm+pASWjx5+QOXvfX2oT3oKGhP"


# ---------- compute_hash ----------

def test_compute_hash_sha256_known_vector():
    assert compute_hash(b"hello", "sha256") == HELLO_SHA256_B64


def test_compute_hash_sha384_known_vector():
    assert compute_hash(b"hello", "sha384") == HELLO_SHA384_B64


def test_compute_hash_rejects_unsupported_algo():
    with pytest.raises(ValueError):
        compute_hash(b"hello", "md5")


# ---------- parse_sri_tags ----------

def test_parse_sri_extracts_link_and_script_tags():
    html = """
        <link rel="stylesheet" href="https://cdn.example.com/x.css"
              integrity="sha256-abc123==" crossorigin="">
        <script src="https://cdn.example.com/y.js"
                integrity="sha384-def456=="></script>
    """
    refs = parse_sri_tags(html)
    assert len(refs) == 2
    assert {r.tag for r in refs} == {"link", "script"}
    assert {r.algo for r in refs} == {"sha256", "sha384"}


def test_parse_sri_handles_attribute_order():
    """`integrity` may appear before `href`/`src` in the markup."""
    html = (
        '<script integrity="sha256-abc=" src="https://x.example/y.js"></script>'
    )
    refs = parse_sri_tags(html)
    assert len(refs) == 1
    assert refs[0].url == "https://x.example/y.js"


def test_parse_sri_skips_tags_without_integrity():
    html = '<link rel="stylesheet" href="https://x.example/x.css">'
    assert parse_sri_tags(html) == []


def test_parse_sri_skips_tags_without_remote_url():
    html = '<link rel="stylesheet" href="./local.css" integrity="sha256-abc=">'
    assert parse_sri_tags(html) == []


def test_parse_sri_skips_unknown_algorithms():
    """SHA-1 / MD5 etc. should not be picked up; only sha256/384/512."""
    html = (
        '<script src="https://x.example/y.js" integrity="md5-deadbeef"></script>'
    )
    assert parse_sri_tags(html) == []


def test_parse_sri_emits_multiple_tokens_per_attribute():
    """Browsers accept a space-separated list of hashes; we emit one ref per."""
    html = (
        '<link rel="stylesheet" href="https://x.example/x.css" '
        'integrity="sha256-aaa= sha384-bbb=">'
    )
    refs = parse_sri_tags(html)
    assert {r.algo for r in refs} == {"sha256", "sha384"}


# ---------- verify_sri ----------

def test_verify_sri_passes_when_hash_matches():
    ref = SriRef("link", "https://x.example/x.css", "sha256", HELLO_SHA256_B64)
    ok, actual = verify_sri(ref, fetch=lambda _u: b"hello")
    assert ok is True
    assert actual == HELLO_SHA256_B64


def test_verify_sri_fails_when_hash_mismatches():
    ref = SriRef("link", "https://x.example/x.css", "sha256", "DEADBEEF==")
    ok, actual = verify_sri(ref, fetch=lambda _u: b"hello")
    assert ok is False
    assert actual == HELLO_SHA256_B64  # the computed value is reported back


# ---------- live integration: verify the actual site/index.html ----------

@pytest.mark.slow
def test_live_site_index_sri_hashes_match():
    """Fetch every external resource referenced in site/index.html and confirm
    the declared SRI hash matches the served content.

    This is the regression test that would have caught the fabricated-hash bug
    in commit 4473ba5 (and the corrected commits 75d1abb, a5f4559).
    """
    repo_root = Path(__file__).parent.parent
    html = (repo_root / "site" / "index.html").read_text()
    refs = parse_sri_tags(html)
    assert len(refs) > 0, "no SRI references found in site/index.html"
    failures = []
    for ref in refs:
        ok, actual = verify_sri(ref)
        if not ok:
            failures.append((ref, actual))
    if failures:
        msg = "\n".join(
            f"  {r.url}\n    declared: {r.algo}-{r.hash_b64}\n    actual:   {r.algo}-{a}"
            for r, a in failures
        )
        pytest.fail(f"SRI hash mismatch on {len(failures)} resource(s):\n{msg}")
