#!/usr/bin/env python3
"""The loop (§2, asyncio): writer two beats ahead → generator (one in flight) → post →
ready queue → playhead. Spend meter wraps every generation and hard-stops at the cap.

  python3 run_live.py                 # live run, 12 turns (E5)
  python3 run_live.py --dry-run       # zero-spend loop shakeout (local test clips)
  python3 run_live.py --force-hold-at 5   # E6: kill take 5 in flight, watch the hold
"""
from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from core import Manifest, load_config, out_dirs
from generator import DryRunGenerator, FalGenerator
from playhead import make_playhead
from post import post_take, upload_frame
from spend import SpendCapReached, SpendMeter
from writer import Writer


async def line_producer(writer: Writer, queue: asyncio.Queue) -> None:
    """Keeps the line queue full — the two-beats-ahead buffer (§2)."""
    while True:
        line, t = await writer.next_line()
        await queue.put((line, t))


async def run(cfg: dict, args) -> None:
    root = Path(cfg["_root"])
    dirs = out_dirs(root)
    manifest = Manifest(dirs["out"] / "takes.jsonl")

    loop_cfg = cfg["loop"]
    ident = cfg["identity"]
    duration = float(cfg["video"]["duration"])
    turns = args.turns or int(loop_cfg["turns"])
    reset_every = int(ident["anchor_reset_every"])
    voice_effect = bool(ident["voice_effect"])
    max_fail = int(loop_cfg["max_consecutive_failures"])
    max_ready_depth = int(loop_cfg["max_ready_depth"])

    already = manifest.total_spend() if cfg["spend"].get("resume_from_manifest", True) else 0.0
    meter = SpendMeter(cfg["spend"]["rate_768p"], cfg["spend"]["cap_usd"], already)
    if already:
        print(f"[spend] resuming: ${already:.2f} already on the manifest, cap ${meter.cap_usd:.2f}")

    # Anchors. Real runs need the baked hero (M0); dry runs fake it.
    hero_png = root / loop_cfg["hero_asset"]
    if args.dry_run:
        generator = DryRunGenerator(cfg)
        hero_url = hero_png.as_uri() if hero_png.exists() else "file:///dry-run-hero.png"
    else:
        if not hero_png.exists():
            raise SystemExit(f"{hero_png} missing — run bake_assets.py first (M0).")
        generator = FalGenerator(cfg)
        print("[assets] uploading hero.png to fal CDN…")
        hero_url = await upload_frame(hero_png)
    anchor_url, anchor_kind = hero_url, "hero"

    playhead = make_playhead(cfg, dirs["ready"], override=args.player)
    await playhead.start()
    est_play_end = time.monotonic()

    async def append_clip(path: Path) -> None:
        nonlocal est_play_end
        await playhead.append(path)
        est_play_end = max(est_play_end, time.monotonic()) + duration

    hold = root / loop_cfg["hold_asset"]
    if hold.exists():
        await append_clip(hold)  # playlist item zero hides the first wait off-air (§4)
    else:
        print(f"[warn] {hold} missing — first wait will be on-air (run bake_assets.py)")

    writer = Writer(cfg)
    line_queue: asyncio.Queue = asyncio.Queue(maxsize=2)
    producer = asyncio.create_task(line_producer(writer, line_queue))

    take_num = manifest.next_take_number()
    played, consecutive_failures = 0, 0
    reissue_line: tuple[str, float] | None = None
    stop_reason = "turns complete"

    try:
        for turn in range(turns):
            # D3: one generation in flight, driven by completion; throttle on ready depth.
            while (est_play_end - time.monotonic()) / duration >= max_ready_depth:
                await asyncio.sleep(0.25)

            line, t_writer = reissue_line or await line_queue.get()
            reissue_line = None

            try:
                meter.authorize(duration)
            except SpendCapReached as e:
                print(f"[spend] {e} — clean shutdown")
                stop_reason = "spend cap"
                break

            # Forced re-anchor every N takes; extract failure also resets (§6).
            if (take_num - 1) % reset_every == 0:
                anchor_url, anchor_kind = hero_url, "hero"

            n = f"{take_num:03d}"
            raw_path = dirs["raw"] / f"{n}.mp4"
            t0 = time.monotonic()

            if args.force_hold_at == take_num:
                # E6: pretend this in-flight generation died. No retry — the gap IS the test.
                print(f"[E6] take {take_num}: generation killed on purpose — expect a hold")
                manifest.append({
                    "take": take_num, "line": line, "status": "failed",
                    "error": "forced_hold_e6", "anchor": anchor_kind,
                    "cost_usd": 0.0, "cost_cum_usd": meter.spent,
                })
                take_num += 1
                await asyncio.sleep(duration)  # the window this take would have filled
                continue

            result = await generator.generate(line, anchor_url, raw_path)
            if not result.ok and not result.dropped_422:
                print(f"[take {take_num}] failed ({result.error[:120]}) — retrying once")
                result = await generator.generate(line, anchor_url, raw_path)

            cost, cum = meter.charge(result.billed_seconds)  # dropped takes still billed (§5)

            if result.dropped_422:
                print(f"[take {take_num}] safety 422 — dropped; reissuing blander line")
                manifest.append({
                    "take": take_num, "line": line, "status": "dropped_422",
                    "anchor": anchor_kind, "cost_usd": cost, "cost_cum_usd": cum,
                })
                reissue_line = await writer.next_line(reissue=True)
                take_num += 1
                consecutive_failures += 1
                if consecutive_failures >= max_fail:
                    stop_reason = f"{max_fail} consecutive failures"
                    break
                continue

            if not result.ok:
                print(f"[take {take_num}] failed twice ({result.error[:120]}) — holding")
                manifest.append({
                    "take": take_num, "line": line, "status": "failed",
                    "error": result.error[:300], "anchor": anchor_kind,
                    "cost_usd": cost, "cost_cum_usd": cum,
                })
                take_num += 1
                consecutive_failures += 1
                if consecutive_failures >= max_fail:
                    stop_reason = f"{max_fail} consecutive failures (fal outage?)"
                    break
                continue

            consecutive_failures = 0
            ready_path = dirs["ready"] / f"{n}.mp4"
            frame_png = dirs["frames"] / f"{n}.png"
            postr = await post_take(
                raw_path, ready_path, frame_png, voice_effect,
                cfg["identity"]["voice_filtergraph"], dry_run=args.dry_run,
            )
            if postr["frame_ok"]:
                anchor_next = (postr["frame_url"], "chain")
            else:
                print(f"[take {take_num}] frame extract/upload failed — hero fallback")
                anchor_next = (hero_url, "hero")

            t_total = round(time.monotonic() - t0, 3)
            manifest.append({
                "take": take_num, "line": line,
                "clip": str(ready_path.relative_to(root)), "raw": str(raw_path.relative_to(root)),
                "anchor": anchor_kind,
                "frame_png": str(frame_png.relative_to(root)), "frame_url": postr["frame_url"],
                "voice_effect": voice_effect,
                "t_writer_s": t_writer, "t_queue_s": result.t_queue_s,
                "t_inference_s": result.t_inference_s, "t_download_s": result.t_download_s,
                "t_post_s": postr["t_post_s"], "t_total_s": t_total,
                "cost_usd": cost, "cost_cum_usd": cum, "status": "ready",
            })
            await append_clip(ready_path)
            played += 1
            print(f"[take {take_num}] ready in {t_total:.1f}s  (${cum:.2f} cum)  “{line}”")

            anchor_url, anchor_kind = anchor_next
            take_num += 1
    finally:
        producer.cancel()
        await writer.close()

    # Graceful stop: let the playhead finish the queue (§5), then close.
    remaining = est_play_end - time.monotonic()
    if remaining > 0 and args.player != "none" and cfg.get("player") != "none":
        print(f"[playhead] draining queue ({remaining:.0f}s left)…")
        await asyncio.sleep(remaining + 1)
    await playhead.close()
    print(f"\nDone: {stop_reason}. {played} clips played, ${meter.spent:.2f} total spend.")
    print("Manifest: out/takes.jsonl  →  analyze with experiments/e7_cost.py")


def main() -> None:
    ap = argparse.ArgumentParser(description="Desk Show MVP live loop")
    ap.add_argument("--config", default=None)
    ap.add_argument("--turns", type=int, default=None, help="override loop.turns")
    ap.add_argument("--dry-run", action="store_true", help="no fal calls, local test clips, $0")
    ap.add_argument("--player", choices=["mpv", "folder", "none"], default=None)
    ap.add_argument("--force-hold-at", type=int, default=0,
                    help="E6: kill the generation of take N in flight")
    args = ap.parse_args()
    cfg = load_config(args.config)
    asyncio.run(run(cfg, args))


if __name__ == "__main__":
    main()
