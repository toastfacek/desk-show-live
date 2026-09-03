"""Isolated sequential fal timing probe. Fake performer only."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from runtime_flight.__main__ import main
from runtime_flight.performer_fal import FalCookTimings, ReadyTake, TakeRequest
from runtime_flight.spend import SpendMeter, arguments_sha256
from runtime_flight.time_fal import TIME_FAL_LINES, run_time_fal
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


class TimingPerformer:
    def __init__(self, meter: SpendMeter, work_dir: Path, baseline) -> None:
        self.meter = meter
        self.work_dir = Path(work_dir)
        self.baseline = baseline
        self.started: list[TakeRequest] = []
        self.stop_requested = False
        self._active = 0

    @property
    def active_requests(self) -> int:
        return self._active

    def start(self, request: TakeRequest) -> asyncio.Task[ReadyTake]:
        self.started.append(request)
        self._active += 1
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
                clip = self.work_dir / "ready" / f"{request.take:03d}.mp4"
                clip.parent.mkdir(parents=True, exist_ok=True)
                clip.write_bytes(b"ready")
                return ReadyTake(
                    take=request.take,
                    speaker=request.speaker,
                    line=request.line,
                    clip_path=clip,
                    frame_path=self.work_dir / "frames" / f"{request.take:03d}.png",
                    frame_url=f"https://v3.fal.media/files/time-fal-{request.take}.png",
                    anchor=request.anchor,
                    request_id=f"time-fal-{request.take}",
                    status="ready",
                    reserved_cost_usd=reservation.reserved_cost_usd,
                    cook=FalCookTimings(
                        t_inference_s=2.71,
                        timings={"inference": 2.71},
                        t_submit_s=0.2,
                        t_poll_s=3.1,
                        t_completed_s=3.3,
                        t_download_s=0.4,
                        t_post_s=0.5,
                        t_cook_s=4.2,
                    ),
                )
            finally:
                self._active -= 1

        return asyncio.create_task(finish())


def test_time_fal_runs_three_sequential_hero_cooks(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    config_path = _write_flight_config(tmp_path, flight_setup)
    from runtime_flight.config import load_config, validate_config

    config = load_config(config_path)
    validate_config(config, require_obs=False)
    seen: list[TimingPerformer] = []

    def factory(meter, work_dir, baseline):
        performer = TimingPerformer(meter, work_dir, baseline)
        seen.append(performer)
        return performer

    summary = run_time_fal(
        config=config,
        takes=3,
        duration_s=5,
        out_dir=tmp_path / "out",
        performer_factory=factory,
    )
    assert summary["duration_s"] == 5
    assert len(summary["takes"]) == 3
    assert [row["t_inference_s"] for row in summary["takes"]] == [2.71, 2.71, 2.71]
    assert summary["mean_t_inference_s"] == 2.71
    assert summary["mean_t_cook_s"] == 4.2
    assert summary["surplus_play_minus_cook_s"] == pytest.approx(0.8)
    assert summary["spend_reserved_usd"] == "1.20"
    assert seen[0].started[0].anchor == "hero"
    assert seen[0].started[1].anchor == "hero"
    assert [req.line for req in seen[0].started] == list(TIME_FAL_LINES)
    assert (tmp_path / "out" / "time-fal" / summary["run_id"] / "summary.json").is_file()
    assert Path(summary["timeline_html"]).is_file()
    assert "Flame graph" in Path(summary["timeline_html"]).read_text(encoding="utf-8")


def test_time_fal_refuses_without_paid_flag(
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
            "time-fal",
            "--config",
            str(config_path),
            "--confirm-spend",
            "12.00",
            "--takes",
            "3",
        ],
        time_fal_runner=lambda **kwargs: {"ok": True},
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "paid flag absent" in captured.err


def test_time_fal_refuses_duration_other_than_five(
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
            "time-fal",
            "--config",
            str(config_path),
            "--confirm-spend",
            "12.00",
            "--duration",
            "15",
        ],
        time_fal_runner=lambda **kwargs: {"ok": True},
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "duration" in captured.err


def test_time_fal_module_stays_isolated_from_obs_and_writer() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "time_fal.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN)
    source = path.read_text(encoding="utf-8")
    assert "from runtime_flight.writer" not in source
    assert "from runtime_flight.harness_live" not in source
