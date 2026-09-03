"""Dequeue next tweet, cook, stop at the ready buffer. Fake performer only."""

from __future__ import annotations

import ast
import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from runtime_flight.__main__ import main
from runtime_flight.config import load_config, validate_config
from runtime_flight.content_queue import enqueue, pending_ids
from runtime_flight.fal_gateway import H3_MAX_TURBO_ENDPOINT
from runtime_flight.operator import OperatorError
from runtime_flight.performer_fal import FalCookTimings, ReadyTake, TakeRequest
from runtime_flight.prepare_pass import apply_prepare_overrides
from runtime_flight.queue_worker import run_cook_queue
from runtime_flight.spend import SpendMeter, arguments_sha256
from test_prepare_queue import ScriptWriter, _write_staged
from test_preflight import _complete_env, _make_flight_setup, _write_flight_config

FORBIDDEN = {
    "harness_live",
    "obs_session",
    "playhead",
    "run_live",
    "studio",
}


@pytest.fixture
def flight_setup(tmp_path: Path) -> dict:
    return _make_flight_setup(tmp_path / "pack-root")


class InstantPerformer:
    def __init__(
        self,
        meter: SpendMeter,
        work_dir: Path,
        baseline,
        *,
        fail_takes: frozenset[int] = frozenset(),
        events: list[str] | None = None,
    ) -> None:
        self.meter = meter
        self.work_dir = Path(work_dir)
        self.baseline = baseline
        self.fail_takes = fail_takes
        self.started: list[TakeRequest] = []
        self.events = events if events is not None else []

    def start(self, request: TakeRequest) -> asyncio.Task[ReadyTake]:
        self.started.append(request)
        self.events.append(f"cook:{request.take}")
        arguments = {
            "prompt": request.prompt,
            "duration": self.meter.duration_s,
            "resolution": "768P",
            "enable_safety_checker": True,
            "prompt_expansion_mode": "balanced",
            "image_url": request.image_url,
        }
        reservation = self.meter.reserve_attempt(
            request.take, 1, arguments_sha256(arguments)
        )

        async def finish() -> ReadyTake:
            if request.take in self.fail_takes:
                return ReadyTake(
                    take=request.take,
                    speaker=request.speaker,
                    line=request.line,
                    clip_path=None,
                    frame_path=None,
                    frame_url=None,
                    anchor=request.anchor,
                    request_id=f"fail-{request.take}",
                    status="failed",
                    reserved_cost_usd=reservation.reserved_cost_usd,
                    cook=FalCookTimings(t_inference_s=1.5, t_cook_s=None),
                )
            clip = self.work_dir / "ready" / f"{request.take:03d}.mp4"
            clip.parent.mkdir(parents=True, exist_ok=True)
            clip.write_bytes(b"ready")
            return ReadyTake(
                take=request.take,
                speaker=request.speaker,
                line=request.line,
                clip_path=clip,
                frame_path=self.work_dir / "frames" / f"{request.take:03d}.png",
                frame_url=f"https://v3.fal.media/files/queue-{request.take}.png",
                anchor=request.anchor,
                request_id=f"queue-{request.take}",
                status="ready",
                reserved_cost_usd=reservation.reserved_cost_usd,
                cook=FalCookTimings(
                    t_inference_s=1.5,
                    timings={"inference": 1.5},
                    t_cook_s=3.0,
                ),
            )

        return asyncio.create_task(finish())


class EventWriter(ScriptWriter):
    def __init__(self, client, events: list[str]) -> None:
        super().__init__(client)
        self.events = events

    async def write_point(self, package, planned, next_speaker, *args, **kwargs):
        self.events.append(f"write:{package.item_id}")
        return await super().write_point(package, planned, next_speaker, *args, **kwargs)


def _config(tmp_path: Path, flight_setup: dict, monkeypatch: pytest.MonkeyPatch):
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    config_path = _write_flight_config(tmp_path, flight_setup)
    config = apply_prepare_overrides(
        load_config(config_path),
        endpoint=H3_MAX_TURBO_ENDPOINT,
        duration_s=5,
        rate_768p_usd_per_s=Decimal("0.01"),
    )
    validate_config(config, require_obs=False)
    return config


def _fill_inbox(tmp_path: Path, tweet_ids: tuple[str, ...]) -> Path:
    inbox = tmp_path / "inbox"
    for tweet_id in tweet_ids:
        enqueue(inbox, _write_staged(tmp_path, tweet_id, f"user{tweet_id}"))
    return inbox


