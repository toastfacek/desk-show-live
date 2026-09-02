"""Prepared 3-segment preroll. Fake performer only."""

from __future__ import annotations

import ast
import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from runtime_flight.__main__ import main
from runtime_flight.config import load_config, validate_config
from runtime_flight.fal_gateway import H3_MAX_TURBO_ENDPOINT
from runtime_flight.performer_fal import FalCookTimings, ReadyTake, TakeRequest
from runtime_flight.prepare_pass import (
    PREPARE_PASS_LINES,
    apply_prepare_overrides,
    run_prepare_pass,
)
from runtime_flight.spend import SpendMeter, arguments_sha256
from test_preflight import (
    _complete_env,
    _make_flight_setup,
    _write_flight_config,
)

FORBIDDEN = {
    "writer",
    "post",
    "generator",
    "playhead",
    "run_live",
    "studio",
    "harness_live",
    "obs_session",
}


@pytest.fixture
def flight_setup(tmp_path: Path) -> dict:
    return _make_flight_setup(tmp_path / "pack-root")


class BarrierPerformer:
    def __init__(self, meter: SpendMeter, work_dir: Path, baseline) -> None:
        self.meter = meter
        self.work_dir = Path(work_dir)
        self.baseline = baseline
        self.started: list[TakeRequest] = []
        self.ready_order: list[int] = []
        self.stop_requested = False
        self._active = 0
        self._gate = asyncio.Event()

    @property
    def active_requests(self) -> int:
        return self._active

    def start(self, request: TakeRequest) -> asyncio.Task[ReadyTake]:
        self.started.append(request)
        self._active += 1
        if len(self.started) == 3:
            self._gate.set()
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
            try:
                await self._gate.wait()
                clip = self.work_dir / "ready" / f"{request.take:03d}.mp4"
                clip.parent.mkdir(parents=True, exist_ok=True)
                clip.write_bytes(b"ready")
                self.ready_order.append(request.take)
                return ReadyTake(
                    take=request.take,
                    speaker=request.speaker,
                    line=request.line,
                    clip_path=clip,
                    frame_path=self.work_dir / "frames" / f"{request.take:03d}.png",
                    frame_url=f"https://v3.fal.media/files/prepare-{request.take}.png",
                    anchor=request.anchor,
                    request_id=f"prepare-{request.take}",
                    status="ready",
                    reserved_cost_usd=reservation.reserved_cost_usd,
                    cook=FalCookTimings(
                        t_inference_s=1.51,
                        timings={"inference": 1.51},
                        t_submit_s=0.2,
                        t_poll_s=2.1,
                        t_completed_s=2.3,
                        t_download_s=0.3,
                        t_post_s=0.4,
                        t_cook_s=3.0,
                    ),
                )
            finally:
                self._active -= 1

        return asyncio.create_task(finish())


def test_prepare_pass_cooks_all_three_before_concat(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    seen: list[BarrierPerformer] = []
    concat_after: list[int] = []

    def factory(meter, work_dir, baseline):
        performer = BarrierPerformer(meter, work_dir, baseline)
        seen.append(performer)
        return performer

    async def concat_fn(clips, dest: Path) -> None:
        concat_after.append(len(seen[0].ready_order))
        dest.write_bytes(b"concat")

    summary = run_prepare_pass(
        config=config,
        out_dir=tmp_path / "out",
        performer_factory=factory,
        concat_fn=concat_fn,
    )
    assert summary["endpoint"] == H3_MAX_TURBO_ENDPOINT
    assert summary["duration_s"] == 5
    assert summary["segments"] == 3
    assert summary["mode"] == "prepare-ahead"
    assert summary["spend_reserved_usd"] == "0.15"
    assert [row["t_inference_s"] for row in summary["takes"]] == [1.51, 1.51, 1.51]
    assert [row["anchor"] for row in summary["takes"]] == ["hero", "hero", "hero"]
    assert [req.line for req in seen[0].started] == [line for _, line in PREPARE_PASS_LINES]
    assert [req.speaker for req in seen[0].started] == [speaker for speaker, _ in PREPARE_PASS_LINES]
    assert concat_after == [3]
    assert Path(summary["recording"]).read_bytes() == b"concat"
    assert Path(summary["timeline_html"]).is_file()
    assert (tmp_path / "out" / "prepare-pass" / summary["run_id"] / "summary.json").is_file()


def test_prepare_pass_refuses_without_paid_flag(
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
            "prepare-pass",
            "--config",
            str(config_path),
            "--confirm-spend",
            "12.00",
        ],
        prepare_pass_runner=lambda **kwargs: {"ok": True},
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "paid flag absent" in captured.err


def test_prepare_pass_refuses_duration_other_than_five(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    config_path = _write_flight_config(tmp_path, flight_setup)
    code = main(
        [
            "prepare-pass",
            "--config",
            str(config_path),
            "--confirm-spend",
            "12.00",
            "--duration",
            "15",
        ],
        prepare_pass_runner=lambda **kwargs: {"ok": True},
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "duration" in captured.err


def test_prepare_pass_module_stays_isolated_from_obs_and_writer() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "prepare_pass.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN)
    assert "from runtime_flight.writer" not in source
    assert "from runtime_flight.harness_live" not in source
    assert "import fal_client" not in source.split("async def _fal_upload")[0]
