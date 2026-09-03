"""Infinite list orchestrator: next tweet, dissect, write, cook. No OBS."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
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
    pending_ids,
    release_claimed,
)
from runtime_flight.discuss import load_package
from runtime_flight.evidence import package_as_dict
from runtime_flight.list_load import load_list, pull_next_page
from runtime_flight.operator import OperatorError
from runtime_flight.performer_fal import ReadyTake, TakeRequest
from runtime_flight.prepare_pass import (
    HERO_IMAGE_PLACEHOLDER,
    PREPARE_PASS_DURATION_S,
    PREPARE_PASS_TURNS,
    _append_jsonl,
    _build_performer,
    _concat,
)
from runtime_flight.prepare_queue import _write_one
from runtime_flight.prompt import assemble_prompt
from runtime_flight.segment_planner import SegmentPlanner, SegmentPlannerError
from runtime_flight.source import SourceError, load_source_packet
from runtime_flight.runway import has_runway, resolve_until
from runtime_flight.spend import SpendCapExceeded, SpendLedger, SpendMeter
from runtime_flight.text_client import TextAttemptLimiter, TextClient, TextClientError
from runtime_flight.topic_map import host_voices_from_baseline
from runtime_flight.writer import Writer, WriterError

PREFETCH_PENDING = 3


def run_orchestrator(
    *,
    config: RuntimeConfig,
    inbox: Path,
    turns: int,
    max_text_requests: int,
    until: str | None = None,
    out_dir: Path | None = None,
    list_url: str | None = None,
    list_file: Path | None = None,
    bearer: str | None = None,
    http_get=None,
    http_post=None,
    fixtures: dict[str, dict[str, Any]] | None = None,
    performer_factory=None,
    concat_fn=None,
    writer_factory=None,
    planner_factory=None,
    now_fn: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    if turns not in PREPARE_PASS_TURNS:
        raise OperatorError("run-list --turns must be 2 or 3")
    clock = now_fn or (lambda: datetime.now(timezone.utc))
    deadline = resolve_until(until)
    inbox = Path(inbox).resolve()
    if list_url or list_file:
        load_list(
            inbox,
            list_url=list_url,
            list_file=list_file,
            bearer=bearer,
            http_get=http_get,
            fixtures=fixtures,
        )
    return asyncio.run(
        _run_async(
            config=config,
            inbox=inbox,
            deadline=deadline,
            turns=turns,
            max_text_requests=max_text_requests,
            out_dir=out_dir,
            bearer=bearer,
            http_get=http_get,
            http_post=http_post,
            fixtures=fixtures,
            performer_factory=performer_factory,
            concat_fn=concat_fn,
            writer_factory=writer_factory,
            planner_factory=planner_factory,
            now_fn=clock,
        )
    )


async def _run_async(
    *,
    config: RuntimeConfig,
    inbox: Path,
    deadline: datetime,
    turns: int,
    max_text_requests: int,
    out_dir: Path | None,
    bearer: str | None,
    http_get,
    http_post,
    fixtures,
    performer_factory,
    concat_fn,
    writer_factory,
    planner_factory,
    now_fn: Callable[[], datetime],
) -> dict[str, Any]:
    baseline = BaselineContext.load(config.pack_manager_data_dir, config.baseline_id or "")
    voices = host_voices_from_baseline(baseline)
    run_id = f"run-list-{_stamp(now_fn())}"
    root = Path(out_dir).resolve() if out_dir is not None else Path("out").resolve()
    work_dir = root / "run-list" / run_id
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
    planner = (
        planner_factory(client)
        if planner_factory is not None
        else SegmentPlanner(client)
    )
    duration_s = int(config.video_duration_s or PREPARE_PASS_DURATION_S)
    take_n = 1
    ready_s = 0
    ready_clips: list[Path] = []
    commented: list[str] = []
    dropped: list[dict[str, Any]] = []
    stop_reason = "empty"
    release_claimed(inbox)

    while True:
        if deadline is not None and now_fn() >= deadline:
            stop_reason = "until"
            break
        if len(pending_ids(inbox)) < PREFETCH_PENDING:
            pull_next_page(inbox, bearer=bearer, http_get=http_get, fixtures=fixtures)
        pending = len(pending_ids(inbox))
        if not has_runway(
            reserved_usd=meter.total,
            cap_usd=meter.cap_usd,
            take_cost_usd=meter.next_cost,
            text_left=limiter.max_requests - limiter.attempts,
            pending=pending,
        ):
            stop_reason = "empty" if pending < 1 else "runway"
            break
        claimed = claim_next(inbox, dissected=False)
        if claimed is None:
            stop_reason = "empty"
            break
        item_id = claimed.name
        try:
            load_source_packet(claimed / PACKET_NAME, claimed / LOCK_NAME)
            if not (claimed / PACKAGE_NAME).is_file():
                source = load_source_packet(claimed / PACKET_NAME, claimed / LOCK_NAME)
                package = await planner.plan(
                    source,
                    baseline,
                    time_budget_s=int(config.target_duration_s),
                    voices=voices,
                )
                (claimed / PACKAGE_NAME).write_text(
                    json.dumps(package_as_dict(package), indent=2, ensure_ascii=False)
                    + "\n",
                    encoding="utf-8",
                )
            package = load_package(claimed / PACKAGE_NAME)
            thoughts = await _write_one(
                writer,
                package,
                turns=turns,
                voices=voices,
                clip_duration_s=duration_s,
            )
        except (
            SourceError,
            SegmentPlannerError,
            WriterError,
            TextClientError,
            OperatorError,
        ) as error:
            if isinstance(error, TextClientError) and "budget" in str(error):
                mark_dropped(inbox, item_id)
                dropped.append({"tweet_id": item_id, "reason": "runway"})
                stop_reason = "runway"
                break
            mark_dropped(inbox, item_id)
            dropped.append({"tweet_id": item_id, "reason": str(error)})
            continue

        any_ready = False
        for thought in thoughts:
            request = TakeRequest(
                take=take_n,
                speaker=thought.speaker,
                line=thought.text,
                prompt=assemble_prompt(baseline, thought.speaker, thought.text),
                anchor="hero",
                image_url=HERO_IMAGE_PLACEHOLDER,
                baseline_id=baseline.baseline_id,
            )
            take_n += 1
            try:
                ready: ReadyTake = await performer.start(request)
            except SpendCapExceeded:
                mark_dropped(inbox, item_id)
                dropped.append({"tweet_id": item_id, "reason": "runway"})
                stop_reason = "runway"
                any_ready = False
                break
            row = {
                "take": ready.take,
                "tweet_id": item_id,
                "speaker": ready.speaker,
                "line": request.line,
                "status": ready.status,
                "clip": str(ready.clip_path) if ready.clip_path is not None else None,
            }
            _append_jsonl(work_dir / "logs" / "takes.jsonl", row)
            if ready.status == "ready" and ready.clip_path is not None:
                ready_s += duration_s
                ready_clips.append(Path(ready.clip_path))
                any_ready = True
            else:
                dropped.append({"tweet_id": item_id, "take": ready.take, "reason": ready.status})
        if stop_reason == "runway":
            break
        if any_ready:
            mark_done(inbox, item_id)
            commented.append(item_id)
        else:
            mark_dropped(inbox, item_id)

    recording = None
    if ready_clips:
        show_path = work_dir / "rundown.mp4"
        await _concat(ready_clips, show_path, concat_fn)
        recording = str(show_path)
    summary = {
        "run_id": run_id,
        "work_dir": str(work_dir),
        "mode": "run-list",
        "until": deadline.isoformat() if deadline is not None else None,
        "stop_reason": stop_reason,
        "commented": commented,
        "dropped": dropped,
        "ready_s": ready_s,
        "recording": recording,
        "spend_reserved_usd": str(meter.total),
        "text_attempts": limiter.attempts,
    }
    (work_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def _stamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
