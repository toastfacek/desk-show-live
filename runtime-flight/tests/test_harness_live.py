"""Task 13: realtime flight state machine with fake clock, OBS, Writer, and Performer."""

from __future__ import annotations

import ast
import asyncio
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from obs_harness.player_fake import FakePlayer
from PIL import Image

from runtime_flight.baseline import BaselineContext, CharacterPackTruth, ScenePackTruth
from runtime_flight.harness_live import (
    CLIP_DURATION_S,
    FakeClock,
    LiveHarness,
    remaining_submit_slots,
    writer_phase,
)
from runtime_flight.models import Fact, SegmentPackage, Thought, TweetCard
from runtime_flight.performer_fal import ReadyTake, TakeRequest
from runtime_flight.source import (
    EXPECTED_AUTHOR,
    EXPECTED_LINKED_URL,
    EXPECTED_TWEET_ID,
    EXPECTED_TWEET_URL,
)
from runtime_flight.spend import SpendLedger, SpendMeter, arguments_sha256
from runtime_flight.writer import WriterError
from runtime_flight.writer_pipeline import WriterPipeline

from conftest import character_manifest_v2, scene_manifest_v2

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}

RATE = Decimal("0.08")
NEXT_COST = RATE * Decimal(5)
FRAME_URL = "https://v3.fal.media/files/frame-{take}.png"
BASELINE_ID = "baseline-live-locked"


def _character(slot: str) -> CharacterPackTruth:
    manifest = character_manifest_v2()
    if slot == "BOT2":
        invariants = dict(manifest["visual_invariants"])
        invariants["silhouette"] = "Broad rounded mint software sprite."
        manifest = {**manifest, "visual_invariants": invariants}
    return CharacterPackTruth(
        slot=slot,  # type: ignore[arg-type]
        pack_id=f"char-{slot.lower()}",
        version=2,
        display_name=slot,
        manifest=MappingProxyType(manifest),
    )


def _baseline(tmp_path: Path, *, reanchor_every: int = 60) -> BaselineContext:
    hero = tmp_path / "hero.png"
    Image.new("RGB", (1344, 768), (9, 9, 9)).save(hero, format="PNG")
    return BaselineContext(
        baseline_id=BASELINE_ID,
        hero_path=hero,
        hero_sha256="h" * 64,
        host_map={"BOT1": "host_a", "BOT2": "host_b"},
        display_names={"BOT1": "PHASEONE[lol]", "BOT2": "deb"},
        reanchor_every=reanchor_every,
        frame={"w": 1920, "h": 1080, "fps": 30},
        characters=(_character("BOT1"), _character("BOT2")),
        scene=ScenePackTruth(
            pack_id="scene-1",
            version=2,
            manifest=MappingProxyType(scene_manifest_v2()),
        ),
    )


def _package() -> SegmentPackage:
    return SegmentPackage(
        item_id=EXPECTED_TWEET_ID,
        question="What happened to the secret AI civilizations?",
        framing="A reviewed account of three wiped-out agent societies.",
        angles=("scope", "takeover"),
        facts=(
            Fact(
                id="f1",
                text="Three secret AI civilizations started and were wiped out.",
                source_url=EXPECTED_TWEET_URL,
            ),
            Fact(
                id="f2",
                text="The article retells the OpenAI and Hugging Face story.",
                source_url=EXPECTED_LINKED_URL,
            ),
        ),
        chyron="Secret AI civilizations",
        chyron_fact_ids=("f1",),
        center=TweetCard(
            author=EXPECTED_AUTHOR,
            text="Hello café\nworld",
            url=EXPECTED_TWEET_URL,
        ),
    )


class LiveWriter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def write(
        self,
        package: SegmentPackage,
        planned_transcript: tuple[Thought, ...],
        next_speaker: Literal["BOT1", "BOT2"],
        thought_open: bool,
        segment_phase: Literal["open", "develop", "close"],
        target_duration_s: float = 4.3,
        reissue: Literal["shorter, blander"] | None = None,
        **kwargs: Any,
    ) -> Thought:
        self.calls.append(
            {
                "next_speaker": next_speaker,
                "segment_phase": segment_phase,
                "reissue": reissue,
                "thought_open": thought_open,
            }
        )
        n = len(self.calls)
        return Thought(
            speaker=next_speaker,
            text=f"{next_speaker} names the wiped-out civilizations {n}.",
            thought_open=False,
            angle_used=package.angles[0],
        )


