"""Sequential look-ahead: one Writer request, two completed thoughts queued."""

from __future__ import annotations

import asyncio
from typing import Literal

from runtime_flight.clip import speech_target_s
from runtime_flight.models import CoverageState, HostVoice, SegmentPackage, Thought
from runtime_flight.topic_map import advance_coverage, resolve_topic_map
from runtime_flight.writer import Writer, WriterError

SEGMENT_PHASES = frozenset({"open", "develop", "close"})
REISSUE_SHORTER_BLANDER: Literal["shorter, blander"] = "shorter, blander"


class WriterPipelineStopped(Exception):
    """Raised when three consecutive write failures stop the pipeline."""


class WriterPipeline:
    def __init__(
        self,
        writer: Writer,
        voices: tuple[HostVoice, ...] | None = None,
        clip_duration_s: int = 5,
    ) -> None:
        self._writer = writer
        self._voices = voices
        self.clip_duration_s = clip_duration_s
        self._ready: asyncio.Queue[Thought] = asyncio.Queue(maxsize=2)
        self._planned: list[Thought] = []
        self._aired: list[Thought] = []
        self._lock = asyncio.Lock()
        self._consecutive_failures = 0
        self._stopped = False
        self._next_speaker: Literal["BOT1", "BOT2"] = "BOT1"
        self._thought_open = False
        self._opener_speaker: Literal["BOT1", "BOT2"] = "BOT1"
        self._coverage = CoverageState.initial()
        self._pending: list[Thought] = []

    @property
    def ready(self) -> asyncio.Queue[Thought]:
        return self._ready

    @property
    def planned_transcript(self) -> tuple[Thought, ...]:
        return tuple(self._planned)

    @property
    def aired_transcript(self) -> tuple[Thought, ...]:
        return tuple(self._aired)

    @property
    def stopped(self) -> bool:
        return self._stopped

    @property
    def coverage(self) -> CoverageState:
        return self._coverage

    async def fill(
        self,
        package: SegmentPackage,
        *,
        segment_phase: Literal["open", "develop", "close"],
        next_speaker: Literal["BOT1", "BOT2"] | None = None,
        thought_open: bool | None = None,
        reissue: Literal["shorter, blander"] | None = None,
    ) -> None:
        if segment_phase not in SEGMENT_PHASES:
            raise WriterError("segment_phase must be open, develop, or close")
        async with self._lock:
            if self._stopped:
                raise WriterPipelineStopped("three consecutive write failures")
            if next_speaker is not None:
                self._next_speaker = next_speaker
                self._opener_speaker = next_speaker
            if thought_open is not None:
                self._thought_open = thought_open
            await self._fill_unlocked(package, segment_phase, reissue)

    def peek_ready(self) -> Thought | None:
        if self._ready.empty():
            return None
        return self._ready._queue[0]

    async def pop_ready(self) -> Thought:
        return await self._ready.get()

    def mark_aired(self, thought: Thought) -> None:
        if thought not in self._aired:
            self._aired.append(thought)

    async def drop_take(
        self,
        thought: Thought,
        package: SegmentPackage,
        *,
        segment_phase: Literal["open", "develop", "close"],
    ) -> None:
        if segment_phase not in SEGMENT_PHASES:
            raise WriterError("segment_phase must be open, develop, or close")
        if self._stopped:
            raise WriterPipelineStopped("three consecutive write failures")
        async with self._lock:
            self._aired = [item for item in self._aired if item != thought]
            self._planned = list(self._aired)
            self._pending = []
            self._drain_ready()
            self._restore_speaker_from_aired()
            await self._fill_unlocked(package, segment_phase, REISSUE_SHORTER_BLANDER)

    async def _fill_unlocked(
        self,
        package: SegmentPackage,
        segment_phase: Literal["open", "develop", "close"],
        reissue: Literal["shorter, blander"] | None,
    ) -> None:
        self._sync_coverage(package)
        while self._ready.qsize() < 2:
            if self._stopped:
                raise WriterPipelineStopped("three consecutive write failures")
            if self._coverage.map_complete:
                break
            thought = await self._next_thought(package, segment_phase, reissue)
            self._planned.append(thought)
            self._advance_speaker(thought)
            self._sync_coverage(package)
            self._ready.put_nowait(thought)

    async def _next_thought(
        self,
        package: SegmentPackage,
        segment_phase: Literal["open", "develop", "close"],
        reissue: Literal["shorter, blander"] | None,
    ) -> Thought:
        if self._pending:
            return self._pending.pop(0)
        try:
            write_point = getattr(self._writer, "write_point", None)
            if write_point is not None:
                thoughts = await write_point(
                    package,
                    tuple(self._planned),
                    self._next_speaker,
                    self._thought_open,
                    segment_phase,
                    speech_target_s(self.clip_duration_s),
                    reissue=reissue,
                    voices=self._voices,
                    coverage=self._coverage,
                    clip_duration_s=self.clip_duration_s,
                )
            else:
                thoughts = (
                    await self._writer.write(
                        package,
                        tuple(self._planned),
                        self._next_speaker,
                        self._thought_open,
                        segment_phase,
                        speech_target_s(self.clip_duration_s),
                        reissue=reissue,
                        voices=self._voices,
                        coverage=self._coverage,
                        clip_duration_s=self.clip_duration_s,
                    ),
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                self._stopped = True
                raise WriterPipelineStopped("three consecutive write failures") from error
            raise
        if not thoughts:
            raise WriterError("writer returned no chunks")
        self._consecutive_failures = 0
        first, *rest = thoughts
        self._pending.extend(rest)
        return first

    def _advance_speaker(self, thought: Thought) -> None:
        if thought.thought_open:
            self._next_speaker = thought.speaker
            self._thought_open = True
            return
        self._next_speaker = "BOT2" if thought.speaker == "BOT1" else "BOT1"
        self._thought_open = False

    def _restore_speaker_from_aired(self) -> None:
        if not self._aired:
            self._next_speaker = self._opener_speaker
            self._thought_open = False
            return
        last = self._aired[-1]
        if last.thought_open:
            self._next_speaker = last.speaker
            self._thought_open = True
            return
        self._next_speaker = "BOT2" if last.speaker == "BOT1" else "BOT1"
        self._thought_open = False

    def _drain_ready(self) -> None:
        while True:
            try:
                self._ready.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _sync_coverage(self, package: SegmentPackage) -> None:
        topic_map = resolve_topic_map(package)
        state = CoverageState.initial()
        for thought in self._planned:
            state = advance_coverage(state, thought, topic_map)
        self._coverage = state
