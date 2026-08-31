"""Task 13B: OBS lifecycle, stream abort, watchdog, and recording post-roll."""

from __future__ import annotations

import asyncio
from pathlib import Path

from obs_harness.player_fake import FakePlayer

from runtime_flight.harness_live import CLIP_DURATION_S, FakeClock, LiveHarness
from runtime_flight.obs_session import ObsSession
from runtime_flight.writer_pipeline import WriterPipeline
from test_harness_live import FakePerformer, LiveWriter, _baseline, _meter, _package
from conftest_obs import FakeObsClient, complete_obs_client


class FakeOverlay:
    def __init__(self) -> None:
        self.healthy = True

    def mark_unhealthy(self) -> None:
        self.healthy = False


class DisconnectAtClipEnd(FakePlayer):
    def get_program_state(self) -> dict:
        state = super().get_program_state()
        on_air = state.get("on_air")
        if on_air and on_air.get("ends_at") is not None:
            if self.t + 1e-9 >= on_air["ends_at"]:
                self.connected = False
                state["connected"] = False
                state["media_ok"] = False
        return state


class LaggingRecordClient(FakeObsClient):
    def get_record_status(self):
        if self.recording and self.record_duration_ms < 90_000:
            self.record_duration_ms = min(90_000, self.record_duration_ms + 1_000)
        return super().get_record_status()


def _obs_harness(
    tmp_path: Path,
    *,
    player: FakePlayer | None = None,
    client: FakeObsClient | None = None,
    overlay: FakeOverlay | None = None,
    target_duration_s: float = 90.0,
    delay_s: float = 4.0,
) -> tuple[LiveHarness, FakePerformer, FakeObsClient, FakeOverlay]:
    clock_player = player or FakePlayer()
    clock_player.set_clip_duration(CLIP_DURATION_S)
    obs_client = client or complete_obs_client()
    session = ObsSession(client=obs_client, poll_interval_s=0.0)
    overlay = overlay or FakeOverlay()
    writer = LiveWriter()
    meter = _meter(tmp_path)
    clock = FakeClock()
    performer = FakePerformer(clock, meter, tmp_path, delay_s=delay_s)
    harness = LiveHarness(
        clock=clock,
        player=clock_player,
        pipeline=WriterPipeline(writer),
        performer=performer,
        meter=meter,
        baseline=_baseline(tmp_path),
        package=_package(),
        target_duration_s=target_duration_s,
        overlay=overlay,
        obs_session=session,
    )
    clock_player.t = 0.0
    return harness, performer, obs_client, overlay


def _run(coro):
    return asyncio.run(coro)


def test_obs_disconnect_at_clip_end_marks_watchdog_unhealthy(tmp_path: Path) -> None:
    player = DisconnectAtClipEnd()
    overlay = FakeOverlay()
    harness, _, _, overlay = _obs_harness(tmp_path, player=player, overlay=overlay)

    async def run() -> None:
        await harness.run_simulated(until_aired=2, max_t=20)

    _run(run())
    assert overlay.healthy is False
    assert any(event["kind"] == "watchdog_unhealthy" for event in harness.events)
    assert harness.stop_reason == "obs disconnect"


def test_stream_active_mid_flight_stops_submits_holds_and_never_stops_stream(
    tmp_path: Path,
) -> None:
    client = complete_obs_client()
    harness, performer, client, overlay = _obs_harness(tmp_path, client=client)

    def flip_stream() -> None:
        if harness.aired_count >= 1:
            client.streaming = True

    harness.after_step = flip_stream

    async def run() -> None:
        await harness.run_with_obs(max_t=20)

    _run(run())
    assert harness.stop_reason == "obs streaming"
    assert harness.spend_policy == "stop"
    assert harness.flags["hold"] is True
    assert client.streaming is True
    assert not any(call[0] == "stop_stream" for call in client.calls)
    assert ("stop_record",) in client.calls
    assert any(event["kind"] == "stream_status" for event in harness.events)
    assert any(event["kind"] == "stream_active_abort" for event in harness.events)
    assert any(event["kind"] == "recording_stopped" for event in harness.events)
    statuses = [event for event in harness.events if event["kind"] == "stream_status"]
    assert statuses
    times = [event["t"] for event in statuses]
    if len(times) >= 2:
        gaps = [b - a for a, b in zip(times, times[1:])]
        assert all(gap <= 1.0001 for gap in gaps)


def test_post_roll_waits_until_recording_covers_programme(tmp_path: Path) -> None:
    complete = complete_obs_client()
    client = LaggingRecordClient(
        scenes=complete.scenes,
        inputs=complete.inputs,
        scene_items=complete.scene_items,
        supported_kinds=complete.supported_kinds,
    )
    client.record_duration_ms = 70_000
    harness, _, client, _ = _obs_harness(
        tmp_path, client=client, target_duration_s=90.0, delay_s=0.0
    )

    async def run() -> None:
        await harness.run_with_obs(max_t=90.0)

    _run(run())
    assert client.record_duration_ms >= 90_000
    assert any(event["kind"] == "programme_hold" for event in harness.events)
    assert any(event["kind"] == "post_roll" for event in harness.events)
    assert ("stop_record",) in client.calls
    assert harness.recording_path == client.output_path


def test_run_with_obs_stops_recording_in_finally(tmp_path: Path) -> None:
    client = complete_obs_client()
    harness, _, client, _ = _obs_harness(tmp_path, client=client, delay_s=0.0)

    def boom() -> None:
        raise RuntimeError("forced failure")

    harness.after_step = boom

    async def run() -> None:
        await harness.run_with_obs(max_t=5)

    try:
        _run(run())
    except RuntimeError as error:
        assert "forced failure" in str(error)
    assert ("start_record",) in client.calls
    assert ("stop_record",) in client.calls
    assert not any(call[0] == "stop_stream" for call in client.calls)