class ContinuingWriter:
    """Same host keeps the thought open so take 2 can chain."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def write(
        self,
        package: SegmentPackage,
        planned_transcript: tuple[Thought, ...],
        next_speaker: Literal["BOT1", "BOT2"],
        thought_open: bool,
        segment_phase: Literal["open", "develop", "close"],
        target_duration_s: float = 4.3,
        reissue: Literal["shorter, blander"] | None = None,
        **kwargs: Any,
    ) -> Thought:
        self.calls.append(
            {
                "next_speaker": next_speaker,
                "segment_phase": segment_phase,
                "reissue": reissue,
                "thought_open": thought_open,
            }
        )
        n = len(self.calls)
        return Thought(
            speaker=next_speaker,
            text=f"{next_speaker} keeps the thought going {n}.",
            thought_open=n % 2 == 1,
            angle_used=package.angles[0],
        )


class FailingWriter:
    async def write(self, *args: Any, **kwargs: Any) -> Thought:
        raise WriterError("writer down")


class FakePerformer:
    def __init__(
        self,
        clock: FakeClock,
        meter: SpendMeter,
        work_dir: Path,
        *,
        delay_s: float = 4.0,
        forced_late_takes: tuple[int, ...] = (),
        forced_late_delay_s: float = 8.0,
        fail_takes: tuple[int, ...] = (),
        drop_422_takes: tuple[int, ...] = (),
    ) -> None:
        self.clock = clock
        self.meter = meter
        self.work_dir = work_dir
        self.delay_s = delay_s
        self.forced_late_takes = set(forced_late_takes)
        self.forced_late_delay_s = forced_late_delay_s
        self.fail_takes = set(fail_takes)
        self.drop_422_takes = set(drop_422_takes)
        self.started: list[TakeRequest] = []
        self._active = 0
        self.max_inflight = 0
        self._consecutive_failures = 0
        self.stop_requested = False

    @property
    def active_requests(self) -> int:
        return self._active

    def delay_for(self, take: int) -> float:
        if take in self.forced_late_takes:
            return self.forced_late_delay_s
        return self.delay_s

    def start(self, request: TakeRequest) -> asyncio.Task[ReadyTake]:
        self.started.append(request)
        self._active += 1
        self.max_inflight = max(self.max_inflight, self._active)
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
        ready_at = self.clock.monotonic() + self.delay_for(request.take)

        async def wait() -> ReadyTake:
            try:
                while self.clock.monotonic() < ready_at:
                    await asyncio.sleep(0)
                return self._finish(request, reservation.reserved_cost_usd)
            finally:
                self._active -= 1

        return asyncio.create_task(wait())

    def _finish(self, request: TakeRequest, reserved: Decimal) -> ReadyTake:
        if request.take in self.drop_422_takes:
            self._consecutive_failures = 0
            return ReadyTake(
                take=request.take,
                speaker=request.speaker,
                line=request.line,
                clip_path=None,
                frame_path=None,
                frame_url=None,
                anchor=request.anchor,
                request_id=None,
                status="dropped_422",
                reserved_cost_usd=reserved,
            )
        if request.take in self.fail_takes:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                self.stop_requested = True
            return ReadyTake(
                take=request.take,
                speaker=request.speaker,
                line=request.line,
                clip_path=None,
                frame_path=None,
                frame_url=None,
                anchor=request.anchor,
                request_id=f"req-{request.take}",
                status="failed",
                reserved_cost_usd=reserved,
            )
        self._consecutive_failures = 0
        clip = self.work_dir / f"{request.take:03d}.mp4"
        clip.write_bytes(b"clip")
        return ReadyTake(
            take=request.take,
            speaker=request.speaker,
            line=request.line,
            clip_path=clip,
            frame_path=self.work_dir / f"{request.take:03d}.png",
            frame_url=FRAME_URL.format(take=request.take),
            anchor=request.anchor,
            request_id=f"req-{request.take}",
            status="ready",
            reserved_cost_usd=reserved,
        )


def _meter(tmp_path: Path, *, cap: Decimal = Decimal("12.00")) -> SpendMeter:
    return SpendMeter(
        cap_usd=cap,
        rate_768p_usd_per_s=RATE,
        duration_s=5,
        mode="live",
        ledger=SpendLedger(tmp_path / "reservations.jsonl"),
    )


def _harness(
    tmp_path: Path,
    *,
    writer: Any | None = None,
    cap: Decimal = Decimal("12.00"),
    target_duration_s: float = 90.0,
    delay_s: float = 4.0,
    forced_late_takes: tuple[int, ...] = (),
    fail_takes: tuple[int, ...] = (),
    drop_422_takes: tuple[int, ...] = (),
    reanchor_every: int = 60,
) -> tuple[LiveHarness, LiveWriter | Any, FakePerformer, FakePlayer]:
    clock = FakeClock()
    player = FakePlayer()
    player.set_clip_duration(CLIP_DURATION_S)
    live_writer = writer if writer is not None else LiveWriter()
    meter = _meter(tmp_path, cap=cap)
    performer = FakePerformer(
        clock,
        meter,
        tmp_path,
        delay_s=delay_s,
        forced_late_takes=forced_late_takes,
        fail_takes=fail_takes,
        drop_422_takes=drop_422_takes,
    )
    harness = LiveHarness(
        clock=clock,
        player=player,
        pipeline=WriterPipeline(live_writer),
        performer=performer,
        meter=meter,
        baseline=_baseline(tmp_path, reanchor_every=reanchor_every),
        package=_package(),
        target_duration_s=target_duration_s,
    )
    return harness, live_writer, performer, player


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_remaining_submit_slots_and_writer_phase_formula():
    assert remaining_submit_slots(90, 0) == 17
    assert remaining_submit_slots(10, 0) == 1
    assert remaining_submit_slots(10, 4) == 0
    assert remaining_submit_slots(90, 90) == 0
    assert writer_phase(17, False) == "open"
    assert writer_phase(17, True) == "develop"
    assert writer_phase(2, True) == "close"
    assert writer_phase(0, True) == "close"


def test_play_current_while_next_cooks(tmp_path: Path) -> None:
    harness, writer, performer, player = _harness(tmp_path)

    async def run() -> None:
        await harness.run_simulated(until_aired=2)

    _run(run())
    play_take_1 = [
        beat for beat in harness.beats if beat.get("host_source") == "ready:1"
    ]
    assert play_take_1
    take1 = next(row for row in harness.log if row["take"] == 1)
    take2 = next(row for row in harness.log if row["take"] == 2)
    assert take2["t_submit"] is not None
    assert take1["t_on_air"] is not None
    assert take2["t_submit"] <= take1["t_on_air"]
    assert performer.max_inflight >= 2
    assert {req.baseline_id for req in performer.started} == {BASELINE_ID}


def test_alternating_hosts_cook_in_parallel(tmp_path: Path) -> None:
    harness, _, performer, _ = _harness(tmp_path)

    async def run() -> None:
        await harness.run_simulated(until_aired=3)

    _run(run())
    assert performer.max_inflight >= 2
    heroes = [req for req in performer.started if req.anchor == "hero"]
    assert len(heroes) >= 2
    assert {req.speaker for req in heroes[:2]} == {"BOT1", "BOT2"}
    assert all(req.speaker in {"BOT1", "BOT2"} for req in performer.started)


def test_speaker_cut_rebases_to_hero(tmp_path: Path) -> None:
    harness, _, performer, _ = _harness(tmp_path)

    async def run() -> None:
        await harness.run_simulated(until_aired=2)

    _run(run())
    assert performer.started[0].anchor == "hero"
    assert performer.started[0].image_url == "hero"
    assert performer.started[0].speaker == "BOT1"
    assert performer.started[1].speaker == "BOT2"
    assert performer.started[1].anchor == "hero"
    assert performer.started[1].image_url == "hero"
    for beat in harness.beats:
        if beat["submit"]:
            assert set(beat["submit"]) == {"take", "line", "speaker"}


def test_same_speaker_chains_the_exact_frame_url(tmp_path: Path) -> None:
    harness, _, performer, _ = _harness(tmp_path, writer=ContinuingWriter())

    async def run() -> None:
        await harness.run_simulated(until_aired=2)

    _run(run())
    assert performer.started[0].anchor == "hero"
    assert performer.started[0].image_url == "hero"
    assert performer.started[0].speaker == "BOT1"
    assert performer.started[1].speaker == "BOT1"
    assert performer.started[1].anchor == "chain"
    assert performer.started[1].image_url == FRAME_URL.format(take=1)
    take1 = next(row for row in harness.log if row["take"] == 1)
    take2 = next(row for row in harness.log if row["take"] == 2)
    assert take2["t_submit"] >= take1["t_ready"]
    assert take2["t_submit"] <= take1["t_on_air"]


def test_late_take_uses_card_or_hold(tmp_path: Path) -> None:
    harness, _, performer, _ = _harness(
        tmp_path, writer=ContinuingWriter(), forced_late_takes=(2,)
    )

    async def run() -> None:
        await harness.run_simulated(until_aired=2)

    _run(run())
    assert any(beat["layout"] in {"card_full", "hold", "split"} for beat in harness.beats)
    take2 = next(row for row in harness.log if row["take"] == 2)
    assert take2["status"] == "late"
    assert take2["t_on_air"] is not None
    assert take2["anchor"] == "chain"


def test_cap_prevents_submit(tmp_path: Path) -> None:
    harness, _, performer, _ = _harness(tmp_path, cap=NEXT_COST)

    async def run() -> None:
        await harness.run_simulated(until_aired=1, max_t=20)

    _run(run())
    assert len(performer.started) == 1
    assert harness.spend_policy == "stop"
    assert all(beat["submit"] is None or beat["submit"]["take"] == 1 for beat in harness.beats)


def test_422_invalidates_dependent_thoughts_and_reissues(tmp_path: Path) -> None:
    harness, writer, performer, _ = _harness(tmp_path, drop_422_takes=(1,))

    async def run() -> None:
        await harness.run_simulated(until_aired=1)

    _run(run())
    assert any(event["kind"] == "dropped_422" for event in harness.events)
    assert any(call["reissue"] == "shorter, blander" for call in writer.calls)
    assert performer.started[0].take == 1
    assert any(req.take > 1 for req in performer.started)
    aired = [row for row in harness.log if row.get("t_on_air") is not None]
    assert aired
    assert aired[0]["take"] != 1


def test_writer_down_stops_safely(tmp_path: Path) -> None:
    harness, _, performer, _ = _harness(tmp_path, writer=FailingWriter())

    async def run() -> None:
        await harness.run_simulated(max_t=5)

    _run(run())
    assert harness.stop_reason == "writer down"
    assert harness.spend_policy == "stop"
    assert performer.started == []
    assert harness.done is True


def test_performer_down_stops_safely(tmp_path: Path) -> None:
    harness, _, performer, _ = _harness(tmp_path, delay_s=0.0, fail_takes=(1, 2, 3))

    async def run() -> None:
        await harness.run_simulated(max_t=5)

    _run(run())
    assert performer.stop_requested is True
    assert harness.stop_reason == "performer down"
    assert harness.spend_policy == "stop"
    assert all(row.get("t_on_air") is None for row in harness.log)


def test_no_new_submit_after_closing_boundary(tmp_path: Path) -> None:
    harness, _, performer, _ = _harness(tmp_path, target_duration_s=10.0)

    async def run() -> None:
        await harness.run_simulated(until_aired=1, max_t=20)

    _run(run())
    assert len(performer.started) == 1
    assert harness.remaining_slots() == 0
    assert harness.spend_policy == "stop"
    assert all(
        beat["submit"] is None or beat["submit"]["take"] == 1 for beat in harness.beats
    )


def test_baseline_id_never_changes(tmp_path: Path) -> None:
    harness, _, performer, _ = _harness(tmp_path)

    async def run() -> None:
        await harness.run_simulated(until_aired=3)

    _run(run())
    assert [req.baseline_id for req in performer.started] == [BASELINE_ID] * len(
        performer.started
    )
    assert harness.baseline_id == BASELINE_ID


def test_bot_ids_stay_until_set_speaking(tmp_path: Path) -> None:
    harness, writer, performer, player = _harness(tmp_path)

    async def run() -> None:
        await harness.run_simulated(until_aired=2)

    _run(run())
    assert {call["next_speaker"] for call in writer.calls} <= {"BOT1", "BOT2"}
    assert {req.speaker for req in performer.started} <= {"BOT1", "BOT2"}
    assert {row["speaker"] for row in harness.log if row["speaker"]} <= {"BOT1", "BOT2"}
    speaking = [call[1] for call in player.calls if call[0] == "set_speaking"]
    assert "host_a" in speaking
    assert "host_b" in speaking
    assert all(host in {None, "host_a", "host_b"} for host in speaking)
    assert "host_a" not in {req.speaker for req in performer.started}


def test_writer_phase_is_derived_not_raw_timing(tmp_path: Path) -> None:
    harness, writer, _, _ = _harness(tmp_path)

    async def run() -> None:
        await harness.run_simulated(until_aired=2)

    _run(run())
    phases = [call["segment_phase"] for call in writer.calls]
    assert phases
    assert phases[0] == "open"
    assert "develop" in phases
    assert all(phase in {"open", "develop", "close"} for phase in phases)


def test_simulated_path_does_not_sleep() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "runtime_flight" / "harness_live.py"
    ).read_text(encoding="utf-8")
    assert "time.sleep" not in source
    assert "asyncio.sleep(0)" in source
    assert "asyncio.sleep(POLL" not in source
    assert "asyncio.sleep(self" not in source


def test_harness_does_not_import_root_scaffold() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "harness_live.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN_ROOT_MODULES)
    assert "fal_client" not in imported
    assert "run_live" not in imported
