"""Tweet URL → reviewed packet, tweet image, producer card, planner, writer."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from runtime_flight.baseline import BaselineContext
from runtime_flight.config import RuntimeConfig
from runtime_flight.evidence import package_as_dict
from runtime_flight.ingest import IMAGE_NAME, IngestError, ingest_tweet, producer_card_payload
from runtime_flight.models import Thought
from runtime_flight.overlay import OverlayServer
from runtime_flight.segment_planner import SegmentPlanner
from runtime_flight.source import load_source_packet
from runtime_flight.text_client import TextAttemptLimiter, TextClient
from runtime_flight.topic_map import host_voices_from_baseline
from runtime_flight.writer import Writer
from runtime_flight.writer_pipeline import WriterPipeline

STAGE_PLAN_REQUESTS = 1
STAGE_WRITER_REQUESTS = 2


class StageError(Exception):
    """Raised when a tweet cannot be staged into a producer card and writer queue."""


def expected_text_requests(*, plan: bool, write: bool) -> int:
    if write:
        return STAGE_PLAN_REQUESTS + STAGE_WRITER_REQUESTS
    if plan:
        return STAGE_PLAN_REQUESTS
    return 0


def run_stage(
    *,
    tweet_url: str,
    config: RuntimeConfig,
    out_dir: Path,
    confirm_text_requests: int,
    plan: bool = True,
    write: bool = True,
    overlay_port: int = 8765,
    keep_overlay: bool = False,
    fixture: dict[str, Any] | None = None,
    http_get=None,
    http_post=None,
    overlay: OverlayServer | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        _run_stage_async(
            tweet_url=tweet_url,
            config=config,
            out_dir=out_dir,
            confirm_text_requests=confirm_text_requests,
            plan=plan,
            write=write,
            overlay_port=overlay_port,
            keep_overlay=keep_overlay,
            fixture=fixture,
            http_get=http_get,
            http_post=http_post,
            overlay=overlay,
        )
    )


async def _run_stage_async(
    *,
    tweet_url: str,
    config: RuntimeConfig,
    out_dir: Path,
    confirm_text_requests: int,
    plan: bool,
    write: bool,
    overlay_port: int,
    keep_overlay: bool,
    fixture: dict[str, Any] | None,
    http_get,
    http_post,
    overlay: OverlayServer | None,
) -> dict[str, Any]:
    if write:
        plan = True
    needed = expected_text_requests(plan=plan, write=write)
    if needed and confirm_text_requests != needed:
        raise StageError(
            f"stage --confirm-text-requests must be {needed} for this mode"
        )
    if not needed and confirm_text_requests not in {0, needed}:
        raise StageError("stage ingest-only does not consume text requests")

    staged_root = Path(out_dir)
    staged_root.mkdir(parents=True, exist_ok=True)
    try:
        ingested = ingest_tweet(
            tweet_url,
            staged_root / "_pending",
            http_get=http_get,
            fixture=fixture,
        )
    except IngestError as error:
        raise StageError(str(error)) from error
    tweet_id = ingested["fetched"].id
    dest = staged_root / tweet_id
    _replace_dir(dest, ingested["source_dir"])
    source = load_source_packet(dest / "source_packet.local.json", dest / "source_packet.lock.json")
    image_bytes = (dest / IMAGE_NAME).read_bytes()
    card = producer_card_payload(
        author=source.tweet.author,
        text=source.tweet.text,
        url=source.tweet.url,
        chyron=ingested["card"]["chyron"],
        image_url=f"/{IMAGE_NAME}",
    )

    overlay_server = overlay
    created_overlay = overlay is None
    if overlay_server is None:
        overlay_server = OverlayServer(port=overlay_port, state_dir=dest / "overlay-state")
    if created_overlay:
        overlay_server.start()
    overlay_server.set_card(
        author=card["author"],
        text=card["text"],
        url=card["url"],
        chyron=card["chyron"],
        image_url=card["image_url"],
        image_bytes=image_bytes,
    )

    package = None
    thoughts: list[Thought] = []
    limiter = None
    if plan:
        baseline = BaselineContext.load(
            config.pack_manager_data_dir, config.baseline_id or ""
        )
        limiter = TextAttemptLimiter(confirm_text_requests)
        client = TextClient(
            base_url=config.text_base_url or "",
            api_key=config.text_api_key or "",
            model=config.text_model or "",
            limiter=limiter,
            http_post=http_post,
            timeout_s=float(config.text_timeout_s),
        )
        voices = host_voices_from_baseline(baseline)
        package = await SegmentPlanner(client).plan(
            source, baseline, time_budget_s=int(config.target_duration_s), voices=voices
        )
        card = producer_card_payload(
            author=package.center.author,
            text=package.center.text,
            url=package.center.url,
            chyron=package.chyron,
            ticker=list(package.angles),
            image_url=f"/{IMAGE_NAME}",
        )
        overlay_server.set_card(
            author=card["author"],
            text=card["text"],
            url=card["url"],
            chyron=card["chyron"],
            ticker=card["ticker"],
            image_url=card["image_url"],
            image_bytes=image_bytes,
        )
        (dest / "package.json").write_text(
            json.dumps(package_as_dict(package), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if write:
            pipeline = WriterPipeline(Writer(client), voices=voices)
            await pipeline.fill(package, segment_phase="open")
            while True:
                thought = pipeline.peek_ready()
                if thought is None:
                    break
                thoughts.append(await pipeline.pop_ready())
            (dest / "writer-preview.json").write_text(
                json.dumps(
                    [
                        {
                            "speaker": thought.speaker,
                            "text": thought.text,
                            "thought_open": thought.thought_open,
                            "angle_used": thought.angle_used,
                        }
                        for thought in thoughts
                    ],
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

    (dest / "card.json").write_text(
        json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    summary = {
        "tweet_id": source.tweet.id,
        "tweet_url": source.tweet.url,
        "author": source.tweet.author,
        "source_dir": str(dest),
        "packet_path": str(dest / "source_packet.local.json"),
        "lock_path": str(dest / "source_packet.lock.json"),
        "image_path": str(dest / IMAGE_NAME),
        "package_path": str(dest / "package.json") if package is not None else None,
        "writer_preview_path": str(dest / "writer-preview.json") if thoughts else None,
        "overlay_url": overlay_server.live_url,
        "card_url": overlay_server.url + "card.json",
        "tweet_image_url": overlay_server.url + "tweet.png",
        "chyron": card.get("chyron"),
        "writer_lines": [
            {"speaker": thought.speaker, "text": thought.text} for thought in thoughts
        ],
        "text_requests": limiter.attempts if limiter is not None else 0,
        "text_model": "baseline",
        "keep_overlay": keep_overlay,
    }
    (dest / "stage.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if created_overlay and not keep_overlay:
        overlay_server.stop()
    return summary


def _replace_dir(dest: Path, incoming: Path) -> None:
    if dest.resolve() == incoming.resolve():
        return
    if dest.exists():
        for child in dest.iterdir():
            if child.is_file():
                child.unlink()
    dest.mkdir(parents=True, exist_ok=True)
    for child in incoming.iterdir():
        target = dest / child.name
        if target.exists():
            target.unlink()
        child.rename(target)
    incoming.rmdir()
