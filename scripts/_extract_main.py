"""Pipeline stage 3: fill in window end times via regex."""
from __future__ import annotations

import argparse
from pathlib import Path

from scripts._lib.io import read_yaml, write_yaml
from scripts._lib.time_extractor import extract_end_time


def main(force: bool = False) -> int:
    parsed = read_yaml(Path("data/parsed.yaml"), default=[])
    out = []
    for rec in parsed:
        if rec["kind"] != "happy_hour":
            rec["extraction_source"] = "n/a"
            out.append(rec)
            continue

        wins = rec.get("pre_extracted_windows") or []
        if wins and all(w.get("end") for w in wins):
            rec["extraction_source"] = "source_taxonomy"
            out.append(rec)
            continue

        text = rec.get("raw_text", "")
        start_hint = wins[0]["start"] if wins else None
        result = extract_end_time(text, start_hint=start_hint)

        if result.end:
            for w in wins:
                w["end"] = result.end
                if result.is_reverse:
                    w["type"] = "reverse_hh"
            rec["extraction_source"] = "regex"
            rec["needs_review"] = False
        else:
            rec["needs_review"] = True
            rec["extraction_source"] = "none"
        out.append(rec)

    write_yaml(Path("data/extracted.yaml"), out)
    needs = sum(1 for r in out if r.get("needs_review"))
    print(f"[extract] {len(out)} records | needs_review: {needs}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    raise SystemExit(main(force=ap.parse_args().force))
