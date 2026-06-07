"""Pipeline stage 2: parse latest snapshots into a unified parsed.yaml."""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

from scripts._lib.io import read_yaml, write_yaml
from sources._registry import load_active_sources


def main(force: bool = False) -> int:
    active = load_active_sources()
    out = []
    for name, mod in zip(active.names, active.modules, strict=False):
        snap = Path(f"data/raw/{name}/latest.pickle")
        if not snap.exists():
            print(f"[parse] {name}: no snapshot, skipping")
            continue
        # Trusted: snapshots are written by our own 01_fetch stage on the
        # same machine. Not externally-sourced data.
        records = mod.parse(pickle.loads(snap.read_bytes()))  # noqa: S301
        if not records:
            print(f"[parse] {name}: WARN 0 records (selector drift? source empty?)")
        else:
            print(f"[parse] {name}: {len(records)} records")
        out.extend(r.to_dict() for r in records)

    prior = read_yaml(Path("data/parsed.yaml"), default=[])
    if prior and not force and len(out) < len(prior) * 0.5:
        print(f"[parse] ABORT: new count {len(out)} < 50% of prior {len(prior)}; use --force")
        return 2
    write_yaml(Path("data/parsed.yaml"), out)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    raise SystemExit(main(force=ap.parse_args().force))
