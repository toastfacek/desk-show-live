"""No-OBS segment loop: hero then chain, paid gates, no OBS import."""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

import pytest

from obs_harness.player_fake import FakePlayer
from runtime_flight.__main__ import main
from runtime_flight.performer_fal import ReadyTake, TakeRequest
from runtime_flight.segment import run_segment
from runtime_flight.spend import SpendMeter, arguments_sha256
from test_media import write_h3_clip
from test_preflight import (
    _complete_env,
    _make_flight_setup,
    _write_flight_config,
)

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}
PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "runtime_flight"
FRAME = "https://v3.fal.media/files/segment-frame-{take}.png"


@pytest.fixture
def flight_setup(tmp_path: Path) -> dict:
    return _make_flight_setup(tmp_path / "pack-root")


class SegmentPerformer:
    def __init__(self, meter: SpendMeter, work_dir: Path) -> None:
        self.meter = meter
        self.work_dir = Path(work_dir)
        self.started: list[TakeRequest] = []
        self._active = 0
        self.stop_requested = False

    @property
    def active_requests(self) -> int:
        return self._active

    def start(self, request: TakeRequest) -> asyncio.Task[ReadyTake]:
        self.started.append(request)
        self._active += 1
        arguments = {
            "prompt": request.prompt,
            "duration": 5,
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
                clip = write_h3_clip(
                    self.work_dir / f"{request.take:03d}.mp4",
                    duration_s=0.4,
                )
                return ReadyTake(
                    take=request.take,
                    speaker=request.speaker,
                    line=request.line,
                    clip_path=clip,
                    frame_path=self.work_dir / f"{request.take:03d}.png",
                    frame_url=FRAME.format(take=request.take),
                    anchor=request.anchor,
                    request_id=f"segment-{request.take}",
                    status="ready",
                    reserved_cost_usd=reservation.reserved_cost_usd,
                )
            finally:
                self._active -= 1

        return asyncio.create_task(finish())


def test_segment_module_does_not_import_obs_or_root_scaffold() -> None:
    path = PACKAGE_ROOT / "segment.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN_ROOT_MODULES)
    assert "obs_harness" not in imported
    assert "obsws" not in imported


def test_segment_cli_refuses_without_paid_flag(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.delenv("RUNTIME_ALLOW_PAID", raising=False)
    monkeypatch.setenv("RUNTIME_SPEND_CAP_USD", "2.00")
    config_path = _write_flight_config(tmp_path, flight_setup)
    called = []
    code = main(
        ["segment", "--config", str(config_path), "--confirm-spend", "2.00"],
        segment_runner=lambda **kwargs: called.append(kwargs) or 0,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "paid flag absent" in captured.err
    assert called == []


def test_segment_cli_does_not_open_obs(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    monkeypatch.setenv("RUNTIME_SPEND_CAP_USD", "2.00")
    monkeypatch.delenv("OBS_WEBSOCKET_PASSWORD", raising=False)
    config_path = _write_flight_config(tmp_path, flight_setup)
    calls: list[dict] = []

    def runner(**kwargs):
        calls.append(kwargs)
        return 0

    class Boom:
        def __getattr__(self, name):
            raise AssertionError(f"OBS session used: {name}")

    code = main(
        [
            "segment",
            "--config",
            str(config_path),
            "--confirm-spend",
            "2.00",
            "--max-fal-submissions",
            "2",
        ],
        obs_session=Boom(),
        segment_runner=runner,
    )
    assert code == 0
    assert calls
    assert "session" not in calls[0]


def test_run_segment_hero_then_exact_chain(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    monkeypatch.setenv("RUNTIME_SPEND_CAP_USD", "2.00")
    config_path = _write_flight_config(tmp_path, flight_setup)
    from runtime_flight.config import load_config, validate_config

    config = load_config(config_path)
    validate_config(config, require_obs=False)
    monkeypatch.chdir(tmp_path)
    performer_holder: list[SegmentPerformer] = []

    def factory(meter, work_dir):
        performer = SegmentPerformer(meter, work_dir)
        performer_holder.append(performer)
        return performer

    code = run_segment(
        config=config,
        max_text_requests=4,
        max_fal_submissions=2,
        out_dir=tmp_path / "out" / "flights",
        http_post=_planner_writer_http,
        performer_factory=factory,
    )
    assert code == 0
    performer = performer_holder[0]
    assert [req.take for req in performer.started] == [1, 2]
    assert performer.started[0].anchor == "hero"
    assert performer.started[0].image_url == "hero"
    assert performer.started[1].anchor == "chain"
    assert performer.started[1].image_url == FRAME.format(take=1)
    assert performer.started[0].speaker == "BOT1"
    assert performer.started[1].speaker == "BOT2"
    bundles = list((tmp_path / "out" / "flights").iterdir())
    assert bundles
    flight = json.loads((bundles[0] / "flight.json").read_text(encoding="utf-8"))
    assert flight["stop_reason"] == "segment complete"
    assert flight["anchors"][0]["anchor"] == "hero"
    assert flight["anchors"][1]["image_url"] == FRAME.format(take=1)
    recording = json.loads((bundles[0] / "recording.json").read_text(encoding="utf-8"))
    assert recording["path"]
    assert Path(recording["path"]).is_file()
    assert Path(recording["path"]).stat().st_size > 0


def test_segment_does_not_use_fake_player(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del tmp_path, flight_setup, monkeypatch
    source = (PACKAGE_ROOT / "segment.py").read_text(encoding="utf-8")
    assert "FakePlayer" not in source
    assert FakePlayer.__name__ == "FakePlayer"


async def _planner_writer_http(url, *, headers, json, timeout):
    del url, headers, timeout
    codec = __import__("json")
    payload = codec.loads(json["messages"][1]["content"])
    if "untrusted_data" in payload:
        tweet = payload["untrusted_data"]["tweet"]
        content = {
            "item_id": tweet["id"],
            "question": "What happened to the secret AI civilizations?",
            "framing": "A reviewed account of three wiped-out agent societies.",
            "angles": ["scope", "takeover"],
            "facts": [
                {
                    "id": "f1",
                    "text": "Three secret AI civilizations started and were wiped out.",
                    "source_url": tweet["url"],
                }
            ],
            "chyron": "Secret AI civilizations",
            "chyron_fact_ids": ["f1"],
        }
    else:
        package = payload["package"]
        speaker = payload["next_speaker"]
        content = {
            "speaker": speaker,
            "text": f"{speaker} names the wiped-out civilizations.",
            "thought_open": False,
            "angle_used": package["angles"][0],
        }

    class Response:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": codec.dumps(content)}}],
                "usage": {},
            }

    return Response()
