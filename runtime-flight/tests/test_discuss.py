"""Text-only host bounce. Fake HTTP only. No fal."""

from __future__ import annotations

import ast
import asyncio
import json as json_module
from pathlib import Path
from typing import Any

import pytest

from runtime_flight.discuss import (
    HOST_SYSTEM,
    DiscussError,
    HostMind,
    load_package,
    run_discuss,
)
from runtime_flight.models import CoverageState, Fact, HostVoice, SegmentPackage, TweetCard
from runtime_flight.source import (
    EXPECTED_AUTHOR,
    EXPECTED_LINKED_URL,
    EXPECTED_TWEET_ID,
    EXPECTED_TWEET_URL,
)
from runtime_flight.text_client import TextAttemptLimiter, TextClient
from runtime_flight.__main__ import main
from test_preflight import (
    _complete_env,
    _make_flight_setup,
    _write_flight_config,
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


def _voices() -> tuple[HostVoice, HostVoice]:
    return (
        HostVoice(speaker="BOT1", persona="Calm, dry.", rules=("Stay dry.",)),
        HostVoice(speaker="BOT2", persona="Wants the number.", rules=("Ask what moved.",)),
    )


def _valid_turn(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "speaker": "BOT1",
        "text": "Is this a thesis, or just weather around a crash?",
        "move": "frame",
        "reply_to": None,
        "angle_used": "scope",
        "landed_own_job": False,
        "beat_exhausted": False,
    }
    payload.update(overrides)
    return payload


class FakeResponse:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        return self._body


def _json_body(turn: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": json_module.dumps(turn, separators=(",", ":"))}}],
    }


def _client(http_post, *, max_requests: int = 8) -> TextClient:
    return TextClient(
        base_url="https://text.example.invalid/v1",
        api_key="sk-test-text-api-key-abcdef0123456789",
        model="test-model",
        limiter=TextAttemptLimiter(max_requests),
        http_post=http_post,
    )


def _run(coro):
    return asyncio.run(coro)


def test_host_mind_sees_last_line_not_a_script():
    captured: dict[str, Any] = {}

    async def http_post(url, *, headers, json, timeout):
        captured["user"] = json_module.loads(json["messages"][1]["content"])
        captured["system"] = json["messages"][0]["content"]
        return FakeResponse(
            200,
            _json_body(
                _valid_turn(
                    speaker="BOT2",
                    text="Then give me the number that moved.",
                    move="poke",
                    reply_to="Is this a thesis, or just weather around a crash?",
                    angle_used="takeover",
                )
            ),
        )

    async def run():
        mind = HostMind(_client(http_post))
        return await mind.reply(
            _package(),
            speaker="BOT2",
            last_line={
                "speaker": "BOT1",
                "text": "Is this a thesis, or just weather around a crash?",
                "move": "frame",
            },
            own_lines=(),
            coverage=CoverageState.initial(),
            voices=_voices(),
        )

    thought, turn = _run(run())
    assert thought.speaker == "BOT2"
    assert thought.thought_open is False
    assert turn["move"] == "poke"
    user = captured["user"]
    assert user["speaker"] == "BOT2"
    assert user["last_line"]["text"].startswith("Is this a thesis")
    assert "planned_transcript" not in user
    assert user["you"]["stance"]
    assert "script" in captured["system"]
    assert "PHASEONE" not in captured["system"]
    assert "deb" not in captured["system"]


def test_first_line_must_frame_and_later_lines_must_reply():
    async def first(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            _json_body(_valid_turn(move="poke", reply_to=None)),
        )

    async def bad_reply(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            _json_body(
                _valid_turn(
                    speaker="BOT2",
                    text="Meanwhile, a separate essay about autonomy.",
                    move="frame",
                    reply_to=None,
                )
            ),
        )

    async def missing_reply(url, *, headers, json, timeout):
        return FakeResponse(
            200,
            _json_body(
                _valid_turn(
                    speaker="BOT2",
                    text="Name the cluster.",
                    move="number",
                    reply_to="not the last line",
                )
            ),
        )

    last = {
        "speaker": "BOT1",
        "text": "Is this a thesis, or just weather around a crash?",
        "move": "frame",
    }

    async def run_first():
        return await HostMind(_client(first)).reply(
            _package(),
            speaker="BOT1",
            last_line=None,
            own_lines=(),
            coverage=CoverageState.initial(),
            voices=_voices(),
        )

    async def run_frame():
        return await HostMind(_client(bad_reply)).reply(
            _package(),
            speaker="BOT2",
            last_line=last,
            own_lines=(),
            coverage=CoverageState.initial(),
            voices=_voices(),
        )

    async def run_mismatch():
        return await HostMind(_client(missing_reply)).reply(
            _package(),
            speaker="BOT2",
            last_line=last,
            own_lines=(),
            coverage=CoverageState.initial(),
            voices=_voices(),
        )

    with pytest.raises(DiscussError, match="frame"):
        _run(run_first())
    with pytest.raises(DiscussError, match="frame"):
        _run(run_frame())
    with pytest.raises(DiscussError, match="reply_to"):
        _run(run_mismatch())


def test_run_discuss_alternates_and_writes_transcript(tmp_path: Path, monkeypatch):
    flight_setup = _make_flight_setup(tmp_path / "pack-root")
    _complete_env(monkeypatch, flight_setup)
    config_path = _write_flight_config(tmp_path, flight_setup)
    from runtime_flight.config import load_config

    config = load_config(config_path)
    lines = [
        _valid_turn(
            speaker="BOT1",
            text="Is this weather, or did control actually move?",
            move="frame",
            reply_to=None,
        ),
        _valid_turn(
            speaker="BOT2",
            text="Then name the cluster and the twelve hundred agents.",
            move="number",
            reply_to="Is this weather, or did control actually move?",
            angle_used="takeover",
            landed_own_job=True,
        ),
        _valid_turn(
            speaker="BOT1",
            text="A wipe after the fact is still weather, not a thesis.",
            move="reframe",
            reply_to="Then name the cluster and the twelve hundred agents.",
            landed_own_job=True,
            beat_exhausted=True,
        ),
        _valid_turn(
            speaker="BOT2",
            text="Admin creds on the third wave is the stake. That is it.",
            move="land",
            reply_to="A wipe after the fact is still weather, not a thesis.",
            angle_used="takeover",
            landed_own_job=True,
            beat_exhausted=True,
        ),
    ]
    calls: list[dict[str, Any]] = []

    async def http_post(url, *, headers, json, timeout):
        user = json_module.loads(json["messages"][1]["content"])
        calls.append(user)
        return FakeResponse(200, _json_body(lines[len(calls) - 1]))

    payload = run_discuss(
        config=config,
        max_text_requests=4,
        max_turns=4,
        package=_package(),
        out_dir=tmp_path / "discussions",
        http_post=http_post,
    )
    assert [item["speaker"] for item in payload["turns"]] == [
        "BOT1",
        "BOT2",
        "BOT1",
        "BOT2",
    ]
    assert payload["stop_reason"] == "topic exhausted"
    assert calls[1]["last_line"]["speaker"] == "BOT1"
    assert "planned_transcript" not in calls[1]
    text = Path(payload["work_dir"], "transcript.txt").read_text(encoding="utf-8")
    assert "BOT2 [number]" in text


def test_discuss_cli_refuses_without_confirm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    flight_setup = _make_flight_setup(tmp_path / "pack-root")
    _complete_env(monkeypatch, flight_setup)
    config_path = _write_flight_config(tmp_path, flight_setup)
    with pytest.raises(SystemExit) as raised:
        main(["discuss", "--config", str(config_path), "--max-turns", "4"])
    captured = capsys.readouterr()
    assert raised.value.code == 2
    assert "confirm-text-requests" in captured.err


def test_discuss_cli_refuses_confirm_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    flight_setup = _make_flight_setup(tmp_path / "pack-root")
    _complete_env(monkeypatch, flight_setup)
    config_path = _write_flight_config(tmp_path, flight_setup)
    code = main(
        [
            "discuss",
            "--config",
            str(config_path),
            "--max-turns",
            "4",
            "--confirm-text-requests",
            "4",
        ],
        discuss_runner=lambda **kwargs: {"work_dir": str(tmp_path)},
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "planner" in captured.err


def test_load_package_roundtrip(tmp_path: Path):
    raw = {
        "item_id": EXPECTED_TWEET_ID,
        "question": "What happened to the secret AI civilizations?",
        "framing": "A reviewed account of three wiped-out agent societies.",
        "angles": ["scope", "takeover"],
        "facts": [
            {
                "id": "f1",
                "text": "Three secret AI civilizations started and were wiped out.",
                "source_url": EXPECTED_TWEET_URL,
            }
        ],
        "chyron": "Secret AI civilizations",
        "chyron_fact_ids": ["f1"],
        "center": {
            "author": EXPECTED_AUTHOR,
            "text": "Hello café\nworld",
            "url": EXPECTED_TWEET_URL,
        },
        "topic_map": {
            "throughline": "Was this autonomy or weather?",
            "fight": "Thesis versus number.",
            "done_when": "Both jobs landed.",
            "beats": [
                {
                    "id": "b1",
                    "question": "Did control move?",
                    "tension": "Warning versus glitch.",
                    "bot1_job": "Land the thesis.",
                    "bot2_job": "Land the number.",
                    "fact_ids": ["f1"],
                    "done_when": "Both landed.",
                }
            ],
        },
    }
    path = tmp_path / "package.json"
    path.write_text(json_module.dumps(raw), encoding="utf-8")
    package = load_package(path)
    assert package.item_id == raw["item_id"]
    assert package.topic_map is not None
    assert package.topic_map.beats[0].id == "b1"


def test_discuss_source_has_no_forbidden_names():
    source = ast.parse(Path("runtime_flight/discuss.py").read_text(encoding="utf-8"))
    text = Path("runtime_flight/discuss.py").read_text(encoding="utf-8")
    assert "host_a" not in text
    assert "host_b" not in text
    assert "PHASEONE" not in text
    assert isinstance(source, ast.Module)