def test_cook_queue_writes_next_item_then_cooks_and_stops_at_buffer(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path, flight_setup, monkeypatch)
    inbox = _fill_inbox(tmp_path, ("111", "222", "333", "444", "555", "666"))
    events: list[str] = []
    seen: list[InstantPerformer] = []

    def writer_factory(client):
        return EventWriter(client, events)

    def factory(meter, work_dir, baseline):
        performer = InstantPerformer(meter, work_dir, baseline, events=events)
        seen.append(performer)
        return performer

    async def concat_fn(clips, dest: Path) -> None:
        dest.write_bytes(b"concat")

    summary = run_cook_queue(
        config=config,
        inbox=inbox,
        ready_buffer_s=45,
        turns=2,
        max_text_requests=12,
        out_dir=tmp_path / "out",
        performer_factory=factory,
        concat_fn=concat_fn,
        writer_factory=writer_factory,
    )
    assert summary["mode"] == "content-queue"
    assert summary["ready_s"] >= 45
    assert summary["ready_s"] <= 60
    assert summary["claimed"] == ["111", "222", "333", "444", "555"]
    assert pending_ids(inbox) == ("666",)
    assert events[0].startswith("write:111")
    first_cook = next(i for i, item in enumerate(events) if item.startswith("cook:"))
    last_write = max(i for i, item in enumerate(events) if item.startswith("write:"))
    assert first_cook < last_write
    assert Path(summary["recording"]).read_bytes() == b"concat"
    assert "666" not in summary["claimed"]


def test_cook_queue_drops_a_failed_take_and_keeps_firing(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path, flight_setup, monkeypatch)
    inbox = _fill_inbox(tmp_path, ("111", "222", "333", "444", "555", "666"))

    def factory(meter, work_dir, baseline):
        return InstantPerformer(meter, work_dir, baseline, fail_takes=frozenset({2}))

    async def concat_fn(clips, dest: Path) -> None:
        dest.write_bytes(b"".join(path.read_bytes() for path in clips))

    summary = run_cook_queue(
        config=config,
        inbox=inbox,
        ready_buffer_s=45,
        turns=2,
        max_text_requests=12,
        out_dir=tmp_path / "out",
        performer_factory=factory,
        concat_fn=concat_fn,
        writer_factory=lambda client: ScriptWriter(client),
    )
    assert summary["dropped"][0]["take"] == 2
    assert summary["dropped"][0]["status"] == "failed"
    assert summary["ready_s"] >= 45
    assert all(row["take"] != 2 for row in summary["takes"])


def test_cook_queue_refuses_buffer_outside_45_60(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path, flight_setup, monkeypatch)
    inbox = _fill_inbox(tmp_path, ("111", "222", "333"))
    with pytest.raises(OperatorError, match="45 to 60"):
        run_cook_queue(
            config=config,
            inbox=inbox,
            ready_buffer_s=30,
            turns=2,
            max_text_requests=6,
            out_dir=tmp_path / "out",
            writer_factory=lambda client: ScriptWriter(client),
        )


def test_cook_queue_cli_refuses_without_paid_flag(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.delenv("RUNTIME_ALLOW_PAID", raising=False)
    config_path = _write_flight_config(tmp_path, flight_setup)
    code = main(
        [
            "cook-queue",
            "--config",
            str(config_path),
            "--confirm-spend",
            "12.00",
            "--inbox",
            str(tmp_path / "inbox"),
            "--confirm-text-requests",
            "6",
        ],
        cook_queue_runner=lambda **kwargs: {"ok": True},
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "paid flag absent" in captured.err


def test_enqueue_cli_copies_staged_dirs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _write_staged(tmp_path, "111", "one")
    inbox = tmp_path / "inbox"
    code = main(
        [
            "enqueue",
            "--inbox",
            str(inbox),
            str(source),
        ]
    )
    assert code == 0
    captured = capsys.readouterr()
    assert "111" in captured.out
    assert pending_ids(inbox) == ("111",)


def test_queue_worker_stays_isolated_from_obs() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "queue_worker.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN)
    assert "from runtime_flight.harness_live" not in source
    assert "from runtime_flight.obs_session" not in source
    assert "import fal_client" not in source
