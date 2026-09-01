#!/usr/bin/env python3
"""Shared generation for E1–E4 (§7): N scripted takes, chained, optional reset-every-5.

  python3 experiments/gen_takes.py --mode chain    # 8 takes, pure last-frame chain
  python3 experiments/gen_takes.py --mode reset5   # 8 takes, re-anchor to hero every 5

The chain run serves E1 (verbatim), E2 (raw voice drift), E3 (effect masking) and half
of E4; the reset5 run is E4's other half. Output: out/exp/<mode>/NNN.mp4 (raw),
NNN_fx.mp4 (treated), NNN.png (last frame), manifest rows in out/takes.jsonl.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import Manifest, load_config, out_dirs  # noqa: E402
from generator import DryRunGenerator, FalGenerator  # noqa: E402
from post import apply_voice_effect, extract_last_frame, upload_frame  # noqa: E402
from spend import SpendMeter  # noqa: E402


async def run(cfg: dict, args) -> None:
    root = Path(cfg["_root"])
    out_dirs(root)
    exp_dir = root / "out" / "exp" / args.mode
    exp_dir.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(root / "out" / "takes.jsonl")
    meter = SpendMeter(cfg["spend"]["rate_768p"], cfg["spend"]["cap_usd"],
                       manifest.total_spend())
    duration = float(cfg["video"]["duration"])

    lines = [ln.strip() for ln in open(args.lines) if ln.strip()][: args.n]
    if len(lines) < args.n:
        raise SystemExit(f"need {args.n} lines in {args.lines}, found {len(lines)}")

    hero = root / cfg["loop"]["hero_asset"]
    if args.dry_run:
        gen = DryRunGenerator(cfg)
        hero_url = hero.as_uri() if hero.exists() else "file:///dry-run-hero.png"
    else:
        if not hero.exists():
            raise SystemExit("assets/hero.png missing — run bake_assets.py first")
        gen = FalGenerator(cfg)
        hero_url = await upload_frame(hero)

    anchor_url, anchor_kind = hero_url, "hero"
    for i, line in enumerate(lines, start=1):
        meter.authorize(duration)
        if args.mode == "reset5" and (i - 1) % 5 == 0:
            anchor_url, anchor_kind = hero_url, "hero"

        raw = exp_dir / f"{i:03d}.mp4"
        t0 = time.monotonic()
        result = await gen.generate(line, anchor_url, raw)
        cost, cum = meter.charge(result.billed_seconds)
        if not result.ok:
            status = "dropped_422" if result.dropped_422 else "failed"
            print(f"[{args.mode} {i}] {status}: {result.error[:120]}")
            manifest.append({"take": i, "line": line, "status": status,
                             "exp": args.mode, "anchor": anchor_kind,
                             "cost_usd": cost, "cost_cum_usd": cum})
            continue

        png = exp_dir / f"{i:03d}.png"
        fx = exp_dir / f"{i:03d}_fx.mp4"
        await extract_last_frame(raw, png)
        await apply_voice_effect(raw, fx, cfg["identity"]["voice_filtergraph"])
        try:
            frame_url = await upload_frame(png, dry_run=args.dry_run)
            anchor_url, anchor_kind = frame_url, "chain"
        except Exception as e:
            print(f"[{args.mode} {i}] frame upload failed ({e}) — hero fallback")
            anchor_url, anchor_kind = hero_url, "hero"

        manifest.append({
            "take": i, "line": line, "exp": args.mode, "status": "ready",
            "raw": str(raw.relative_to(root)), "clip": str(fx.relative_to(root)),
            "frame_png": str(png.relative_to(root)), "anchor": anchor_kind,
            "t_inference_s": result.t_inference_s,
            "t_total_s": round(time.monotonic() - t0, 3),
            "cost_usd": cost, "cost_cum_usd": cum,
        })
        print(f"[{args.mode} {i}/{len(lines)}] ok  (${cum:.2f} cum)  “{line}”")

    print(f"\nDone. Takes in {exp_dir}. Next: e1_verbatim.py / e4_contact_sheet.py")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--mode", choices=["chain", "reset5"], default="chain")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--lines", default=str(Path(__file__).parent / "lines.txt"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(load_config(args.config), args))


if __name__ == "__main__":
    main()
