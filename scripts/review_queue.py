"""Print restaurants flagged needs_review so the operator can fix overrides."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    bundle = json.loads(Path("data/deals.json").read_text())
    flagged = [r for r in bundle["restaurants"] if r.get("needs_review")]
    if not flagged:
        print("No restaurants need review.")
        return 0
    print(f"{len(flagged)} restaurants need review:\n")
    for r in flagged:
        print(f"- {r['id']}  ({r['name']})")
        print(f"  address: {r.get('address') or '(missing)'}")
        print(f"  geocode_confidence: {r.get('geocode_confidence')}")
        print(f"  deals: {[d['kind'] for d in r['deals']]}")
        print()
    print("Fix via data/overrides/addresses.yaml or data/overrides/categories.yaml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
