#!/usr/bin/env python3
"""E7 — real $/min from the manifest (§7), including dropped/failed takes,
plus timing distributions. The output of this script goes back into TDD §10.

  python3 experiments/e7_cost.py
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Manifest, load_config  # noqa: E402


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    rows = Manifest(Path(cfg["_root"]) / "out" / "takes.jsonl").rows()
    if not rows:
        raise SystemExit("out/takes.jsonl is empty — run something first")

    ready = [r for r in rows if r.get("status") == "ready" and r.get("take", 0) > 0]
    dropped = [r for r in rows if r.get("status") == "dropped_422"]
    failed = [r for r in rows if r.get("status") == "failed"]
    total_cost = sum(float(r.get("cost_usd", 0)) for r in rows)
    duration = float(cfg["video"]["duration"])
    played_min = len(ready) * duration / 60.0

    print(f"takes: {len(ready)} ready, {len(dropped)} dropped_422, {len(failed)} failed")
    print(f"total spend:      ${total_cost:.2f}")
    if played_min:
        print(f"playable minutes: {played_min:.2f}")
        print(f"REAL $/min:       ${total_cost / played_min:.2f}  (incl. dropped/failed)")
    wasted = sum(float(r.get("cost_usd", 0)) for r in dropped + failed)
    if total_cost:
        print(f"retry overhead:   {100 * wasted / total_cost:.1f}% of spend on non-playable takes")

    for key in ("t_writer_s", "t_queue_s", "t_inference_s", "t_download_s",
                "t_post_s", "t_total_s"):
        vals = [float(r[key]) for r in ready if key in r]
        if vals:
            print(f"{key:15s} median={statistics.median(vals):5.2f}  "
                  f"p90={pct(vals, 90):5.2f}  max={max(vals):5.2f}")

    over = [r for r in ready if float(r.get("t_total_s", 0)) > duration]
    print(f"\ntakes over the {duration:.0f}s playback window: {len(over)}/{len(ready)}"
          f"  (each risks a hold at depth 1)")


if __name__ == "__main__":
    main()
