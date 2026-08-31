"""Task 7: Writer drafts one grounded spoken thought. Fake HTTP only."""

from __future__ import annotations

import ast
import asyncio
import json as json_module
from pathlib import Path
from typing import Any

import pytest

from runtime_flight.models import CoverageState, Fact, HostVoice, SegmentPackage, Thought, TweetCard
from runtime_flight.source import (
    EXPECTED_AUTHOR,
    EXPECTED_LINKED_URL,
    EXPECTED_TWEET_ID,
    EXPECTED_TWEET_URL,
)
from runtime_flight.text_client import TextAttemptLimiter, TextClient, TextClientError
from runtime_flight.writer import Writer, WriterError

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}

SECRET_API_KEY = "sk-test-text-api-key-abcdef0123456789"
SECRET_BASE_URL = "https://text.example.invalid/v1"
SECRET_MODEL = "test-model"
FAL_URL = "https://queue.fal.run/minimax/h3-max/image-to-video"
HERO_PATH = "/secret/local/hero.png"
OBS_REMAINING_S = 47.2


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


def _valid_thought_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "speaker": "BOT1",
        "text": "Three civilizations rose and fell in three months.",
        "thought_open": False,
        "angle_used": "scope",
    }
    payload.update(overrides)
    return payload


class FakeResponse:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _json_body(thought: dict[str, Any], *, usage: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "choices": [{"message": {"content": json_module.dumps(thought, separators=(",", ":"))}}],
    }
    if usage is not None:
        body["usage"] = usage
    return body


def _client(http_post, *, max_requests: int = 8) -> TextClient:
    return TextClient(
        base_url=SECRET_BASE_URL,
        api_key=SECRET_API_KEY,
        model=SECRET_MODEL,
        limiter=TextAttemptLimiter(max_requests),
        http_post=http_post,
    )


def _run(coro):
    return asyncio.run(coro)


async def _write(
    writer: Writer,
    *,
    planned_transcript: tuple[Thought, ...] = (),
    next_speaker: str = "BOT1",
    thought_open: bool = False,
    segment_phase: str = "open",
    target_duration_s: float = 4.3,
    reissue: str | None = None,
) -> Thought:
    return await writer.write(
        _package(),
        planned_transcript,
        next_speaker,  # type: ignore[arg-type]
        thought_open,
        segment_phase,  # type: ignore[arg-type]
        target_duration_s,
        reissue,  # type: ignore[arg-type]
    )


def test_writer_honors_next_speaker_for_both_hosts():
    captured: list[dict[str, Any]] = []

    async def http_post(url, *, headers, json, timeout):
        captured.append(json)
        user = json_module.loads(json["messages"][1]["content"])
        speaker = user["next_speaker"]
        return FakeResponse(200, _json_body(_valid_thought_payload(speaker=speaker)))

    async def run():
        writer = Writer(_client(http_post))
        first = await _write(writer, next_speaker="BOT1")
        second = await _write(writer, next_speaker="BOT2")
        return first, second

    first, second = _run(run())
    assert first.speaker == "BOT1"
    assert second.speaker == "BOT2"
    users = [json_module.loads(item["messages"][1]["content"]) for item in captured]
    assert users[0]["next_speaker"] == "BOT1"
    assert users[1]["next_speaker"] == "BOT2"
    assert first.speaker != "host_a"
    assert second.speaker != "host_b"


def test_writer_sends_full_planned_transcript():
    captured: dict[str, Any] = {}
    planned = (
        _thought(speaker="BOT1", text="Three civilizations rose in three months."),
        _thought(speaker="BOT2", text="Then the third one took over part of OpenAI."),
        _thought(speaker="BOT1", text="Humans stayed in the dark about the scope.", thought_open=True),
    )

    async def http_post(url, *, headers, json, timeout):
        captured["json"] = json
        return FakeResponse(200, _json_body(_valid_thought_payload(speaker="BOT2")))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer, planned_transcript=planned, next_speaker="BOT2")

    thought = _run(run())
    user = json_module.loads(captured["json"]["messages"][1]["content"])
    assert user["planned_transcript"] == [
        {
            "speaker": item.speaker,
            "text": item.text,
            "thought_open": item.thought_open,
            "angle_used": item.angle_used,
            "beat_id": item.beat_id,
            "landed_own_job": item.landed_own_job,
            "beat_exhausted": item.beat_exhausted,
        }
        for item in planned
    ]
    assert thought.speaker == "BOT2"


