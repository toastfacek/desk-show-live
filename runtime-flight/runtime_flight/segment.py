"""Sequential one-segment producer. Real text + fal; no OBS."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from runtime_flight.anchor import persist_anchor
from runtime_flight.baseline import BaselineContext
from runtime_flight.config import RuntimeConfig
from runtime_flight.evidence import FlightEvidence, write_evidence_bundle
from runtime_flight.fal_gateway import FalGateway
from runtime_flight.media import run_ffmpeg
from runtime_flight.models import CoverageState, SegmentPackage, Thought
from runtime_flight.operator import OperatorError
from runtime_flight.topic_map import (
    TOPIC_EXHAUSTED,
    advance_coverage,
    discussion_phase,
    host_voices_from_baseline,
    resolve_topic_map,
)
from runtime_flight.performer_fal import FalPerformer, ReadyTake, TakeRequest
from runtime_flight.prompt import assemble_prompt
from runtime_flight.segment_planner import SegmentPlanner
from runtime_flight.source import load_source_packet
from runtime_flight.spend import SpendLedger, SpendMeter
from runtime_flight.text_client import TextAttemptLimiter, TextClient
from runtime_flight.writer import Writer

HERO_IMAGE_PLACEHOLDER = "hero"
PerformerFactory = Any


def run_segment(
    *,
    config: RuntimeConfig,
    max_text_requests: int,
    max_fal_submissions: int,
    out_dir: Path | None = None,
    http_post=None,
    performer_factory: PerformerFactory = None,
) -> int:
    return asyncio.run(
        _run_segment_async(
            config=config,
            max_text_requests=max_text_requests,
            max_fal_submissions=max_fal_submissions,
            out_dir=out_dir,
            http_post=http_post,
            performer_factory=performer_factory,
        )
    )


async def _run_segment_async(
    *,
    config: RuntimeConfig,
    max_text_requests: int,
    max_fal_submissions: int,
    out_dir: Path | None,
    http_post,
    performer_factory,
) -> int:
    source = load_source_packet(config.source_packet, config.source_lock)
    baseline = BaselineContext.load_loadout(
        config.pack_manager_data_dir, config.baseline_id or ""
    )
    limiter = TextAttemptLimiter(max_text_requests)
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
    writer = Writer(client)
    flight_id = f"segment-{_stamp()}"
    work_dir = Path("out") / "segment-work" / flight_id
    work_dir.mkdir(parents=True, exist_ok=True)
    meter = SpendMeter(
        cap_usd=config.spend_cap_usd or Decimal("2.00"),
        rate_768p_usd_per_s=config.spend_rate_768p_usd_per_s,
        duration_s=config.video_duration_s,
        mode=config.mode,
        ledger=SpendLedger(work_dir / "reservations.jsonl"),
    )
    performer = (
        performer_factory(meter, work_dir)
        if performer_factory is not None
        else _build_fal_performer(config, meter, work_dir, baseline.hero_path)
    )

    completed: list[ReadyTake] = []
    requests: list[TakeRequest] = []
    log: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    playhead = ConcatPlayhead()
    planned: list[Thought] = []
    pending: list[Thought] = []
    next_speaker: Literal["BOT1", "BOT2"] = "BOT1"
    thought_open = False
    topic_map = resolve_topic_map(package)
    coverage = CoverageState.initial()
    stop_reason = "segment complete"

    for take in range(1, max_fal_submissions + 1):
        if coverage.map_complete:
            stop_reason = coverage.stop_reason or TOPIC_EXHAUSTED
            break
        phase = discussion_phase(coverage, topic_map)
        if pending:
            thought = pending.pop(0)
        else:
            batch = await writer.write_point(
                package,
                tuple(planned),
                next_speaker,
                thought_open,
                phase,
                voices=voices,
                coverage=coverage,
            )
            thought, *pending = list(batch)
        planned.append(thought)
        coverage = advance_coverage(coverage, thought, topic_map)
        request = _request_for(baseline, thought, take, completed)
        requests.append(request)
        events.append(
            {
                "t": float(take - 1),
                "kind": "submit",
                "take": take,
                "anchor": request.anchor,
                "speaker": request.speaker,
            }
        )
        ready = await performer.start(request)
        completed.append(ready)
        row = {
            "take": take,
            "line": thought.text,
            "speaker": thought.speaker,
            "clip": str(ready.clip_path) if ready.clip_path else None,
            "status": ready.status,
            "layout_on_air": "wide",
            "t_submit": float(take - 1),
            "t_ready": float(take),
            "t_on_air": float(take),
            "anchor": ready.anchor,
            "image_url": request.image_url,
            "frame_url": ready.frame_url,
            "prompt": request.prompt,
            "request_id": ready.request_id,
        }
        log.append(row)
        events.append(
            {
                "t": float(take),
                "kind": "on_air",
                "take": take,
                "layout": "wide",
                "speaker": thought.speaker,
            }
        )
        if ready.status != "ready" or ready.clip_path is None:
            raise OperatorError(f"take {take} did not produce a ready clip")
        playhead.play_clip(str(ready.clip_path))
        if thought.thought_open:
            next_speaker = thought.speaker
            thought_open = True
        else:
            next_speaker = "BOT2" if thought.speaker == "BOT1" else "BOT1"
            thought_open = False
        if coverage.map_complete:
            stop_reason = coverage.stop_reason or TOPIC_EXHAUSTED
            break

    if not completed:
        raise OperatorError("segment produced no takes")

    recording = work_dir / "segment.mp4"
    await _concat_clips(playhead.clips, recording)
    write_evidence_bundle(
        Path(out_dir or "out/flights"),
            _evidence(
            baseline=baseline,
            package=package,
            config=config,
            work_dir=work_dir,
            flight_id=flight_id,
            takes=log,
            events=events,
            requests=requests,
            meter=meter,
            recording=recording,
            text_requests=limiter.attempts,
            text_request_limit=max_text_requests,
            stop_reason=stop_reason,
        ),
        sleep=lambda _dt: None,
    )
    return 0


class ConcatPlayhead:
    """No-OBS playhead: the live loop's play_clip, then concat for review."""

    def __init__(self) -> None:
        self.clips: list[Path] = []

    def play_clip(self, path: str) -> None:
        if not path:
            raise OperatorError("playhead received an empty clip path")
        self.clips.append(Path(path))


