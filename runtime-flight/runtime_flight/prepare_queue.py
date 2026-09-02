"""Write three tweet discussions, then hand them to prepare-pass."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from runtime_flight.baseline import BaselineContext
from runtime_flight.config import RuntimeConfig
from runtime_flight.discuss import load_package
from runtime_flight.models import CoverageState, Thought
from runtime_flight.operator import OperatorError
from runtime_flight.prepare_pass import (
    PREPARE_PASS_SEGMENTS_MAX,
    PREPARE_PASS_SEGMENTS_MIN,
    PREPARE_PASS_TURNS,
    PreparedSegment,
    PreparedTurn,
    run_prepare_pass,
)
from runtime_flight.source import load_source_packet
from runtime_flight.text_client import TextAttemptLimiter, TextClient
from runtime_flight.topic_map import (
    TOPIC_EXHAUSTED,
    advance_coverage,
    discussion_phase,
    host_voices_from_baseline,
    resolve_topic_map,
)
from runtime_flight.writer import Writer

PACKET_NAME = "source_packet.local.json"
LOCK_NAME = "source_packet.lock.json"
PACKAGE_NAME = "package.json"


def run_prepare_queue(
    *,
    config: RuntimeConfig,
    source_dirs: list[Path],
    turns: int,
    max_text_requests: int,
    out_dir: Path | None = None,
    performer_factory=None,
    concat_fn=None,
    http_post=None,
    writer_factory=None,
) -> dict[str, Any]:
    if not (PREPARE_PASS_SEGMENTS_MIN <= len(source_dirs) <= PREPARE_PASS_SEGMENTS_MAX):
        raise OperatorError("prepare-pass --queue must be 3 to 6 staged tweet directories")
    if turns not in PREPARE_PASS_TURNS:
        raise OperatorError("prepare-pass --turns must be 2 or 3")
    segments = _write_segments(
        config=config,
        source_dirs=source_dirs,
        turns=turns,
        max_text_requests=max_text_requests,
        http_post=http_post,
        writer_factory=writer_factory,
    )
    return run_prepare_pass(
        config=config,
        out_dir=out_dir,
        performer_factory=performer_factory,
        concat_fn=concat_fn,
        segments=segments,
    )


def _write_segments(
    *,
    config: RuntimeConfig,
    source_dirs: list[Path],
    turns: int,
    max_text_requests: int,
    http_post,
    writer_factory,
) -> tuple[PreparedSegment, ...]:
    import asyncio

    return asyncio.run(
        _write_segments_async(
            config=config,
            source_dirs=source_dirs,
            turns=turns,
            max_text_requests=max_text_requests,
            http_post=http_post,
            writer_factory=writer_factory,
        )
    )


async def _write_segments_async(
    *,
    config: RuntimeConfig,
    source_dirs: list[Path],
    turns: int,
    max_text_requests: int,
    http_post,
    writer_factory,
) -> tuple[PreparedSegment, ...]:
    baseline = BaselineContext.load(config.pack_manager_data_dir, config.baseline_id or "")
    voices = host_voices_from_baseline(baseline)
    limiter = TextAttemptLimiter(max_text_requests)
    client = TextClient(
        base_url=config.text_base_url or "",
        api_key=config.text_api_key or "",
        model=config.text_model or "",
        limiter=limiter,
        http_post=http_post,
        timeout_s=float(config.text_timeout_s),
    )
    writer = writer_factory(client) if writer_factory is not None else Writer(client)
    prepared: list[PreparedSegment] = []
    for source_dir in source_dirs:
        root = Path(source_dir).resolve()
        load_source_packet(root / PACKET_NAME, root / LOCK_NAME)
        package = load_package(root / PACKAGE_NAME)
        thoughts = await _write_one(
            writer,
            package,
            turns=turns,
            voices=voices,
            clip_duration_s=config.video_duration_s,
        )
        prepared.append(
            PreparedSegment(
                tweet_id=package.item_id,
                chyron=package.chyron,
                turns=tuple(
                    PreparedTurn(speaker=thought.speaker, line=thought.text)
                    for thought in thoughts
                ),
            )
        )
    return tuple(prepared)


async def _write_one(
    writer: Writer,
    package,
    *,
    turns: int,
    voices,
    clip_duration_s: int,
) -> list[Thought]:
    topic_map = resolve_topic_map(package)
    coverage = CoverageState.initial()
    planned: list[Thought] = []
    pending: list[Thought] = []
    next_speaker: Literal["BOT1", "BOT2"] = "BOT1"
    thought_open = False
    for _ in range(turns):
        if coverage.map_complete:
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
                clip_duration_s=clip_duration_s,
            )
            thought, *pending = list(batch)
        planned.append(thought)
        coverage = advance_coverage(coverage, thought, topic_map)
        if thought.thought_open:
            next_speaker = thought.speaker
            thought_open = True
        else:
            next_speaker = "BOT2" if thought.speaker == "BOT1" else "BOT1"
            thought_open = False
        if coverage.map_complete:
            break
    if not planned:
        raise OperatorError(coverage.stop_reason or TOPIC_EXHAUSTED)
    return planned
