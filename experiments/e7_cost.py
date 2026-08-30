"""E7 — $/min (TDD §7).

Computes real cost-per-minute and retry overhead from a manifest
(out/takes.jsonl by default). Pass: a real number, with retry overhead %.

Usage: python experiments/e7_cost.py [path/to/takes.jsonl]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / "out" / "takes.jsonl"


def main() -> None:
    manifest_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MANIFEST
    if not manifest_path.exists():
        raise SystemExit(f"no manifest at {manifest_path}")

    rows = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    if not rows:
        raise SystemExit("manifest is empty")

    ready = [r for r in rows if r["status"] == "ready"]
    dropped = [r for r in rows if r["status"] == "dropped_422"]
    failed = [r for r in rows if r["status"] not in ("ready", "dropped_422")]

    total_cost = sum(r["cost_usd"] for r in rows)
    ready_seconds = sum(5 for _ in ready)  # 5s takes in the MVP; adjust if duration varies
    minutes_of_show = ready_seconds / 60 if ready_seconds else 0

    print(f"takes total:   {len(rows)}")
    print(f"  ready:       {len(ready)}")
    print(f"  dropped_422: {len(dropped)}")
    print(f"  failed:      {len(failed)}")
    print(f"total cost:    ${total_cost:.2f}")
    if minutes_of_show:
        print(f"show minutes:  {minutes_of_show:.2f}")
        print(f"$/min:         ${total_cost / minutes_of_show:.2f}")
    if rows:
        overhead_pct = 100 * (len(dropped) + len(failed)) / len(rows)
        print(f"retry overhead: {overhead_pct:.1f}% of takes were dropped or failed")


if __name__ == "__main__":
    main()
