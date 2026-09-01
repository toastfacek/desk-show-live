#!/usr/bin/env python3
"""E4 — face drift (§7): contact sheet of frame 0 of each take, chain vs reset5.

  python3 experiments/e4_contact_sheet.py --dir out/exp/chain
  python3 experiments/e4_contact_sheet.py --dir out/exp/reset5

Pass: the reset5 sheet stays visibly closer to hero; the chain sheet documents drift.
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="out/exp/chain")
    ap.add_argument("--out", default=None, help="default: <dir>/contact_sheet.png")
    args = ap.parse_args()

    src = Path(args.dir)
    takes = sorted(src.glob("[0-9][0-9][0-9].mp4"))
    if not takes:
        raise SystemExit(f"no takes in {src}")
    out = Path(args.out) if args.out else src / "contact_sheet.png"

    with tempfile.TemporaryDirectory() as td:
        frames = []
        for p in takes:
            f = Path(td) / f"{p.stem}.png"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(p),
                 "-frames:v", "1", "-update", "1", str(f)],
                check=True,
            )
            frames.append(f)
        cols = 4
        rows = (len(frames) + cols - 1) // cols
        inputs = []
        for f in frames:
            inputs += ["-i", str(f)]
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *inputs,
             "-filter_complex",
             f"concat=n={len(frames)}:v=1:a=0 [t]; [t] scale=336:192, tile={cols}x{rows}",
             "-frames:v", "1", "-update", "1", str(out)],
            check=True,
        )
    print(f"contact sheet: {out}  (frame 0 of {len(takes)} takes, reading order)")


if __name__ == "__main__":
    main()