def test_writer_sends_package_facts():
    captured: dict[str, Any] = {}

    async def http_post(url, *, headers, json, timeout):
        captured["json"] = json
        return FakeResponse(200, _json_body(_valid_thought_payload()))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    _run(run())
    user = json_module.loads(captured["json"]["messages"][1]["content"])
    facts = user["package"]["facts"]
    assert facts == [
        {
            "id": "f1",
            "text": "Three secret AI civilizations started and were wiped out.",
            "source_url": EXPECTED_TWEET_URL,
        },
        {
            "id": "f2",
            "text": "The article retells the OpenAI and Hugging Face story.",
            "source_url": EXPECTED_LINKED_URL,
        },
    ]


def test_writer_sends_thought_open_for_completion():
    captured: dict[str, Any] = {}
    planned = (
        _thought(
            speaker="BOT1",
            text="Three civilizations rose and fell in three months.",
            thought_open=True,
        ),
    )

    async def http_post(url, *, headers, json, timeout):
        captured["system"] = json["messages"][0]["content"]
        captured["user"] = json_module.loads(json["messages"][1]["content"])
        return FakeResponse(
            200,
            _json_body(
                _valid_thought_payload(
                    speaker="BOT1",
                    text="The third one took over part of OpenAI itself.",
                    thought_open=False,
                )
            ),
        )

    async def run():
        writer = Writer(_client(http_post))
        return await _write(
            writer,
            planned_transcript=planned,
            next_speaker="BOT1",
            thought_open=True,
            segment_phase="develop",
        )

    thought = _run(run())
    assert captured["user"]["thought_open"] is True
    assert captured["user"]["next_speaker"] == "BOT1"
    assert "complet" in captured["system"].lower()
    assert thought.speaker == "BOT1"
    assert thought.thought_open is False


@pytest.mark.parametrize("segment_phase", ["open", "develop", "close"])
def test_writer_passes_each_segment_phase(segment_phase: str):
    captured: dict[str, Any] = {}

    async def http_post(url, *, headers, json, timeout):
        captured["user"] = json_module.loads(json["messages"][1]["content"])
        captured["system"] = json["messages"][0]["content"]
        return FakeResponse(200, _json_body(_valid_thought_payload()))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer, segment_phase=segment_phase)

    _run(run())
    assert captured["user"]["segment_phase"] == segment_phase
    assert captured["user"]["segment_phase"] in {"open", "develop", "close"}
    assert "OBS" not in captured["system"]
    assert "elapsed" not in captured["user"]
    assert str(OBS_REMAINING_S) not in json_module.dumps(captured["user"])


def test_writer_prompt_targets_four_to_four_point_six_seconds():
    captured: dict[str, Any] = {}

    async def http_post(url, *, headers, json, timeout):
        captured["system"] = json["messages"][0]["content"]
        captured["user"] = json_module.loads(json["messages"][1]["content"])
        return FakeResponse(200, _json_body(_valid_thought_payload()))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    _run(run())
    system = captured["system"]
    assert "4.0" in system
    assert "4.6" in system
    assert "4.3" in system
    assert "120" in system
    assert "280" not in system
    assert captured["user"]["target_duration_s"] == 4.3


def test_writer_sends_reissue_instruction():
    captured: dict[str, Any] = {}

    async def http_post(url, *, headers, json, timeout):
        captured["system"] = json["messages"][0]["content"]
        captured["user"] = json_module.loads(json["messages"][1]["content"])
        return FakeResponse(200, _json_body(_valid_thought_payload()))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer, reissue="shorter, blander")

    _run(run())
    assert captured["user"]["reissue"] == "shorter, blander"
    assert "shorter, blander" in captured["system"]


