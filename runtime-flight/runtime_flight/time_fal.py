"""Isolated sequential H3 cooks. Measures fal inference vs wall-clock time-to-file."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from runtime_flight.baseline import BaselineContext
from runtime_flight.clip import require_clip_duration_s
from runtime_flight.config import RuntimeConfig
from runtime_flight.fal_gateway import FalGateway
from runtime_flight.operator import OperatorError
from runtime_flight.performer_fal import FalPerformer, ReadyTake, TakeRequest
from runtime_flight.prompt import assemble_prompt
from runtime_flight.spend import SpendLedger, SpendMeter
from runtime_flight.timeline import write_timeline

TIME_FAL_DURATION_S = 5
TIME_FAL_MAX_TAKES = 3
TIME_FAL_LINES = (
    "The only clock that matters is the one on the cook.",
    "We wait for the picture, then we talk.",
    "Five seconds of air, whatever the queue says.",
)


def run_time_fal(
    *,
    config: RuntimeConfig,
    takes: int = TIME_FAL_MAX_TAKES,
    duration_s: int = TIME_FAL_DURATION_S,
    out_dir: Path | None = None,
    performer_factory=None,
) -> dict[str, Any]:
    duration_s = require_clip_duration_s(duration_s)
    if takes < 1 or takes > TIME_FAL_MAX_TAKES:
        raise OperatorError("time-fal takes must be 1 to 3")
    return asyncio.run(
        _run_async(
            config=config,
            takes=takes,
            duration_s=duration_s,
            out_dir=out_dir,
            performer_factory=performer_factory,
        )
    )


async def _run_async(
    *,
    config: RuntimeConfig,
    takes: int,
    duration_s: int,
    out_dir: Path | None,
    performer_factory,
) -> dict[str, Any]:
    baseline = BaselineContext.load(config.pack_manager_data_dir, config.baseline_id or "")
    run_id = f"time-fal-{_stamp()}"
    root = Path(out_dir).resolve() if out_dir is not None else Path("out").resolve()
    work_dir = root / "time-fal" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    meter = SpendMeter(
        cap_usd=config.spend_cap_usd or Decimal("8.00"),
        rate_768p_usd_per_s=config.spend_rate_768p_usd_per_s,
        duration_s=duration_s,
        mode="live",
        ledger=SpendLedger(work_dir / "reservations.jsonl"),
    )
    performer = (
        performer_factory(meter, work_dir, baseline)
        if performer_factory is not None
        else _build_performer(config, meter, work_dir, baseline.hero_path, duration_s)
    )
    rows: list[dict[str, Any]] = []
    for index in range(takes):
        line = TIME_FAL_LINES[index]
        request = TakeRequest(
            take=index + 1,
            speaker="BOT1",
            line=line,
            prompt=assemble_prompt(baseline, "BOT1", line),
            anchor="hero",
            image_url="hero",
            baseline_id=baseline.baseline_id,
        )
        ready: ReadyTake = await performer.start(request)
        cook = ready.cook.as_dict() if ready.cook is not None else {}
        row = {
            "take": ready.take,
            "status": ready.status,
            "request_id": ready.request_id,
            "reserved_cost_usd": str(ready.reserved_cost_usd),
            "clip": str(ready.clip_path) if ready.clip_path else None,
            **cook,
        }
        rows.append(row)
        _append_jsonl(work_dir / "logs" / "takes.jsonl", row)

    summary = {
        "run_id": run_id,
        "work_dir": str(work_dir),
        "duration_s": duration_s,
        "takes": rows,
        "mean_t_inference_s": _mean([row.get("t_inference_s") for row in rows]),
        "mean_t_cook_s": _mean([row.get("t_cook_s") for row in rows]),
        "mean_t_completed_s": _mean([row.get("t_completed_s") for row in rows]),
        "surplus_play_minus_cook_s": _surplus(
            duration_s, [row.get("t_cook_s") for row in rows]
        ),
        "spend_reserved_usd": str(meter.total),
    }
    (work_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    timeline_path = write_timeline(
        work_dir, title=f"cook timeline · {run_id}", duration_s=float(duration_s)
    )
    summary["timeline_html"] = str(timeline_path)
    (work_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def _build_performer(
    config: RuntimeConfig,
    meter: SpendMeter,
    work_dir: Path,
    hero_path: Path,
    duration_s: int,
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
        duration_s=duration_s,
    )


async def _fal_upload(path: Path) -> str:
    try:
        import fal_client
    except ImportError as error:
        raise OperatorError("fal-client is required for paid flights") from error
    return await asyncio.to_thread(fal_client.upload_file, Path(path))


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def _mean(values: list[Any]) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 3)


def _surplus(duration_s: int, cooks: list[Any]) -> float | None:
    numbers = [float(value) for value in cooks if isinstance(value, (int, float))]
    if not numbers:
        return None
    return round(duration_s - (sum(numbers) / len(numbers)), 3)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
