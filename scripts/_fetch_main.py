"""01_fetch entry point factored for testability."""
from __future__ import annotations

import argparse
import pickle
from datetime import UTC, datetime
from pathlib import Path

from scripts._lib.http_cache import CachedHttpClient
from scripts._lib.io import write_yaml
from sources._registry import load_active_sources


def main(force: bool = False) -> int:
    raw_dir = Path("data/raw")
    raw_dir.mkdir(parents=True, exist_ok=True)
    cache_path = Path("data/http_cache.yaml")
    client = CachedHttpClient(cache_path=cache_path)

    summary = {}
    active = load_active_sources()
    for name, mod in zip(active.names, active.modules, strict=True):
        print(f"[fetch] {name}...", flush=True)
        src_dir = raw_dir / name
        src_dir.mkdir(exist_ok=True)
        try:
            payload = mod.fetch(client=client, cache_path=cache_path)
        except Exception as e:
            print(f"[fetch] {name} FAILED: {e}")
            summary[name] = {"ok": False, "error": str(e)}
            continue
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        snap = src_dir / f"{ts}.pickle"
        snap.write_bytes(pickle.dumps(payload))
        latest = src_dir / "latest.pickle"
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.symlink_to(snap.name)
        n = len(getattr(payload, "records", []))
        summary[name] = {"ok": True, "snapshot": str(snap), "records": n}
        print(f"[fetch] {name}: {n} records")

    write_yaml(Path("data/fetch_summary.yaml"), summary)
    bad = [n for n, v in summary.items() if not v["ok"]]
    return 1 if bad and not force else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    raise SystemExit(main(force=ap.parse_args().force))
