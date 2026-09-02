"""Cook three prepared H3 segments, then concat. No play during cook."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from runtime_flight.baseline import BaselineContext
from runtime_flight.clip import require_clip_duration_s
from runtime_flight.config import ALLOWED_VIDEO_ENDPOINTS, RuntimeConfig
from runtime_flight.fal_gateway import FalGateway
from runtime_flight.media import run_ffmpeg
from runtime_flight.operator import OperatorError
from runtime_flight.performer_fal import FalPerformer, ReadyTake, TakeRequest
from runtime_flight.prompt import assemble_prompt
from runtime_flight.spend import SpendLedger, SpendMeter
from runtime_flight.timeline import write_timeline

PREPARE_PASS_DURATION_S = 5
PREPARE_PASS_SEGMENTS_MIN = 3
PREPARE_PASS_SEGMENTS_MAX = 6
PREPARE_PASS_RATE_USD_PER_S = Decimal("0.01")
HERO_IMAGE_PLACEHOLDER = "hero"
PREPARE_PASS_LINES = (
    ("BOT1", "Fal just dropped H3 Max Turbo. Same picture, half the wait."),
    ("BOT2", "Two times faster, half the cost. That's the whole pitch."),
    ("BOT1", "We cook three clips first, then we play. No typing into a cold queue."),
)
PREPARE_PASS_TURNS = (2, 3)


@dataclass(frozen=True)
class PreparedTurn:
    speaker: Literal["BOT1", "BOT2"]
    line: str


@dataclass(frozen=True)
class PreparedSegment:
    tweet_id: str
    chyron: str
    turns: tuple[PreparedTurn, ...]


def apply_prepare_overrides(
    config: RuntimeConfig,
    *,
    endpoint: str,
    duration_s: int,
    rate_768p_usd_per_s: Decimal,
) -> RuntimeConfig:
    duration_s = require_clip_duration_s(duration_s)
    if endpoint not in ALLOWED_VIDEO_ENDPOINTS:
        raise OperatorError("prepare-pass endpoint is not allowed")
    if rate_768p_usd_per_s <= 0:
        raise OperatorError("prepare-pass rate must be greater than zero")
    return replace(
        config,
        video_endpoint=endpoint,
        video_duration_s=duration_s,
        spend_rate_768p_usd_per_s=rate_768p_usd_per_s,
    )


def parse_prepare_rate(value: str) -> Decimal:
    try:
        rate = Decimal(str(value))
    except InvalidOperation as error:
        raise OperatorError("prepare-pass --rate must be a decimal") from error
    if rate <= 0:
        raise OperatorError("prepare-pass --rate must be greater than zero")
    return rate


def run_prepare_pass(
    *,
    config: RuntimeConfig,
    out_dir: Path | None = None,
    performer_factory=None,
    concat_fn=None,
    segments: tuple[PreparedSegment, ...] | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        _run_async(
            config=config,
            out_dir=out_dir,
            performer_factory=performer_factory,
            concat_fn=concat_fn,
            segments=segments,
        )
    )


async def _run_async(
    *,
    config: RuntimeConfig,
    out_dir: Path | None,
    performer_factory,
    concat_fn,
    segments: tuple[PreparedSegment, ...] | None,
) -> dict[str, Any]:
    baseline = BaselineContext.load(config.pack_manager_data_dir, config.baseline_id or "")
    run_id = f"prepare-pass-{_stamp()}"
    root = Path(out_dir).resolve() if out_dir is not None else Path("out").resolve()
    work_dir = root / "prepare-pass" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    meter = SpendMeter(
        cap_usd=config.spend_cap_usd or Decimal("8.00"),
        rate_768p_usd_per_s=config.spend_rate_768p_usd_per_s,
        duration_s=config.video_duration_s,
        mode="live",
        ledger=SpendLedger(work_dir / "reservations.jsonl"),
    )
    performer = (
        performer_factory(meter, work_dir, baseline)
        if performer_factory is not None
        else _build_performer(config, meter, work_dir, baseline.hero_path)
    )
    queued = segments if segments is not None else _probe_segments()
    requests, owners = _requests_for_segments(baseline, queued)
    preroll_t0 = time.monotonic()
    tasks = [performer.start(request) for request in requests]
    completed = list(await asyncio.gather(*tasks))
    completed.sort(key=lambda item: item.take)
    t_preroll_s = round(time.monotonic() - preroll_t0, 3)
    by_take = {ready.take: ready for ready in completed}
    rows: list[dict[str, Any]] = []
    segment_rows: list[dict[str, Any]] = []
    show_clips: list[Path] = []
    concat_t0 = time.monotonic()
    for index, segment in enumerate(queued, start=1):
        take_ids = [take for take, owner in owners if owner == segment.tweet_id]
        clips: list[Path] = []
        turns: list[dict[str, Any]] = []
        for take in take_ids:
            request = next(item for item in requests if item.take == take)
            ready = by_take[take]
            if ready.status != "ready" or ready.clip_path is None:
                raise OperatorError(f"take {ready.take} did not produce a ready clip")
            cook = ready.cook.as_dict() if ready.cook is not None else {}
            row = {
                "take": ready.take,
                "segment": index,
                "tweet_id": segment.tweet_id,
                "speaker": ready.speaker,
                "line": request.line,
                "status": ready.status,
                "request_id": ready.request_id,
                "reserved_cost_usd": str(ready.reserved_cost_usd),
                "clip": str(ready.clip_path),
                "anchor": ready.anchor,
                "image_url": request.image_url,
                **cook,
            }
            rows.append(row)
            turns.append(row)
            clips.append(Path(ready.clip_path))
            _append_jsonl(work_dir / "logs" / "takes.jsonl", row)
        recording = work_dir / f"segment-{index:02d}-{segment.tweet_id}.mp4"
        await _concat(clips, recording, concat_fn)
        show_clips.append(recording)
        segment_rows.append(
            {
                "index": index,
                "tweet_id": segment.tweet_id,
                "chyron": segment.chyron,
                "turns": len(turns),
                "recording": str(recording),
            }
        )
    show_path = work_dir / "prepare.mp4"
    await _concat(show_clips, show_path, concat_fn)
    t_concat_s = round(time.monotonic() - concat_t0, 3)
    mode = "tweet-queue" if segments is not None else "prepare-ahead"
    summary = {
        "run_id": run_id,
        "work_dir": str(work_dir),
        "endpoint": config.video_endpoint,
        "duration_s": config.video_duration_s,
        "segments": len(queued),
        "mode": mode,
        "queue": segment_rows,
        "takes": rows,
        "recording": str(show_path),
        "t_preroll_s": t_preroll_s,
        "t_concat_s": t_concat_s,
        "mean_t_inference_s": _mean([row.get("t_inference_s") for row in rows]),
        "mean_t_cook_s": _mean([row.get("t_cook_s") for row in rows]),
        "mean_t_completed_s": _mean([row.get("t_completed_s") for row in rows]),
        "spend_reserved_usd": str(meter.total),
    }
    timeline_path = write_timeline(
        work_dir, title=f"prepare-pass timeline · {run_id}", duration_s=float(config.video_duration_s)
    )
    summary["timeline_html"] = str(timeline_path)
    (work_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def _probe_segments() -> tuple[PreparedSegment, ...]:
    return (
        PreparedSegment(
            tweet_id="probe",
            chyron="H3 Max Turbo preroll",
            turns=tuple(PreparedTurn(speaker, line) for speaker, line in PREPARE_PASS_LINES),
        ),
    )


def _requests_for_segments(
    baseline: BaselineContext,
    segments: tuple[PreparedSegment, ...],
) -> tuple[list[TakeRequest], list[tuple[int, str]]]:
    requests: list[TakeRequest] = []
    owners: list[tuple[int, str]] = []
    take = 1
    for segment in segments:
        if not segment.turns:
            raise OperatorError(f"segment {segment.tweet_id} has no prepared turns")
        for turn in segment.turns:
            requests.append(
                TakeRequest(
                    take=take,
                    speaker=turn.speaker,
                    line=turn.line,
                    prompt=assemble_prompt(baseline, turn.speaker, turn.line),
                    anchor="hero",
                    image_url=HERO_IMAGE_PLACEHOLDER,
                    baseline_id=baseline.baseline_id,
                )
            )
            owners.append((take, segment.tweet_id))
            take += 1
    return requests, owners


async def _concat(clip_paths: list[Path], out_path: Path, concat_fn) -> None:
    if concat_fn is not None:
        await concat_fn(clip_paths, out_path)
        return
    await _concat_clips(clip_paths, out_path)


def _build_performer(
    config: RuntimeConfig,
    meter: SpendMeter,
    work_dir: Path,
    hero_path: Path,
) -> FalPerformer:
    fal_key = os.environ.get("FAL_KEY")
    if not fal_key:
        raise OperatorError("missing required environment variable: FAL_KEY")
    return FalPerformer(
        meter=meter,
        gateway=FalGateway(fal_key=fal_key, endpoint=config.video_endpoint),
        upload=_fal_upload,
        work_dir=work_dir,
        hero_path=hero_path,
        duration_s=config.video_duration_s,
    )


async def _fal_upload(path: Path) -> str:
    try:
        import fal_client
    except ImportError as error:
        raise OperatorError("fal-client is required for paid flights") from error
    return await asyncio.to_thread(fal_client.upload_file, Path(path))


async def _concat_clips(clip_paths: list[Path], out_path: Path) -> None:
    if not clip_paths:
        raise OperatorError("prepare-pass produced no clips")
    listing = out_path.with_suffix(".concat.txt")
    listing.write_text(
        "".join(f"file '{path.resolve().as_posix()}'\n" for path in clip_paths),
        encoding="utf-8",
    )
    await run_ffmpeg(
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(listing),
        "-c",
        "copy",
        str(out_path),
    )


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def _mean(values: list[Any]) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 3)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
