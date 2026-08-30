"""One-time offline bake: hero still + pre-baked idle/hold take.

Slow is fine off-air. Produces assets/hero.png (clip-0 anchor, PiP plate, and
re-anchor target) and assets/hold.mp4 (5s idle take played as playlist item
zero so the first generation wait is hidden off-air).

Usage: python bake_assets.py [--config config.yaml]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

import fal_client
import yaml

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("deskshow.bake_assets")

HERO_IMAGE_MODEL = "fal-ai/flux/dev"  # any fal text-to-image endpoint works here
HOLD_VIDEO_MODEL = "minimax/h3-max/text-to-video"


async def bake_hero(persona: str, hero_path: Path) -> str:
    logger.info("generating hero still...")
    handle = await fal_client.submit_async(
        HERO_IMAGE_MODEL,
        arguments={
            "prompt": (
                f"{persona}\nFull-frame character portrait, facing camera, "
                f"neutral idle pose, studio lit, plain dark background."
            ),
        },
    )
    result = await handle.get()
    image_url = result["images"][0]["url"]

    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.get(image_url)
        resp.raise_for_status()
        hero_path.parent.mkdir(parents=True, exist_ok=True)
        hero_path.write_bytes(resp.content)

    logger.info("hero still saved to %s", hero_path)
    return image_url


async def bake_hold(persona: str, hold_path: Path) -> None:
    logger.info("generating hold clip...")
    handle = await fal_client.submit_async(
        HOLD_VIDEO_MODEL,
        arguments={
            "prompt": f"{persona}\nIdle, looking at camera, waiting, subtle breathing motion.",
            "duration": 5,
            "resolution": "768p",
            "prompt_expansion_mode": "balanced",
        },
    )
    result = await handle.get()
    video_url = result["video"]["url"]

    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.get(video_url)
        resp.raise_for_status()
        hold_path.parent.mkdir(parents=True, exist_ok=True)
        hold_path.write_bytes(resp.content)

    logger.info("hold clip saved to %s", hold_path)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text())
    persona = config["persona"]
    hero_path = Path(config["identity"]["hero_still"])
    hold_path = Path(config["identity"]["hold_clip"])

    await bake_hero(persona, hero_path)
    await bake_hold(persona, hold_path)

    logger.info("done. Review both assets by eye before running run_live.py.")


if __name__ == "__main__":
    asyncio.run(main())