def test_wrong_speaker_is_rejected():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(_valid_thought_payload(speaker="BOT2")))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer, next_speaker="BOT1")

    with pytest.raises(WriterError, match="speaker"):
        _run(run())


def test_invented_angle_is_rejected():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(_valid_thought_payload(angle_used="invented")))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    with pytest.raises(WriterError, match="angle"):
        _run(run())


def test_empty_text_is_rejected():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(_valid_thought_payload(text="   ")))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    with pytest.raises(WriterError, match="empty"):
        _run(run())


def test_control_character_text_is_rejected():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            _json_body(_valid_thought_payload(text="hello\x00civilizations")),
        )

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    with pytest.raises(WriterError, match="control"):
        _run(run())


def test_pathological_text_over_120_characters_retries_once_then_rejects():
    calls: list[dict[str, Any]] = []

    async def http_post(url, *, headers, json, timeout):
        calls.append(json_module.loads(json["messages"][1]["content"]))
        return FakeResponse(200, _json_body(_valid_thought_payload(text="x" * 121)))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    with pytest.raises(WriterError, match="120"):
        _run(run())
    assert len(calls) == 2
    assert calls[0]["reissue"] is None
    assert calls[1]["reissue"] == "shorter"
    assert calls[1]["previous_text"] == "x" * 121


def test_overlong_text_is_rewritten_shorter_on_retry():
    calls: list[dict[str, Any]] = []
    long_line = "x" * 163
    short_line = "Three civilizations rose and fell."

    async def http_post(url, *, headers, json, timeout):
        user = json_module.loads(json["messages"][1]["content"])
        calls.append(user)
        if user["reissue"] == "shorter":
            return FakeResponse(200, _json_body(_valid_thought_payload(text=short_line)))
        return FakeResponse(200, _json_body(_valid_thought_payload(text=long_line)))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    thought = _run(run())
    assert thought.text == short_line
    assert len(calls) == 2
    assert calls[1]["previous_text"] == long_line
    assert "shorter" in json_module.dumps(calls)


def test_shorter_reissue_does_not_retry_a_third_time():
    calls: list[dict[str, Any]] = []

    async def http_post(url, *, headers, json, timeout):
        calls.append(json_module.loads(json["messages"][1]["content"]))
        return FakeResponse(200, _json_body(_valid_thought_payload(text="x" * 121)))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer, reissue="shorter")

    with pytest.raises(WriterError, match="120"):
        _run(run())
    assert len(calls) == 1
    assert calls[0]["reissue"] == "shorter"


def test_one_hundred_twenty_character_text_is_accepted():
    line = "x" * 120

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(_valid_thought_payload(text=line)))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    thought = _run(run())
    assert thought.text == line
    assert len(thought.text) == 120


def test_non_bool_thought_open_is_rejected():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(_valid_thought_payload(thought_open="yes")))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    with pytest.raises(WriterError, match="thought_open"):
        _run(run())


def test_fenced_markdown_content_fails_without_stripping():
    fenced = "```json\n" + json_module.dumps(_valid_thought_payload()) + "\n```"

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, {"choices": [{"message": {"content": fenced}}]})

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    with pytest.raises(TextClientError, match="JSON"):
        _run(run())


def test_timeout_returns_no_invented_thought():
    async def http_post(url, *, headers, json, timeout):
        raise TimeoutError("request timed out")

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    with pytest.raises(TextClientError, match="timed out"):
        _run(run())


def test_cancellation_returns_no_invented_thought():
    started = asyncio.Event()

    async def http_post(url, *, headers, json, timeout):
        started.set()
        await asyncio.sleep(60)
        raise AssertionError("should have been cancelled")

    async def run():
        writer = Writer(_client(http_post))
        task = asyncio.create_task(_write(writer))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled() or task.exception() is not None

    _run(run())


