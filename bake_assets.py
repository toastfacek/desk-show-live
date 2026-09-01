#!/usr/bin/env python3
"""M0 — one-time asset bake (§6): assets/hero.png + assets/hold.mp4.

Slow is fine off-air. Costs ~$1–2 total; spend-metered against the same cap.

  python3 bake_assets.py            # bake whichever of the two is missing
  python3 bake_assets.py --force    # re-bake both (new design roll)

Re-run until the design looks right by eye — hero and hold must read as the SAME
character. M0 is done when both files exist and do.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import httpx

from core import Manifest, load_config, out_dirs
from spend import SpendMeter


async def _download(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


async def bake(cfg: dict, force: bool) -> None:
    import fal_client

    root = Path(cfg["_root"])
    assets = root / "assets"
    assets.mkdir(exist_ok=True)
    hero = root / cfg["loop"]["hero_asset"]
    hold = root / cfg["loop"]["hold_asset"]
    bake_cfg = cfg["bake"]

    manifest = Manifest(out_dirs(root)["out"] / "takes.jsonl")
    meter = SpendMeter(cfg["spend"]["rate_768p"], cfg["spend"]["cap_usd"],
                       manifest.total_spend())

    if force or not hero.exists():
        print("[hero] generating still…")
        result = await fal_client.subscribe_async(
            bake_cfg["image_model_id"],
            arguments={
                "prompt": bake_cfg["hero_prompt"],
                "image_size": "landscape_16_9",
                "num_images": 1,
                "output_format": "png",  # PNG end to end — never JPEG in the chain
            },
        )
        url = result["images"][0]["url"]
        await _download(url, hero)
        print(f"[hero] saved {hero}")
    else:
        print(f"[hero] exists, keeping {hero}")

    if force or not hold.exists():
        duration = int(cfg["video"]["duration"])
        meter.authorize(duration)
        print("[hold] uploading hero + generating 5s idle take…")
        hero_url = await fal_client.upload_file_async(str(hero))
        result = await fal_client.subscribe_async(
            cfg["video"]["model_id"],
            arguments={
                "prompt": bake_cfg["hold_prompt"],
                "image_url": hero_url,
                "duration": duration,
                "resolution": cfg["video"]["resolution"],
                "prompt_expansion_mode": "balanced",
            },
        )
        video = result.get("video") or {}
        await _download(video.get("url") or result.get("video_url"), hold)
        cost, cum = meter.charge(duration)
        manifest.append({
            "take": 0, "line": "(hold asset bake)", "clip": str(hold.relative_to(root)),
            "anchor": "hero", "cost_usd": cost, "cost_cum_usd": cum, "status": "ready",
        })
        print(f"[hold] saved {hold}  (${cost:.2f}, ${cum:.2f} cum)")
    else:
        print(f"[hold] exists, keeping {hold}")

    print("\nM0 check: do hero.png and hold.mp4 look like the same character? "
          "If not: bake_assets.py --force to reroll.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--force", action="store_true", help="re-bake even if files exist")
    args = ap.parse_args()
    asyncio.run(bake(load_config(args.config), args.force))


if __name__ == "__main__":
    main()
