"""The live loop: writer -> generator -> post -> ready queue -> playhead.

A clip queue with a playhead, not a stream. Only the line-as-text plus the
host's last-frame PNG URL crosses turns. See the TDD for the full design.

Usage: python run_live.py [--config config.yaml] [--max-takes N] [--no-player]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from pathlib import Path

import fal_client
import httpx
import yaml
from dotenv import load_dotenv

from generator import Generator, SafetyRejected
from playhead import Playhead
from post import process_take
from spend import SpendCapExceeded, from_config as spend_from_config
from writer import Writer, WriterUnavailable

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("deskshow.run_live")


class Stop(Exception):
    """Graceful-stop sentinel: raised to unwind the generation loop cleanly."""


async def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


async def upload_hero(hero_path: Path) -> str:
    return await fal_client.upload_file_async(str(hero_path))


def append_manifest(manifest_path: Path, row: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a") as f:
        f.write(json.dumps(row) + "\n")


async def generation_loop(
    config: dict,
    writer: Writer,
    generator: Generator,
    ready_queue: asyncio.Queue,
    hero_url: str,
    max_takes: int | None,
) -> None:
    paths = config["paths"]
    identity = config["identity"]
    video_cfg = config["video"]
    manifest_path = Path(paths["manifest"])
    raw_dir = Path(paths["raw_dir"])
    ready_dir = Path(paths["ready_dir"])
    frames_dir = Path(paths["frames_dir"])
    reset_every = identity["anchor_reset_every"]
    voice_effect = identity["voice_effect"]
    resolution = video_cfg["resolution"]
    duration = video_cfg["duration"]

    spend = spend_from_config(config)
    anchor_url = hero_url
    take_num = 0
    consecutive_failures = 0

    while max_takes is None or take_num < max_takes:
        take_num += 1
        take_id = f"{take_num:03d}"
        t_start = time.monotonic()

        try:
            line = await writer.next_line()
        except WriterUnavailable:
            logger.error("writer unavailable and no canned fallback left; stopping")
            break

        try:
            cost = spend.check(resolution, duration)
        except SpendCapExceeded as exc:
            logger.warning("spend cap reached (%s); stopping cleanly", exc)
            break

        t_writer_s = round(time.monotonic() - t_start, 2)

        try:
            gen_t0 = time.monotonic()
            result = await generator.generate(line, anchor_url)
            t_queue_s = round(result.queue_s, 2)
            t_inference_s = round(result.inference_s, 2)
        except SafetyRejected:
            logger.warning("take %s dropped: safety checker rejected", take_id)
            append_manifest(
                manifest_path,
                {
                    "take": take_num,
                    "line": line,
                    "status": "dropped_422",
                    "cost_usd": cost,
                    "cost_cum_usd": spend.record(cost),
                },
            )
            consecutive_failures = 0  # a 422 is expected behavior, not an outage
            continue
        except Exception:
            consecutive_failures += 1
            logger.exception("take %s failed (consecutive=%d)", take_id, consecutive_failures)
            if consecutive_failures >= 3:
                logger.error("3 consecutive failures; stopping cleanly, queue finishes")
                break
            continue

        consecutive_failures = 0

        raw_path = raw_dir / f"{take_id}.mp4"
        await download(result.video_url, raw_path)
        t_download_s = round(time.monotonic() - gen_t0 - t_inference_s - t_queue_s, 2)

        force_hero = take_num % reset_every == 0
        anchor_kind = "hero" if force_hero else "chain"

        frame_path = frames_dir / f"{take_id}.png"
        ready_path = ready_dir / f"{take_id}.mp4"
        post_t0 = time.monotonic()
        try:
            frame_url = await process_take(raw_path, frame_path, ready_path, voice_effect)
            anchor_url = hero_url if force_hero else frame_url
        except Exception:
            logger.exception("post-processing failed on take %s; falling back to hero anchor", take_id)
            anchor_kind = "hero"
            anchor_url = hero_url
            ready_path.write_bytes(raw_path.read_bytes())
        t_post_s = round(time.monotonic() - post_t0, 2)

        t_total_s = round(time.monotonic() - t_start, 2)
        cost_cum = spend.record(cost)

        append_manifest(
            manifest_path,
            {
                "take": take_num,
                "line": line,
                "clip": str(ready_path),
                "raw": str(raw_path),
                "anchor": anchor_kind,
                "frame_png": str(frame_path),
                "frame_url": anchor_url,
                "voice_effect": voice_effect,
                "t_writer_s": t_writer_s,
                "t_queue_s": t_queue_s,
                "t_inference_s": t_inference_s,
                "t_download_s": t_download_s,
                "t_post_s": t_post_s,
                "t_total_s": t_total_s,
                "cost_usd": cost,
                "cost_cum_usd": cost_cum,
                "status": "ready",
            },
        )
        logger.info("take %s ready: %r ($%.2f cum, %.1fs total)", take_id, line, cost_cum, t_total_s)

        await ready_queue.put(ready_path)

    await ready_queue.put(None)  # sentinel: no more takes


async def playhead_loop(ready_queue: asyncio.Queue, playhead: Playhead | None) -> None:
    while True:
        item = await ready_queue.get()
        if item is None:
            break
        if playhead is not None:
            await playhead.append(item)
        else:
            logger.info("(--no-player) would play: %s", item)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--max-takes", type=int, default=None)
    parser.add_argument("--no-player", action="store_true", help="skip mpv, just log")
    args = parser.parse_args()

    load_dotenv()
    if not os.environ.get("FAL_KEY"):
        raise SystemExit("FAL_KEY is not set (env or .env)")

    config = yaml.safe_load(Path(args.config).read_text())
    writer_cfg = config["writer"]
    video_cfg = config["video"]
    identity = config["identity"]

    writer = Writer(
        base_url=writer_cfg["base_url"],
        model=writer_cfg["model"],
        api_key=os.environ.get("WRITER_API_KEY", ""),
        persona=config["persona"],
        topics=config["topics"],
        max_words=writer_cfg["max_words"],
        canned_fallback=writer_cfg.get("canned_fallback"),
    )
    generator = Generator(
        model=video_cfg["model"],
        duration=video_cfg["duration"],
        resolution=video_cfg["resolution"],
        expansion=video_cfg["expansion"],
    )

    hero_path = Path(identity["hero_still"])
    if not hero_path.exists():
        raise SystemExit(f"missing {hero_path} — run bake_assets.py first")
    hero_url = await upload_hero(hero_path)

    ready_queue: asyncio.Queue = asyncio.Queue(maxsize=1)

    playhead = None
    if not args.no_player:
        playhead = Playhead(config["playhead"]["ipc_socket"])
        await playhead.start()
        hold_clip = Path(identity["hold_clip"])
        if hold_clip.exists():
            await playhead.append(hold_clip)

    try:
        await asyncio.gather(
            generation_loop(config, writer, generator, ready_queue, hero_url, args.max_takes),
            playhead_loop(ready_queue, playhead),
        )
    finally:
        if playhead is not None:
            await playhead.stop()


if __name__ == "__main__":
    asyncio.run(main())