def _request_for(
    baseline: BaselineContext,
    thought: Thought,
    take: int,
    completed: list[ReadyTake],
) -> TakeRequest:
    previous = completed[take - 2] if take > 1 else None
    anchor, image_url = persist_anchor(
        take=take,
        speaker=thought.speaker,
        previous_speaker=previous.speaker if previous is not None else None,
        previous_frame_url=previous.frame_url if previous is not None else None,
        reanchor_every=baseline.reanchor_every,
        hero_url=HERO_IMAGE_PLACEHOLDER,
    )
    return TakeRequest(
        take=take,
        speaker=thought.speaker,
        line=thought.text,
        prompt=assemble_prompt(baseline, thought.speaker, thought.text),
        anchor=anchor,
        image_url=image_url,
        baseline_id=baseline.baseline_id,
    )


async def _concat_clips(clip_paths: list[Path], out_path: Path) -> None:
    if not clip_paths:
        raise OperatorError("segment produced no clips")
    if len(clip_paths) == 1:
        shutil.copyfile(clip_paths[0], out_path)
        return
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


def _evidence(
    *,
    baseline: BaselineContext,
    package: SegmentPackage,
    config: RuntimeConfig,
    work_dir: Path,
    flight_id: str,
    takes: list[dict[str, Any]],
    events: list[dict[str, Any]],
    requests: list[TakeRequest],
    meter: SpendMeter,
    recording: Path,
    text_requests: int,
    text_request_limit: int,
    stop_reason: str,
) -> FlightEvidence:
    lock = json.loads(Path(config.source_lock).read_text(encoding="utf-8"))
    manifest = baseline.hero_path.parent / "manifest.json"
    packet = json.loads(Path(config.source_packet).read_text(encoding="utf-8"))
    excerpt = Path(config.source_packet).parent / packet["linked_source"]["excerpt_path"]
    return FlightEvidence(
        flight_id=flight_id,
        baseline_id=baseline.baseline_id,
        mode=config.mode,
        target_duration_s=int(config.video_duration_s * max(len(takes), 1)),
        stop_reason=stop_reason,
        baseline_manifest_path=manifest,
        source_packet_path=config.source_packet,
        source_lock_path=config.source_lock,
        excerpt_path=excerpt,
        package=package,
        takes=takes,
        events=events,
        fal_requests=[
            {
                "take": req.take,
                "request_id": next(
                    (row.get("request_id") for row in takes if row.get("take") == req.take),
                    None,
                ),
                "prompt": req.prompt,
                "anchor": req.anchor,
                "image_url": req.image_url,
                "speaker": req.speaker,
                "reserved_cost_usd": str(meter.next_cost),
            }
            for req in requests
        ],
        recording_path=recording,
        recording_duration_s=float(config.video_duration_s * len(takes)),
        reserved_cost_upper_bound_usd=meter.total,
        spend_rate_768p_usd_per_s=meter.rate_768p_usd_per_s,
        spend_duration_s=meter.duration_s,
        reservations=[
            {
                "id": row.id,
                "take": row.take,
                "attempt": row.attempt,
                "reserved_cost_usd": str(row.reserved_cost_usd),
                "calculation": f"{meter.rate_768p_usd_per_s} * {meter.duration_s}",
            }
            for row in meter.ledger.records()
        ],
        source_hashes={
            "source_packet_sha256": lock["source_packet_sha256"],
            "tweet_text_sha256": lock["tweet_text_sha256"],
            "excerpt_sha256": lock["excerpt_sha256"],
        },
        config=config,
        beats=[],
        spend_cap_usd=config.spend_cap_usd,
        text_requests=text_requests,
        text_request_limit=text_request_limit,
        t_end=float(len(takes)),
        secrets=(),
    )


def _build_fal_performer(
    config: RuntimeConfig,
    meter: SpendMeter,
    work_dir: Path,
    hero_path: Path,
) -> FalPerformer:
    fal_key = os.environ.get("FAL_KEY")
    if not fal_key:
        raise OperatorError("missing required environment variable: FAL_KEY")
    gateway = FalGateway(fal_key=fal_key)
    return FalPerformer(
        meter=meter,
        gateway=gateway,
        upload=_fal_upload,
        work_dir=work_dir,
        hero_path=hero_path,
    )


async def _fal_upload(path: Path) -> str:
    try:
        import fal_client
    except ImportError as error:
        raise OperatorError("fal-client is required for paid flights") from error
    return await asyncio.to_thread(fal_client.upload_file, Path(path))


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
