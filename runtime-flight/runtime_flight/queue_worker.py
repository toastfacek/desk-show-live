"""Dequeue the next dissected tweet, write it, cook it. Stop at a ready buffer."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from runtime_flight.baseline import BaselineContext
from runtime_flight.config import RuntimeConfig
from runtime_flight.content_queue import (
    LOCK_NAME,
    PACKAGE_NAME,
    PACKET_NAME,
    claim_next,
    mark_done,
    mark_dropped,
)
from runtime_flight.discuss import load_package
from runtime_flight.operator import OperatorError
from runtime_flight.performer_fal import ReadyTake, TakeRequest
from runtime_flight.prepare_pass import (
    HERO_IMAGE_PLACEHOLDER,
    PREPARE_PASS_DURATION_S,
    PREPARE_PASS_TURNS,
    _append_jsonl,
    _build_performer,
    _concat,
    _mean,
)
from runtime_flight.prepare_queue import _write_one
from runtime_flight.prompt import assemble_prompt
from runtime_flight.source import load_source_packet
from runtime_flight.spend import SpendLedger, SpendMeter
from runtime_flight.text_client import TextAttemptLimiter, TextClient
from runtime_flight.topic_map import host_voices_from_baseline
from runtime_flight.writer import Writer

READY_BUFFER_MIN_S = 45
READY_BUFFER_MAX_S = 60
DEFAULT_READY_BUFFER_S = 50
DEFAULT_MAX_INFLIGHT = 4


@dataclass(frozen=True)
class QueuedLine:
    item_id: str
    speaker: str
    line: str


def run_cook_queue(
    *,
    config: RuntimeConfig,
    inbox: Path,
    ready_buffer_s: int,
    turns: int,
    max_text_requests: int,
    out_dir: Path | None = None,
    max_inflight: int = DEFAULT_MAX_INFLIGHT,
    performer_factory=None,
    concat_fn=None,
    http_post=None,
    writer_factory=None,
) -> dict[str, Any]:
    _require_buffer(ready_buffer_s)
    if turns not in PREPARE_PASS_TURNS:
        raise OperatorError("cook-queue --turns must be 2 or 3")
    if max_inflight < 1:
        raise OperatorError("cook-queue max_inflight must be at least 1")
    return asyncio.run(
        _run_async(
            config=config,
            inbox=Path(inbox).resolve(),
            ready_buffer_s=ready_buffer_s,
            turns=turns,
            max_text_requests=max_text_requests,
            out_dir=out_dir,
            max_inflight=max_inflight,
            performer_factory=performer_factory,
            concat_fn=concat_fn,
            http_post=http_post,
            writer_factory=writer_factory,
        )
    )


def _require_buffer(ready_buffer_s: int) -> None:
    if not (READY_BUFFER_MIN_S <= ready_buffer_s <= READY_BUFFER_MAX_S):
        raise OperatorError("cook-queue --ready-buffer-s must be 45 to 60")


async def _run_async(
    *,
    config: RuntimeConfig,
    inbox: Path,
    ready_buffer_s: int,
    turns: int,
    max_text_requests: int,
    out_dir: Path | None,
    max_inflight: int,
    performer_factory,
    concat_fn,
    http_post,
    writer_factory,
) -> dict[str, Any]:
    baseline = BaselineContext.load(config.pack_manager_data_dir, config.baseline_id or "")
    voices = host_voices_from_baseline(baseline)
    run_id = f"cook-queue-{_stamp()}"
    root = Path(out_dir).resolve() if out_dir is not None else Path("out").resolve()
    work_dir = root / "cook-queue" / run_id
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
    duration_s = int(config.video_duration_s or PREPARE_PASS_DURATION_S)
    lines: deque[QueuedLine] = deque()
    inflight: dict[asyncio.Task[ReadyTake], tuple[TakeRequest, str]] = {}
    remaining: dict[str, int] = {}
    landed: set[str] = set()
    take_n = 1
    ready_s = 0
    ready_clips: list[Path] = []
    rows: list[dict[str, Any]] = []
    dropped_rows: list[dict[str, Any]] = []
    claimed: list[str] = []

    def projected_s() -> int:
        return ready_s + (len(inflight) + len(lines)) * duration_s

    async def refill() -> bool:
        if lines:
            return True
        if projected_s() >= ready_buffer_s:
            return False
        claimed_dir = claim_next(inbox)
        if claimed_dir is None:
            return False
        item_id = claimed_dir.name
        load_source_packet(claimed_dir / PACKET_NAME, claimed_dir / LOCK_NAME)
        package = load_package(claimed_dir / PACKAGE_NAME)
        thoughts = await _write_one(
            writer,
            package,
            turns=turns,
            voices=voices,
            clip_duration_s=duration_s,
        )
        claimed.append(item_id)
        remaining[item_id] = 0
        for thought in thoughts:
            lines.append(
                QueuedLine(item_id=item_id, speaker=thought.speaker, line=thought.text)
            )
            remaining[item_id] += 1
        return bool(lines)

    def fire_next() -> None:
        nonlocal take_n
        queued = lines.popleft()
        request = TakeRequest(
            take=take_n,
            speaker=queued.speaker,  # type: ignore[arg-type]
            line=queued.line,
            prompt=assemble_prompt(baseline, queued.speaker, queued.line),
            anchor="hero",
            image_url=HERO_IMAGE_PLACEHOLDER,
            baseline_id=baseline.baseline_id,
        )
        inflight[performer.start(request)] = (request, queued.item_id)
        take_n += 1

    def close_take(item_id: str, *, ok: bool) -> None:
        if ok:
            landed.add(item_id)
        left = remaining.get(item_id, 0) - 1
        remaining[item_id] = left
        if left > 0:
            return
        remaining.pop(item_id, None)
        if item_id in landed:
            mark_done(inbox, item_id)
        else:
            mark_dropped(inbox, item_id)

    while True:
        while lines and len(inflight) < max_inflight:
            fire_next()
        if projected_s() < ready_buffer_s and len(inflight) < max_inflight and not lines:
            got = await refill()
            if got:
                continue
            if not inflight:
                break
        elif not inflight and not lines:
            break
        if not inflight:
            break
        finished, _pending = await asyncio.wait(
            set(inflight), return_when=asyncio.FIRST_COMPLETED
        )
        for task in finished:
            request, item_id = inflight.pop(task)
            ready = task.result()
            cook = ready.cook.as_dict() if ready.cook is not None else {}
            row = {
                "take": ready.take,
                "tweet_id": item_id,
                "speaker": ready.speaker,
                "line": request.line,
                "status": ready.status,
                "request_id": ready.request_id,
                "reserved_cost_usd": str(ready.reserved_cost_usd),
                "clip": str(ready.clip_path) if ready.clip_path is not None else None,
                **cook,
            }
            ok = ready.status == "ready" and ready.clip_path is not None
            if ok:
                ready_s += duration_s
                ready_clips.append(Path(ready.clip_path))
                rows.append(row)
            else:
                dropped_rows.append(row)
            _append_jsonl(work_dir / "logs" / "takes.jsonl", row)
            close_take(item_id, ok=ok)

    if not ready_clips:
        raise OperatorError("cook-queue produced no ready clips")
    show_path = work_dir / "queue.mp4"
    await _concat(ready_clips, show_path, concat_fn)
    summary = {
        "run_id": run_id,
        "work_dir": str(work_dir),
        "endpoint": config.video_endpoint,
        "duration_s": duration_s,
        "mode": "content-queue",
        "ready_buffer_s": ready_buffer_s,
        "ready_s": ready_s,
        "claimed": claimed,
        "takes": rows,
        "dropped": dropped_rows,
        "recording": str(show_path),
        "mean_t_inference_s": _mean([row.get("t_inference_s") for row in rows]),
        "mean_t_cook_s": _mean([row.get("t_cook_s") for row in rows]),
        "spend_reserved_usd": str(meter.total),
    }
    (work_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