def test_limiter_counts_before_every_writer_http_request():
    seen: list[int] = []
    limiter = TextAttemptLimiter(2)

    async def http_post(url, *, headers, json, timeout):
        seen.append(limiter.attempts)
        speaker = json_module.loads(json["messages"][1]["content"])["next_speaker"]
        return FakeResponse(200, _json_body(_valid_thought_payload(speaker=speaker)))

    async def run():
        client = TextClient(
            base_url=SECRET_BASE_URL,
            api_key=SECRET_API_KEY,
            model=SECRET_MODEL,
            limiter=limiter,
            http_post=http_post,
        )
        writer = Writer(client)
        first = await _write(writer)
        second = await _write(writer, next_speaker="BOT2")
        with pytest.raises(TextClientError, match="budget|limit"):
            await _write(writer)
        return first, second

    first, second = _run(run())
    assert first.text
    assert second.text
    assert seen == [1, 2]
    assert limiter.attempts == 2


def test_only_one_writer_http_request_runs_at_once():
    in_flight = 0
    max_in_flight = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def http_post(url, *, headers, json, timeout):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        started.set()
        await release.wait()
        in_flight -= 1
        speaker = json_module.loads(json["messages"][1]["content"])["next_speaker"]
        return FakeResponse(200, _json_body(_valid_thought_payload(speaker=speaker)))

    async def run():
        writer = Writer(_client(http_post))
        first = asyncio.create_task(_write(writer, next_speaker="BOT1"))
        await started.wait()
        second = asyncio.create_task(_write(writer, next_speaker="BOT2"))
        await asyncio.sleep(0)
        assert in_flight == 1
        assert max_in_flight == 1
        release.set()
        results = await asyncio.gather(first, second)
        assert max_in_flight == 1
        return results

    first, second = _run(run())
    assert {first.speaker, second.speaker} == {"BOT1", "BOT2"}


def test_writer_payload_omits_obs_fal_spend_paths_and_secrets():
    captured: dict[str, Any] = {}

    async def http_post(url, *, headers, json, timeout):
        captured["json"] = json
        return FakeResponse(200, _json_body(_valid_thought_payload()))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    _run(run())
    serialized = json_module.dumps(captured["json"])
    system = captured["json"]["messages"][0]["content"]
    for leaked in (HERO_PATH, FAL_URL, SECRET_API_KEY, "OBS", "spend", "fal.run", str(OBS_REMAINING_S)):
        assert leaked not in serialized
        assert leaked not in system


def test_writer_does_not_log_authorization(capsys: pytest.CaptureFixture[str]):
    writer = Writer(
        _client(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no http")))
    )
    rendered = repr(writer) + str(writer)
    assert SECRET_API_KEY not in rendered
    assert "Authorization" not in rendered
    captured = capsys.readouterr()
    assert SECRET_API_KEY not in captured.out
    assert SECRET_API_KEY not in captured.err


def test_writer_sends_current_beat_coverage_and_host_voices():
    captured: dict[str, Any] = {}
    voices = (
        HostVoice("BOT1", "Calm, dry, unhurried technical anchor.", ("Make one clear claim.",)),
        HostVoice("BOT2", "Curious co-host who wants the number.", ("Ask what moved.",)),
    )

    async def http_post(url, *, headers, json, timeout):
        captured["system"] = json["messages"][0]["content"]
        captured["user"] = json_module.loads(json["messages"][1]["content"])
        return FakeResponse(200, _json_body(_valid_thought_payload()))

    async def run():
        writer = Writer(_client(http_post))
        return await writer.write(
            _package(),
            (),
            "BOT1",
            False,
            "open",
            voices=voices,
            coverage=CoverageState.initial(),
        )

    thought = _run(run())
    assert thought.beat_id == "b1"
    user = captured["user"]
    assert user["current_beat"]["id"] == "b1"
    assert user["current_beat"]["bot1_job"] == "scope"
    assert user["current_beat"]["bot2_job"] == "takeover"
    assert user["coverage"]["still_open"]
    assert user["hosts"]["BOT1"]["persona"].startswith("Calm")
    assert user["hosts"]["BOT2"]["writer_rules"] == ["Ask what moved."]
    assert user["hosts"]["BOT1"]["soul"]
    assert user["hosts"]["BOT2"]["opinions"]
    system = captured["system"].lower()
    assert "discussion" in system
    assert "recap" in system
    assert "persona" in system
    assert "empty the well" in system
    assert "PHASEONE" not in captured["system"]
    assert "deb" not in captured["system"]


def test_writer_batches_a_point_into_five_second_chunks():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            _json_body(
                {
                    "speaker": "BOT1",
                    "text": "Monitoring missed a society, not a glitch.",
                    "chunks": [
                        "Monitoring missed a society, not a glitch.",
                        "The watchers blinked while three runs died.",
                        "That is the thesis, and it is not weather.",
                    ],
                    "thought_open": False,
                    "angle_used": "scope",
                    "landed_own_job": True,
                }
            ),
        )

    async def run():
        writer = Writer(_client(http_post))
        return await writer.write_point(_package(), (), "BOT1", False, "develop")

    thoughts = _run(run())
    assert len(thoughts) == 3
    assert [item.speaker for item in thoughts] == ["BOT1", "BOT1", "BOT1"]
    assert [item.thought_open for item in thoughts] == [True, True, False]
    assert [item.landed_own_job for item in thoughts] == [False, False, True]
    assert thoughts[1].text == "The watchers blinked while three runs died."


