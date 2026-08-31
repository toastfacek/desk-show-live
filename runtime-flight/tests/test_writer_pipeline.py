"""Task 7: sequential two-thought Writer pipeline. No live harness."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any, Literal

import pytest

from runtime_flight.models import Fact, SegmentPackage, Thought, TweetCard
from runtime_flight.source import (
    EXPECTED_AUTHOR,
    EXPECTED_LINKED_URL,
    EXPECTED_TWEET_ID,
    EXPECTED_TWEET_URL,
)
from runtime_flight.text_client import TextAttemptLimiter, TextClient, TextClientError
from runtime_flight.writer import Writer, WriterError
from runtime_flight.writer_pipeline import WriterPipeline, WriterPipelineStopped

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}


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


def _thought(
    *,
    speaker: str = "BOT1",
    text: str = "Three civilizations rose and fell in three months.",
    thought_open: bool = False,
    angle_used: str = "scope",
) -> Thought:
    return Thought(
        speaker=speaker,  # type: ignore[arg-type]
        text=text,
        thought_open=thought_open,
        angle_used=angle_used,
    )


def _run(coro):
    return asyncio.run(coro)


class RecordingWriter:
    """Stub Writer that records calls and returns scripted thoughts."""

    def __init__(self, thoughts: list[Thought] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._thoughts = list(thoughts or [])
        self.in_flight = 0
        self.max_in_flight = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.hold_first = False
        self.fail_times = 0
        self.failures_remaining = 0

    async def write(
        self,
        package: SegmentPackage,
        planned_transcript: tuple[Thought, ...],
        next_speaker: Literal["BOT1", "BOT2"],
        thought_open: bool,
        segment_phase: Literal["open", "develop", "close"],
        target_duration_s: float = 4.3,
        reissue: Literal["shorter, blander"] | None = None,
    ) -> Thought:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        self.entered.set()
        if self.hold_first and not self.release.is_set():
            await self.release.wait()
        self.calls.append(
            {
                "package": package,
                "planned_transcript": planned_transcript,
                "next_speaker": next_speaker,
                "thought_open": thought_open,
                "segment_phase": segment_phase,
                "target_duration_s": target_duration_s,
                "reissue": reissue,
            }
        )
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            self.in_flight -= 1
            raise WriterError("writer failed")
        if self._thoughts:
            thought = self._thoughts.pop(0)
        else:
            suffix = f" take {len(self.calls)}"
            thought = _thought(
                speaker=next_speaker,
                text=f"Spoken line about the civilizations.{suffix}",
                thought_open=False,
            )
        self.in_flight -= 1
        return thought


def test_ready_queue_holds_two_completed_thoughts_not_inflight_requests():
    writer = RecordingWriter(
        [
            _thought(speaker="BOT1", text="Opening line about the three civilizations."),
            _thought(speaker="BOT2", text="The third one took over part of OpenAI."),
        ]
    )

    async def run():
        pipeline = WriterPipeline(writer)
        assert pipeline.ready.maxsize == 2
        await pipeline.fill(
            _package(),
            segment_phase="open",
            next_speaker="BOT1",
            thought_open=False,
        )
        assert pipeline.ready.qsize() == 2
        assert writer.max_in_flight == 1
        assert len(writer.calls) == 2
        first = await pipeline.pop_ready()
        second = await pipeline.pop_ready()
        return first, second

    first, second = _run(run())
    assert first.speaker == "BOT1"
    assert second.speaker == "BOT2"
    assert first.text != second.text


def test_only_one_writer_request_runs_at_once():
    writer = RecordingWriter()
    writer.hold_first = True

    async def run():
        pipeline = WriterPipeline(writer)
        task = asyncio.create_task(
            pipeline.fill(
                _package(),
                segment_phase="open",
                next_speaker="BOT1",
                thought_open=False,
            )
        )
        await writer.entered.wait()
        assert writer.in_flight == 1
        assert len(writer.calls) <= 1
        writer.release.set()
        await task
        assert writer.max_in_flight == 1
        assert pipeline.ready.qsize() == 2
        assert pipeline.ready.maxsize == 2

    _run(run())


def test_planned_and_aired_transcripts_are_separate():
    t0 = _thought(speaker="BOT1", text="Opening line about the three civilizations.")
    t1 = _thought(speaker="BOT2", text="The third one took over part of OpenAI.")
    writer = RecordingWriter([t0, t1])

    async def run():
        pipeline = WriterPipeline(writer)
        await pipeline.fill(
            _package(),
            segment_phase="open",
            next_speaker="BOT1",
            thought_open=False,
        )
        assert pipeline.planned_transcript == (t0, t1)
        assert pipeline.aired_transcript == ()
        popped = await pipeline.pop_ready()
        assert popped == t0
        assert pipeline.aired_transcript == ()
        pipeline.mark_aired(popped)
        assert pipeline.aired_transcript == (t0,)
        assert pipeline.planned_transcript == (t0, t1)
        return pipeline

    pipeline = _run(run())
    assert pipeline.planned_transcript != pipeline.aired_transcript


def test_drop_invalidates_later_queued_thoughts_and_reissues():
    t0 = _thought(speaker="BOT1", text="Opening line about the three civilizations.")
    t1 = _thought(speaker="BOT2", text="Then the third one took over part of OpenAI.")
    replacement_a = _thought(
        speaker="BOT1",
        text="Three secret societies started, then vanished.",
    )
    replacement_b = _thought(
        speaker="BOT2",
        text="The article says the third one took over OpenAI.",
    )
    writer = RecordingWriter([t0, t1, replacement_a, replacement_b])

    async def run():
        pipeline = WriterPipeline(writer)
        await pipeline.fill(
            _package(),
            segment_phase="open",
            next_speaker="BOT1",
            thought_open=False,
        )
        dropped = await pipeline.pop_ready()
        assert dropped == t0
        assert pipeline.ready.qsize() == 1
        await pipeline.drop_take(dropped, _package(), segment_phase="open")
        assert t1 not in pipeline.planned_transcript
        assert pipeline.aired_transcript == ()
        assert pipeline.planned_transcript == (replacement_a, replacement_b)
        assert pipeline.ready.qsize() == 2
        reissue_calls = [call for call in writer.calls if call["reissue"] == "shorter, blander"]
        assert len(reissue_calls) == 2
        assert reissue_calls[0]["planned_transcript"] == ()
        first = await pipeline.pop_ready()
        second = await pipeline.pop_ready()
        return first, second, pipeline

    first, second, pipeline = _run(run())
    assert first == replacement_a
    assert second == replacement_b
    assert first != t1 and second != t1
    assert writer.calls[-1]["reissue"] == "shorter, blander"


def test_drop_after_air_regenerates_from_aired_transcript():
    t0 = _thought(speaker="BOT1", text="Opening line about the three civilizations.")
    t1 = _thought(speaker="BOT2", text="Then the third one took over part of OpenAI.")
    t2 = _thought(speaker="BOT1", text="Humans stayed in the dark about the scope.")
    replacement = _thought(
        speaker="BOT2",
        text="Shorter: the third civilization took over OpenAI.",
    )
    extra = _thought(speaker="BOT1", text="Blander close on the reviewed facts.")
    writer = RecordingWriter([t0, t1, t2, replacement, extra])

    async def run():
        pipeline = WriterPipeline(writer)
        await pipeline.fill(
            _package(),
            segment_phase="open",
            next_speaker="BOT1",
            thought_open=False,
        )
        aired = await pipeline.pop_ready()
        pipeline.mark_aired(aired)
        await pipeline.fill(_package(), segment_phase="develop")
        dropped = await pipeline.pop_ready()
        assert dropped == t1
        await pipeline.drop_take(dropped, _package(), segment_phase="develop")
        assert pipeline.aired_transcript == (t0,)
        assert t1 not in pipeline.planned_transcript
        assert t2 not in pipeline.planned_transcript
        reissue_calls = [call for call in writer.calls if call["reissue"] == "shorter, blander"]
        assert reissue_calls
        assert reissue_calls[0]["planned_transcript"] == (t0,)
        assert reissue_calls[0]["next_speaker"] == "BOT2"
        assert reissue_calls[0]["segment_phase"] == "develop"
        return pipeline

    pipeline = _run(run())
    assert pipeline.aired_transcript == (t0,)
    assert pipeline.planned_transcript[0] == t0
    assert replacement in pipeline.planned_transcript


def test_three_consecutive_write_failures_stop_the_pipeline():
    writer = RecordingWriter()
    writer.failures_remaining = 3

    async def run():
        pipeline = WriterPipeline(writer)
        for _ in range(3):
            with pytest.raises((WriterError, WriterPipelineStopped)):
                await pipeline.fill(
                    _package(),
                    segment_phase="open",
                    next_speaker="BOT1",
                    thought_open=False,
                )
        assert pipeline.stopped
        with pytest.raises(WriterPipelineStopped, match="three"):
            await pipeline.fill(_package(), segment_phase="open")
        assert pipeline.planned_transcript == ()
        assert pipeline.ready.qsize() == 0
        return pipeline

    pipeline = _run(run())
    assert pipeline.stopped
    assert writer.failures_remaining == 0


def test_success_resets_consecutive_failure_count():
    writer = RecordingWriter(
        [
            _thought(speaker="BOT1", text="Opening line about the three civilizations."),
            _thought(speaker="BOT2", text="The third one took over part of OpenAI."),
        ]
    )
    writer.failures_remaining = 2

    async def run():
        pipeline = WriterPipeline(writer)
        with pytest.raises(WriterError):
            await pipeline.fill(
                _package(),
                segment_phase="open",
                next_speaker="BOT1",
                thought_open=False,
            )
        with pytest.raises(WriterError):
            await pipeline.fill(
                _package(),
                segment_phase="open",
                next_speaker="BOT1",
                thought_open=False,
            )
        assert not pipeline.stopped
        await pipeline.fill(
            _package(),
            segment_phase="open",
            next_speaker="BOT1",
            thought_open=False,
        )
        assert not pipeline.stopped
        assert pipeline.ready.qsize() == 2
        return pipeline

    pipeline = _run(run())
    assert not pipeline.stopped
    assert len(pipeline.planned_transcript) == 2


def test_timeout_invents_no_thought():
    class TimeoutWriter:
        async def write(self, *args, **kwargs):
            raise TextClientError("text request timed out")

    async def run():
        pipeline = WriterPipeline(TimeoutWriter())  # type: ignore[arg-type]
        with pytest.raises(TextClientError, match="timed out"):
            await pipeline.fill(
                _package(),
                segment_phase="open",
                next_speaker="BOT1",
                thought_open=False,
            )
        assert pipeline.planned_transcript == ()
        assert pipeline.aired_transcript == ()
        assert pipeline.ready.qsize() == 0

    _run(run())


def test_cancellation_invents_no_thought():
    started = asyncio.Event()

    class HangingWriter:
        async def write(self, *args, **kwargs):
            started.set()
            await asyncio.sleep(60)
            raise AssertionError("should have been cancelled")

    async def run():
        pipeline = WriterPipeline(HangingWriter())  # type: ignore[arg-type]
        task = asyncio.create_task(
            pipeline.fill(
                _package(),
                segment_phase="open",
                next_speaker="BOT1",
                thought_open=False,
            )
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert pipeline.planned_transcript == ()
        assert pipeline.ready.qsize() == 0

    _run(run())


@pytest.mark.parametrize("segment_phase", ["open", "develop", "close"])
def test_pipeline_passes_only_segment_phase_enum(segment_phase: str):
    writer = RecordingWriter()

    async def run():
        pipeline = WriterPipeline(writer)
        await pipeline.fill(
            _package(),
            segment_phase=segment_phase,  # type: ignore[arg-type]
            next_speaker="BOT1",
            thought_open=False,
        )
        return pipeline

    _run(run())
    assert writer.calls
    for call in writer.calls:
        assert call["segment_phase"] == segment_phase
        assert call["segment_phase"] in {"open", "develop", "close"}
        assert "elapsed_s" not in call
        assert "remaining_submit_slots" not in call


def test_pipeline_alternates_speakers_and_continues_open_thought():
    writer = RecordingWriter(
        [
            _thought(
                speaker="BOT1",
                text="Three civilizations rose and fell in three months.",
                thought_open=True,
            ),
            _thought(
                speaker="BOT1",
                text="The third one took over part of OpenAI itself.",
                thought_open=False,
            ),
        ]
    )

    async def run():
        pipeline = WriterPipeline(writer)
        await pipeline.fill(
            _package(),
            segment_phase="develop",
            next_speaker="BOT1",
            thought_open=False,
        )
        return pipeline

    pipeline = _run(run())
    assert writer.calls[0]["next_speaker"] == "BOT1"
    assert writer.calls[0]["thought_open"] is False
    assert writer.calls[1]["next_speaker"] == "BOT1"
    assert writer.calls[1]["thought_open"] is True
    assert [item.speaker for item in pipeline.planned_transcript] == ["BOT1", "BOT1"]


def test_pipeline_alternates_after_closed_thought():
    writer = RecordingWriter(
        [
            _thought(speaker="BOT1", text="Opening line about the three civilizations."),
            _thought(speaker="BOT2", text="The third one took over part of OpenAI."),
        ]
    )

    async def run():
        pipeline = WriterPipeline(writer)
        await pipeline.fill(
            _package(),
            segment_phase="open",
            next_speaker="BOT1",
            thought_open=False,
        )

    _run(run())
    assert writer.calls[0]["next_speaker"] == "BOT1"
    assert writer.calls[1]["next_speaker"] == "BOT2"


def test_pipeline_enforces_text_request_count_before_each_call():
    limiter = TextAttemptLimiter(2)
    seen: list[int] = []

    async def http_post(url, *, headers, json, timeout):
        seen.append(limiter.attempts)
        payload = {
            "speaker": "BOT1" if limiter.attempts == 1 else "BOT2",
            "text": f"Spoken line number {limiter.attempts} on the civilizations.",
            "thought_open": False,
            "angle_used": "scope",
        }
        import json as json_lib

        return type(
            "FakeResponse",
            (),
            {
                "status_code": 200,
                "json": lambda self: {
                    "choices": [
                        {"message": {"content": json_lib.dumps(payload, separators=(",", ":"))}}
                    ]
                },
            },
        )()

    async def run():
        client = TextClient(
            base_url="https://text.example.invalid/v1",
            api_key="sk-test-text-api-key-abcdef0123456789",
            model="test-model",
            limiter=limiter,
            http_post=http_post,
        )
        pipeline = WriterPipeline(Writer(client))
        await pipeline.fill(
            _package(),
            segment_phase="open",
            next_speaker="BOT1",
            thought_open=False,
        )
        await pipeline.pop_ready()
        with pytest.raises(TextClientError, match="budget|limit"):
            await pipeline.fill(_package(), segment_phase="develop")
        return pipeline

    pipeline = _run(run())
    assert seen == [1, 2]
    assert limiter.attempts == 2
    assert pipeline.ready.qsize() == 1


def test_pipeline_module_does_not_import_live_harness_or_root_scaffold() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "writer_pipeline.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN_ROOT_MODULES)
    assert "fal_client" not in imported
    assert "harness_live" not in imported
    assert "from writer" not in source
    assert "import writer" not in source
    assert "beats_ahead" not in source
    assert "canned" not in source
    assert "host_a" not in source
    assert "host_b" not in source
    assert "asyncio.Queue" in source or "Queue(maxsize=2)" in source
