"""Production runner wiring and wall-clock loop."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from runtime_flight.__main__ import main
from runtime_flight.flight import run_paid_flight
from runtime_flight.harness_live import CLIP_DURATION_S, LiveHarness
from runtime_flight.obs_session import ObsSession
from runtime_flight.writer_pipeline import WriterPipeline
from test_harness_live import FakePerformer, LiveWriter, _baseline, _meter, _package
from test_preflight import _complete_env, _make_flight_setup, _write_flight_config
from conftest_obs import complete_obs_client
from obs_harness.player_fake import FakePlayer


class SleepClock:
    def __init__(self) -> None:
        self._t = 0.0

    def monotonic(self) -> float:
        return self._t


class FakeOverlay:
    def start(self) -> str:
        return "http://127.0.0.1:0/"

    def stop(self) -> None:
        return None

    def set_card(self, **kwargs) -> None:
        del kwargs

    def mark_unhealthy(self) -> None:
        return None


@pytest.fixture
def flight_setup(tmp_path: Path) -> dict:
    return _make_flight_setup(tmp_path / "pack-root")


def test_run_wall_uses_injected_sleep_instead_of_fake_advance(tmp_path: Path) -> None:
    clock = SleepClock()
    slept: list[float] = []

    async def sleep(dt: float) -> None:
        slept.append(dt)
        clock._t += dt

    player = FakePlayer()
    player.set_clip_duration(CLIP_DURATION_S)
    meter = _meter(tmp_path)
    performer = FakePerformer(clock, meter, tmp_path, delay_s=0.0)  # type: ignore[arg-type]
    harness = LiveHarness(
        clock=clock,  # type: ignore[arg-type]
        player=player,
        pipeline=WriterPipeline(LiveWriter()),
        performer=performer,
        meter=meter,
        baseline=_baseline(tmp_path),
        package=_package(),
        target_duration_s=10.0,
        sleep=sleep,
    )

    asyncio.run(harness.run_wall(until_aired=1, max_t=10.0, sleep=sleep))
    assert slept
    assert all(item >= 0 for item in slept)
    assert harness.aired_count >= 1


def test_run_paid_flight_with_injected_performer(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    config_path = _write_flight_config(tmp_path, flight_setup)
    from runtime_flight.config import load_config, validate_config

    config = load_config(config_path)
    validate_config(config)
    client = complete_obs_client()
    client.record_duration_ms = 90_000
    recording = tmp_path / "recording.mkv"
    recording.write_bytes(b"recording")
    client.output_path = str(recording)
    session = ObsSession(client=client, poll_interval_s=0.0)
    player = FakePlayer()
    player.set_clip_duration(CLIP_DURATION_S)
    clock = __import__("runtime_flight.harness_live", fromlist=["FakeClock"]).FakeClock()

    def factory(live_clock, meter, work_dir):
        return FakePerformer(live_clock, meter, work_dir, delay_s=0.0)

    code = run_paid_flight(
        config=config,
        mode="smoke",
        max_text_requests=24,
        max_fal_submissions=2,
        session=session,
        out_dir=tmp_path / "out" / "flights",
        http_post=_planner_writer_http,
        performer_factory=factory,
        player=player,
        clock=clock,
        overlay=FakeOverlay(),
        sleep=lambda _dt: None,
    )
    assert code == 0
    bundles = list((tmp_path / "out" / "flights").iterdir())
    assert bundles
    assert (bundles[0] / "flight.json").is_file()
    assert ("start_record",) in client.calls
    assert ("stop_record",) in client.calls
    assert not any(call[0] == "stop_stream" for call in client.calls)


def test_rehearse_cli_zero_cost(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_env(monkeypatch, flight_setup)
    config_path = _write_flight_config(tmp_path, flight_setup)
    monkeypatch.chdir(tmp_path)
    code = main(["rehearse", "--config", str(config_path)])
    assert code == 0
    flights = list((tmp_path / "out" / "flights").glob("rehearse-*"))
    assert flights
    assert (flights[0] / "flight.json").is_file()


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
            return {"choices": [{"message": {"content": codec.dumps(content)}}], "usage": {}}

    return Response()
