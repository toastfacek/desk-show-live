"""Realtime live-flight state machine. Tests drive a fake clock; Director stays pure."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol

from obs_harness.director import decide
from runtime_flight.anchor import planned_anchor
from runtime_flight.baseline import BaselineContext
from runtime_flight.models import SegmentPackage, Thought
from runtime_flight.performer_fal import ReadyTake, TakeRequest
from runtime_flight.topic_map import discussion_phase, resolve_topic_map
from runtime_flight.clip import max_thought_chars
from runtime_flight.prompt import assemble_prompt
from runtime_flight.spend import SpendMeter
from runtime_flight.writer_pipeline import WriterPipeline, WriterPipelineStopped

CLIP_DURATION_S = 5.0
POLL_INTERVAL_S = 0.2
STREAM_POLL_INTERVAL_S = 1.0
HERO_IMAGE_PLACEHOLDER = "hero"
HOST_LAYOUTS = ("wide", "split", "solo_l", "solo_r")
DEFAULT_LAYOUT_PLAN = ("split",)
DEFAULT_MAX_INFLIGHT = 4


def remaining_submit_slots(
    target_duration_s: float,
    elapsed_s: float,
    clip_duration_s: float = CLIP_DURATION_S,
) -> int:
    return max(0, math.floor((target_duration_s - elapsed_s) / clip_duration_s) - 1)


def writer_phase(
    remaining: int, opener_done: bool
) -> Literal["open", "develop", "close"]:
    if remaining <= 2:
        return "close"
    if opener_done:
        return "develop"
    return "open"


class Clock(Protocol):
    def monotonic(self) -> float: ...


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._t = float(start)

    def monotonic(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        if dt < 0:
            raise ValueError("clock cannot go backwards")
        self._t += dt

    def advance_to(self, t: float) -> None:
        if t > self._t:
            self._t = t


class WallClock:
    def monotonic(self) -> float:
        return time.monotonic()


SleepFn = Callable[[float], Awaitable[None]]


class Performer(Protocol):
    def start(self, request: TakeRequest) -> asyncio.Task[ReadyTake]: ...

    @property
    def stop_requested(self) -> bool: ...

    @property
    def active_requests(self) -> int: ...


class LiveHarness:
    def __init__(
        self,
        *,
        clock: Clock,
        player: Any,
        pipeline: WriterPipeline,
        performer: Performer,
        meter: SpendMeter,
        baseline: BaselineContext,
        package: SegmentPackage,
        target_duration_s: float = 90.0,
        clip_duration_s: float = CLIP_DURATION_S,
        layout_plan: tuple[str, ...] | None = None,
        overlay: Any | None = None,
        obs_session: Any | None = None,
        max_attempts: int | None = None,
        max_inflight: int = DEFAULT_MAX_INFLIGHT,
        sleep: SleepFn | None = None,
    ) -> None:
        self.clock = clock
        self.player = player
        self.pipeline = pipeline
        self.performer = performer
        self.meter = meter
        self.baseline = baseline
        self.package = package
        self.target_duration_s = target_duration_s
        self.clip_duration_s = clip_duration_s
        self.layout_plan = list(layout_plan or DEFAULT_LAYOUT_PLAN)
        self.overlay = overlay
        self.obs_session = obs_session
        self.max_attempts = max_attempts
        if max_inflight < 1:
            raise ValueError("max_inflight must be at least 1")
        self.max_inflight = max_inflight
        self._sleep = sleep
        self.started_at = clock.monotonic()
        self.baseline_id = baseline.baseline_id
        self.spend_policy = "normal"
        self._stop_submits = False
        self._opener_done = False
        self._programme_hold = False
        self._last_stream_poll_t: float | None = None
        self.stop_reason: str | None = None
        self.recording_path: str | None = None
        self.after_step = None
        self.flags = {"hold": False, "panic": False}
        self.ready: list[ReadyTake] = []
        self.cooking: list[dict[str, Any]] = []
        self.on_air: dict[str, Any] | None = None
        self.next_take = 1
        self.layout_i = 0
        self.done = False
        self.beats: list[dict] = []
        self.events: list[dict] = []
        self.requests: list[TakeRequest] = []
        self.log: list[dict] = []
        self._thought_by_take: dict[int, Thought] = {}
        self._completed: dict[int, ReadyTake] = {}

    @property
    def t(self) -> float:
        return self.clock.monotonic()

    @property
    def elapsed_s(self) -> float:
        return self.t - self.started_at

    @property
    def aired_count(self) -> int:
        return sum(1 for row in self.log if row.get("t_on_air") is not None)

    def remaining_slots(self) -> int:
        budget = remaining_submit_slots(
            self.target_duration_s, 0.0, clip_duration_s=self.clip_duration_s
        )
        return max(0, budget - len(self.requests))

    def current_writer_phase(self) -> Literal["open", "develop", "close"]:
        topic_map = resolve_topic_map(self.package)
        discussion = discussion_phase(self.pipeline.coverage, topic_map)
        clock = writer_phase(self.remaining_slots(), self._opener_done)
        if discussion == "close" or clock == "close":
            return "close"
        if discussion == "open" and not self._opener_done:
            return "open"
        if not self._opener_done and clock == "open":
            return "open"
        return "develop"

    def snapshot(self) -> dict:
        thought = self.pipeline.peek_ready()
        jobs = [
            {"take": job["take"], "submitted_at": job["submitted_at"]}
            for job in self.cooking
        ]
        return {
            "t": self.t,
            "on_air": self.on_air,
            "ready": [
                {
                    "take": item.take,
                    "path": str(item.clip_path) if item.clip_path is not None else "",
                    "speaker": item.speaker,
                    "line": item.line,
                    "duration_s": self.clip_duration_s,
                }
                for item in self._airable_now()
            ],
            "cooking": jobs or None,
            "max_inflight": self.max_inflight,
            "chain_ready": self._next_anchor_available(thought),
            "next_line": (
                {"speaker": thought.speaker, "text": thought.text}
                if thought is not None
                else None
            ),
            "flags": dict(self.flags),
            "next_take": self.next_take,
            "layout": getattr(self.player, "layout", None)
            or (self.on_air or {}).get("layout"),
            "layout_i": self.layout_i,
            "segment": {
                "layout_plan": self.layout_plan,
                "center": self._center(),
                "chyron": self.package.chyron,
                "spend_policy": self.spend_policy,
            },
        }

    async def step(self) -> None:
        self.player.t = self.t
        self._poll_stream_status()
        self._observe_player()
        if self.elapsed_s + 1e-9 >= self.target_duration_s:
            self._enter_programme_hold()
        await self._collect_cooking()
        await self._ensure_writer_ahead()
        self._update_policies()
        if self.performer.stop_requested and not self._stop_submits:
            self._stop_safely("performer down")
        if self._should_cut():
            beat = decide(self.snapshot())
            self.beats.append(beat)
            await self._execute(beat)
        await self._fill_buffer()
        if self.after_step is not None:
            self.after_step()

    async def run_simulated(
        self,
        *,
        until_aired: int | None = None,
        max_t: float = 90.0,
    ) -> None:
        await self.step()
        while self.t < max_t and not self.done:
            self.clock.advance_to(self._next_event_t())
            await self.step()
            if until_aired is not None and self.aired_count >= until_aired:
                return

    async def run_wall(
        self,
        *,
        until_aired: int | None = None,
        max_t: float = 90.0,
        sleep: SleepFn | None = None,
    ) -> None:
        sleeper = sleep or self._sleep or asyncio.sleep
        await self.step()
        deadline = self.started_at + max_t
        while self.t < deadline and not self.done:
            target = min(self._next_event_t(), deadline)
            delay = target - self.t
            if delay > 0:
                await sleeper(delay)
            await self.step()
            if until_aired is not None and self.aired_count >= until_aired:
                return

    async def run_with_obs(self, *, max_t: float | None = None) -> None:
        if self.obs_session is None:
            raise RuntimeError("OBS session required")
        self.obs_session.start_recording()
        try:
            limit = max_t if max_t is not None else self.target_duration_s
            if hasattr(self.clock, "advance_to"):
                await self.run_simulated(max_t=limit)
            else:
                await self.run_wall(max_t=limit)
            if self.stop_reason != "obs streaming":
                await self._post_roll_recording()
        finally:
            self.recording_path = self.obs_session.stop_recording()
            self.events.append(
                {"t": self.t, "kind": "recording_stopped", "path": self.recording_path}
            )

    def _next_event_t(self) -> float:
        now = self.t
        next_t = now + POLL_INTERVAL_S
        for job in self.cooking:
            ready_at = job.get("ready_at")
            if ready_at is not None:
                next_t = min(next_t, float(ready_at))
        if self.on_air is not None:
            ends = self.on_air.get("ends_at")
            if ends is not None:
                next_t = min(next_t, float(ends))
        if self.obs_session is not None:
            last = self._last_stream_poll_t
            next_poll = (last if last is not None else now) + STREAM_POLL_INTERVAL_S
            next_t = min(next_t, next_poll)
        if next_t <= now:
            next_t = now + POLL_INTERVAL_S
        return next_t

    def _mark_unhealthy(self) -> None:
        if self.overlay is not None:
            self.overlay.mark_unhealthy()
        self.events.append({"t": self.t, "kind": "watchdog_unhealthy"})

    def _push_overlay_layout(self, layout: str) -> None:
        setter = getattr(self.overlay, "set_layout", None)
        if setter is None:
            return
        try:
            setter(layout)
        except Exception:
            return

    def _obs_command(self, method: str, *args: Any, **kwargs: Any) -> bool:
        try:
            getattr(self.player, method)(*args, **kwargs)
            return True
        except Exception:
            self._mark_unhealthy()
            self._stop_safely("obs disconnect")
            return False

    def _observe_player(self) -> None:
        getter = getattr(self.player, "get_program_state", None)
        if getter is None:
            if getattr(self.player, "connected", True) is False:
                self._mark_unhealthy()
                self._stop_safely("obs disconnect")
            return
        try:
            state = getter()
        except Exception:
            self._mark_unhealthy()
            self._stop_safely("obs disconnect")
            return
        if state.get("connected") is False or state.get("media_ok") is False:
            self._mark_unhealthy()
            self._stop_safely("obs disconnect")

    def _poll_stream_status(self) -> None:
        if self.obs_session is None:
            return
        last = self._last_stream_poll_t
        if last is not None and self.t + 1e-9 < last + STREAM_POLL_INTERVAL_S:
            return
        try:
            active = bool(self.obs_session.is_streaming())
        except Exception:
            self._mark_unhealthy()
            self._stop_safely("obs disconnect")
            return
        self._last_stream_poll_t = self.t
        self.events.append({"t": self.t, "kind": "stream_status", "active": active})
        if active:
            self._handle_stream_active()

    def _handle_stream_active(self) -> None:
        self._stop_submits = True
        self.spend_policy = "stop"
        self.flags["hold"] = True
        self.stop_reason = "obs streaming"
        self.on_air = {"kind": "hold", "take": None, "ends_at": None}
        self.done = True
        try:
            self.player.set_layout("hold")
        except Exception:
            self._mark_unhealthy()
        self._push_overlay_layout("hold")
        self.events.append({"t": self.t, "kind": "stream_active_abort"})

    def _enter_programme_hold(self) -> None:
        if self._programme_hold:
            return
        self._programme_hold = True
        self._stop_submits = True
        self.spend_policy = "stop"
        self.flags["hold"] = True
        self.events.append({"t": self.t, "kind": "programme_hold"})
        self._obs_command("set_layout", "hold")
        self._push_overlay_layout("hold")

    async def _post_roll_recording(self) -> None:
        self._enter_programme_hold()
        if self.obs_session is None:
            return
        deadline = self.t + max(30.0, self.target_duration_s)
        sleeper = self._sleep or asyncio.sleep
        while self.obs_session.recording_duration_s() + 1e-9 < self.target_duration_s:
            if self.t + 1e-9 >= deadline:
                raise RuntimeError("post-roll exceeded recording duration target")
            if hasattr(self.clock, "advance"):
                self.clock.advance(POLL_INTERVAL_S)
            else:
                await sleeper(POLL_INTERVAL_S)
            self.player.t = self.t
            self.events.append(
                {
                    "t": self.t,
                    "kind": "post_roll",
                    "recording_s": self.obs_session.recording_duration_s(),
                }
            )

    def _center(self) -> dict[str, str]:
        return {
            "kind": "card",
            "id": self.package.item_id,
            "author": self.package.center.author,
            "text": self.package.center.text,
        }

    def _can_reserve(self) -> bool:
        if self._stop_submits:
            return False
        reserved = len(self.meter.ledger.records())
        if self.max_attempts is not None and reserved >= self.max_attempts:
            return False
        if self.meter.mode == "smoke" and reserved >= 2:
            return False
        return self.meter.total + self.meter.next_cost <= self.meter.cap_usd

    def _update_policies(self) -> None:
        if self.remaining_slots() == 0 or not self._can_reserve():
            self.spend_policy = "stop"
            self._stop_submits = True
        elif not self._stop_submits:
            self.spend_policy = "normal"

    async def _ensure_writer_ahead(self) -> None:
        if self._stop_submits or self.pipeline.stopped:
            return
        if self.pipeline.ready.qsize() >= 2:
            return
        if self.remaining_slots() == 0:
            return
        if self.pipeline.coverage.map_complete:
            return
        try:
            await self.pipeline.fill(
                self.package,
                segment_phase=self.current_writer_phase(),
            )
            self._opener_done = True
        except WriterPipelineStopped:
            self._stop_safely("writer down")
        except Exception:
            if self.pipeline.stopped:
                self._stop_safely("writer down")

    async def _fill_buffer(self) -> None:
        while self._can_queue_another():
            thought = self.pipeline.peek_ready()
            if thought is None:
                await self._ensure_writer_ahead()
                thought = self.pipeline.peek_ready()
            if thought is None:
                return
            if not self._next_anchor_available(thought):
                return
            await self._submit(
                {
                    "take": self.next_take,
                    "line": thought.text,
                    "speaker": thought.speaker,
                }
            )

    def _can_queue_another(self) -> bool:
        if self._stop_submits or self.spend_policy != "normal":
            return False
        if len(self.cooking) >= self.max_inflight:
            return False
        if self.remaining_slots() == 0 or not self._can_reserve():
            return False
        thought = self.pipeline.peek_ready()
        if thought is None:
            return not self.pipeline.stopped
        return self._next_anchor_available(thought)

    def _playable_ready(self) -> list[ReadyTake]:
        items = sorted(self.ready, key=lambda item: item.take)
        if not items:
            return []
        first = items[0]
        if any(job["take"] < first.take for job in self.cooking):
            return []
        return items

    def _successor_ready(self, take: int) -> bool:
        return any(item.take == take + 1 for item in self.ready)

    def _must_air_without_successor(self, take: int) -> bool:
        if self._stop_submits or self.remaining_slots() == 0 or not self._can_reserve():
            return True
        if self.pipeline.stopped and self.pipeline.peek_ready() is None:
            return True
        return False

    def _airable_now(self) -> list[ReadyTake]:
        """Clips the director may put on air this beat.

        Play order still waits for a lower take. From standby, hold the first
        ready take until its successor is also ready so the on-air clip has a
        hard-cut partner waiting. After a host clip ends, air the successor
        immediately even if the one after that is still cooking.
        """
        playable = self._playable_ready()
        if not playable:
            return []
        first = playable[0]
        on_air = self.on_air or {}
        if on_air.get("kind") == "host":
            return playable
        if self._successor_ready(first.take) or self._must_air_without_successor(
            first.take
        ):
            return playable
        return []

    def _next_anchor_available(self, thought: Thought | None) -> bool:
        if thought is None:
            return False
        _anchor, _url, available = self._plan_anchor(self.next_take, thought.speaker)
        return available

    def _plan_anchor(
        self, take: int, speaker: str
    ) -> tuple[Literal["hero", "chain"], str, bool]:
        previous_speaker, previous_frame_url, previous_complete = self._previous_picture(
            take
        )
        return planned_anchor(
            take=take,
            speaker=speaker,
            previous_speaker=previous_speaker,
            previous_frame_url=previous_frame_url,
            previous_complete=previous_complete,
            reanchor_every=self.baseline.reanchor_every,
            hero_url=HERO_IMAGE_PLACEHOLDER,
        )

    def _previous_picture(
        self, take: int
    ) -> tuple[str | None, str | None, bool]:
        completed = self._completed.get(take - 1)
        if completed is not None:
            return completed.speaker, completed.frame_url, True
        submitted = next((req for req in self.requests if req.take == take - 1), None)
        if submitted is not None:
            return submitted.speaker, None, False
        return None, None, False

    async def _collect_cooking(self) -> None:
        if not self.cooking:
            return
        await asyncio.sleep(0)
        still: list[dict[str, Any]] = []
        finished: list[dict[str, Any]] = []
        host_ended = False
        if self.on_air and self.on_air.get("kind") == "host":
            ends = self.on_air.get("ends_at")
            host_ended = ends is not None and self.t + 1e-9 >= ends
        for job in self.cooking:
            task: asyncio.Task[ReadyTake] = job["task"]
            if not task.done():
                if host_ended:
                    job["missed_cut"] = True
                still.append(job)
                continue
            finished.append(job)
        self.cooking = still
        for job in finished:
            ready = job["task"].result()
            take = job["take"]
            missed = bool(job.get("missed_cut"))
            if ready.status == "dropped_422":
                await self._handle_422(ready)
                continue
            if ready.status != "ready":
                self.events.append(
                    {
                        "t": self.t,
                        "kind": "performer_failed",
                        "take": take,
                        "status": ready.status,
                    }
                )
                if self.performer.stop_requested:
                    self._stop_safely("performer down")
                continue
            self._completed[take] = ready
            self.ready.append(ready)
            row = self._row(take)
            row["t_ready"] = self.t
            row["status"] = "late" if missed else "ready"
            row["clip"] = str(ready.clip_path) if ready.clip_path else None
            row["frame_url"] = ready.frame_url
            row["anchor"] = ready.anchor
            row["request_id"] = ready.request_id
            self.events.append({"t": self.t, "kind": "ready", "take": take})

    async def _handle_422(self, ready: ReadyTake) -> None:
        thought = self._thought_by_take.get(ready.take)
        self.events.append({"t": self.t, "kind": "dropped_422", "take": ready.take})
        row = self._row(ready.take)
        row["status"] = "dropped_422"
        if thought is None:
            return
        try:
            await self.pipeline.drop_take(
                thought,
                self.package,
                segment_phase=self.current_writer_phase(),
            )
        except WriterPipelineStopped:
            self._stop_safely("writer down")

    def _should_cut(self) -> bool:
        if self.done:
            return False
        if self.flags.get("panic"):
            if self.on_air and self.on_air.get("kind") == "host":
                ends = self.on_air.get("ends_at")
                if ends is not None and self.t + 1e-9 < ends:
                    return False
            return True
        if self.on_air is None:
            return True
        ends = self.on_air.get("ends_at")
        if ends is not None and self.t + 1e-9 >= ends:
            return True
        if self.on_air.get("kind") != "host":
            return bool(self._airable_now())
        return False

    async def _execute(self, beat: dict) -> None:
        self.player.t = self.t
        if not self._obs_command("set_layout", beat["layout"]):
            return
        self._push_overlay_layout(beat["layout"])
        if not self._obs_command("set_headline", beat.get("chyron") or ""):
            return
        center = beat.get("center") or {"kind": "none"}
        if not self._obs_command("set_center", center.get("kind") or "none", center):
            return
        if not self._obs_command(
            "set_speaking", self._mapped_speaking(beat.get("speaking"))
        ):
            return
        if not self._obs_command("duck_music", -6.0 if beat.get("speaking") else 0.0):
            return

        if beat.get("host_source"):
            take = int(str(beat["host_source"]).split(":")[1])
            clip = next(item for item in self.ready if item.take == take)
            self.ready = [item for item in self.ready if item.take != take]
            path = (
                str(clip.clip_path.resolve())
                if clip.clip_path is not None
                else ""
            )
            if not self._obs_command("play_clip", path):
                return
            self.on_air = {
                "kind": "host",
                "take": take,
                "speaker": clip.speaker,
                "ends_at": self.t + self.clip_duration_s,
                "path": path,
                "layout": beat["layout"],
            }
            self.layout_i += 1
            thought = self._thought_by_take.get(take)
            if thought is not None:
                self.pipeline.mark_aired(thought)
            row = self._row(take)
            row["t_on_air"] = self.t
            row["layout_on_air"] = beat["layout"]
            row["line"] = clip.line
            row["speaker"] = clip.speaker
            if row["status"] not in ("late",):
                row["status"] = "ready"
            self.events.append(
                {
                    "t": self.t,
                    "kind": "on_air",
                    "take": take,
                    "layout": beat["layout"],
                    "speaker": clip.speaker,
                }
            )
        elif beat.get("submit"):
            self.on_air = {
                "kind": "card" if beat["layout"] == "card_full" else "wait",
                "take": None,
                "ends_at": None,
                "layout": beat["layout"],
            }
        else:
            if beat.get("why") == "panic" or (
                beat["layout"] == "hold"
                and not self.ready
                and not self.cooking
                and self._stop_submits
            ):
                self.done = True
            if beat["layout"] in HOST_LAYOUTS:
                kind = "wait"
            elif beat["layout"] == "hold":
                kind = "hold"
            else:
                kind = "card"
            self.on_air = {
                "kind": kind,
                "take": None,
                "ends_at": None,
                "layout": beat["layout"],
            }

        if beat.get("submit"):
            await self._submit(beat["submit"])

    async def _submit(self, submit: dict) -> None:
        if len(self.cooking) >= self.max_inflight:
            raise RuntimeError("performer inflight cap")
        if submit.get("take") != self.next_take:
            raise RuntimeError("director take drifted from harness next_take")
        thought = self.pipeline.ready.get_nowait()
        if thought.text != submit["line"] or thought.speaker != submit["speaker"]:
            raise RuntimeError("director submit does not match Writer thought")
        if thought.speaker not in {"BOT1", "BOT2"}:
            raise RuntimeError("submit speaker must stay BOT1/BOT2")
        request = self._enrich(submit)
        if request.baseline_id != self.baseline_id:
            raise RuntimeError("baseline ID must not change")
        delay = 0.0
        delay_for = getattr(self.performer, "delay_for", None)
        if callable(delay_for):
            delay = float(delay_for(request.take))
        task = self.performer.start(request)
        self.requests.append(request)
        self._thought_by_take[request.take] = thought
        self.cooking.append(
            {
                "take": request.take,
                "task": task,
                "submitted_at": self.t,
                "ready_at": self.t + delay,
                "missed_cut": False,
                "request": request,
            }
        )
        row = self._row(request.take)
        row["line"] = request.line
        row["speaker"] = request.speaker
        row["t_submit"] = self.t
        row["anchor"] = request.anchor
        row["image_url"] = request.image_url
        row["prompt"] = request.prompt
        self.next_take = request.take + 1
        self.events.append(
            {
                "t": self.t,
                "kind": "submit",
                "take": request.take,
                "anchor": request.anchor,
                "speaker": request.speaker,
            }
        )

    def _enrich(self, submit: dict) -> TakeRequest:
        speaker: Literal["BOT1", "BOT2"] = submit["speaker"]
        line = submit["line"]
        take = int(submit["take"])
        anchor, image_url, available = self._plan_anchor(take, speaker)
        if not available:
            raise RuntimeError("chain take submitted before the previous frame existed")
        return TakeRequest(
            take=take,
            speaker=speaker,
            line=line,
            prompt=assemble_prompt(
                self.baseline,
                speaker,
                line,
                max_line_chars=max_thought_chars(int(self.clip_duration_s)),
            ),
            anchor=anchor,
            image_url=image_url,
            baseline_id=self.baseline_id,
        )

    def _mapped_speaking(self, speaker: str | None) -> str | None:
        if speaker is None:
            return None
        if speaker not in {"BOT1", "BOT2"}:
            raise RuntimeError("speaking must stay BOT1/BOT2 until host_map")
        return str(self.baseline.host_map[speaker])

    def _stop_safely(self, why: str) -> None:
        self._stop_submits = True
        self.spend_policy = "stop"
        self.flags["hold"] = True
        self.stop_reason = why
        self.events.append({"t": self.t, "kind": "stop", "why": why})
        if self.on_air is None or self.on_air.get("kind") != "host":
            self.done = True

    def _row(self, take: int) -> dict:
        for row in self.log:
            if row["take"] == take:
                return row
        row = {
            "take": take,
            "line": None,
            "speaker": None,
            "clip": None,
            "status": "ready",
            "layout_on_air": None,
            "t_submit": None,
            "t_ready": None,
            "t_on_air": None,
            "anchor": None,
            "image_url": None,
            "frame_url": None,
            "prompt": None,
            "request_id": None,
        }
        self.log.append(row)
        return row
