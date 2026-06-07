#!/usr/bin/env python3
"""Verify SRI integrity hashes in HTML files match actual served content.

Used by the pre-commit hook and `ci.yml`. Exits 0 if all SRI hashes match,
1 otherwise. Reports the actual hash so you can copy-paste the fix.

Usage:
    python scripts/check_sri.py site/index.html [more.html ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

from scripts._lib.sri import parse_sri_tags, verify_sri


def check_file(path: Path) -> list[tuple]:
    """Return a list of (ref, actual_hash) for mismatching SRI refs in `path`."""
    failures = []
    for ref in parse_sri_tags(path.read_text()):
        try:
            ok, actual = verify_sri(ref)
        except Exception as e:
            print(f"  {ref.url}: network error: {e}", file=sys.stderr)
            failures.append((ref, f"<fetch failed: {e}>"))
            continue
        if not ok:
            failures.append((ref, actual))
    return failures


def main(paths: list[str]) -> int:
    if not paths:
        print("usage: check_sri.py <file.html> [...]", file=sys.stderr)
        return 2
    total_fail = 0
    for arg in paths:
        p = Path(arg)
        if not p.is_file():
            print(f"skip (not a file): {p}", file=sys.stderr)
            continue
        failures = check_file(p)
        if not failures:
            print(f"{p}: OK")
            continue
        print(f"{p}: {len(failures)} SRI mismatch(es)")
        for ref, actual in failures:
            print(f"  {ref.url}")
            print(f"    declared: {ref.algo}-{ref.hash_b64}")
            print(f"    actual:   {ref.algo}-{actual}")
        total_fail += len(failures)
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