def test_overlong_spoken_line_is_filed_into_five_second_chunks():
    line = (
        "The watchers blinked while three agent societies rose and fell, "
        "and that is the thesis, not the weather around the card tonight."
    )
    assert len(line) > 120

    calls: list[dict[str, Any]] = []

    async def http_post(url, *, headers, json, timeout):
        calls.append(json_module.loads(json["messages"][1]["content"]))
        return FakeResponse(200, _json_body(_valid_thought_payload(text=line)))

    async def run():
        writer = Writer(_client(http_post))
        return await writer.write_point(_package(), (), "BOT1", False, "open")

    thoughts = _run(run())
    assert len(calls) == 1
    assert all(len(item.text) <= 120 for item in thoughts)
    assert " ".join(item.text for item in thoughts) == line
    assert [item.speaker for item in thoughts] == ["BOT1"] * len(thoughts)
    assert thoughts[0].thought_open is True
    assert thoughts[-1].thought_open is False


def test_wrapped_overflow_keeps_four_files_and_stays_open():
    words = ["civilization"] * 40
    line = " ".join(words)
    assert len(line) > 480

    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            _json_body(
                _valid_thought_payload(
                    text=line,
                    thought_open=False,
                    landed_own_job=True,
                    beat_exhausted=True,
                )
            ),
        )

    async def run():
        writer = Writer(_client(http_post))
        return await writer.write_point(_package(), (), "BOT1", False, "develop")

    thoughts = _run(run())
    assert len(thoughts) == 4
    assert all(len(item.text) <= 120 for item in thoughts)
    assert [item.thought_open for item in thoughts] == [True, True, True, True]
    assert thoughts[-1].landed_own_job is False
    assert thoughts[-1].beat_exhausted is False


def test_writer_rejects_more_than_four_chunks():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            _json_body(
                _valid_thought_payload(
                    chunks=["one", "two", "three", "four", "five"],
                    text="one",
                )
            ),
        )

    async def run():
        writer = Writer(_client(http_post))
        return await writer.write_point(_package(), (), "BOT1", False, "open")

    with pytest.raises(WriterError, match="chunks"):
        _run(run())


def test_writer_rejects_unknown_beat_id():
    async def http_post(url, *, headers, json, timeout):
        return FakeResponse(200, _json_body(_valid_thought_payload(beat_id="nope")))

    async def run():
        writer = Writer(_client(http_post))
        return await _write(writer)

    with pytest.raises(WriterError, match="beat_id"):
        _run(run())


def test_writer_module_does_not_import_root_scaffold_or_live_harness() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "writer.py"
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
    assert "280" not in source
    assert "host_a" not in source
    assert "host_b" not in source
