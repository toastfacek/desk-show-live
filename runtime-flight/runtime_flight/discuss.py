"""Two host minds. Each turn answers the last line. No script, no fal."""

from __future__ import annotations

import asyncio
import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from runtime_flight.baseline import BaselineContext
from runtime_flight.config import RuntimeConfig
from runtime_flight.models import (
    Beat,
    CoverageState,
    Fact,
    HostVoice,
    SegmentPackage,
    Thought,
    TopicMap,
    TweetCard,
)
from runtime_flight.segment_planner import SegmentPlanner
from runtime_flight.source import load_source_packet
from runtime_flight.text_client import TextAttemptLimiter, TextClient
from runtime_flight.topic_map import (
    TOPIC_EXHAUSTED,
    advance_coverage,
    beat_as_dict,
    coverage_as_dict,
    current_beat,
    host_voices_from_baseline,
    resolve_topic_map,
    voice_payload,
)

MAX_LINE_CHARS = 120
DEFAULT_MAX_TURNS = 12
SPEAKERS = frozenset({"BOT1", "BOT2"})
MOVES = frozenset(
    {"frame", "poke", "number", "reframe", "callback", "question", "land"}
)
STANCE = {
    "BOT1": "Treat the card as weather until someone shows that control actually moved.",
    "BOT2": "If you cannot name the number, the cluster, or who got hit, it is a vibe.",
}

HOST_SYSTEM = """You are one host on a two-host desk. Speak only as speaker.
You are not writing a script. You just heard the last line, if there is one.
Answer that. Poke it, number it, reframe it, ask a question, or land.
Do not start a parallel essay. Do not recap the card. Do not read the chyron.
One spoken line. No stage directions. No quotes. No prefix.

If last_line is null, frame the question from your job and stance.
If last_line is set, reply_to must be that line's text exactly, and move
must not be frame.

Honor your persona, rules, job, and stance. The other host asks a different
question of the same card. They agree the card is real.

Required keys:
- speaker: must equal speaker in the request
- text: spoken line, at most 120 characters
- move: frame, poke, number, reframe, callback, question, or land
- reply_to: the last line's text, or null if this is the first line
- angle_used: one of the package angles
- landed_own_job: true only if this line actually lands your beat job
- beat_exhausted: true only if you have nothing grounded left on this beat
"""


class DiscussError(Exception):
    """Raised when a host turn is invalid or the inspect cannot run."""


def run_discuss(
    *,
    config: RuntimeConfig,
    max_text_requests: int,
    max_turns: int = DEFAULT_MAX_TURNS,
    package: SegmentPackage | None = None,
    out_dir: Path | None = None,
    http_post=None,
) -> dict[str, Any]:
    return asyncio.run(
        _run_discuss_async(
            config=config,
            max_text_requests=max_text_requests,
            max_turns=max_turns,
            package=package,
            out_dir=out_dir,
            http_post=http_post,
        )
    )


async def _run_discuss_async(
    *,
    config: RuntimeConfig,
    max_text_requests: int,
    max_turns: int,
    package: SegmentPackage | None,
    out_dir: Path | None,
    http_post,
) -> dict[str, Any]:
    if max_turns < 1:
        raise DiscussError("max_turns must be at least 1")
    source = load_source_packet(config.source_packet, config.source_lock)
    baseline = BaselineContext.load(
        config.pack_manager_data_dir, config.baseline_id or ""
    )
    limiter = TextAttemptLimiter(max_text_requests)
    client = TextClient(
        base_url=config.text_base_url or "",
        api_key=config.text_api_key or "",
        model=config.text_model or "",
        limiter=limiter,
        http_post=http_post,
        timeout_s=float(config.text_timeout_s),
    )
    voices = host_voices_from_baseline(baseline)
    if package is None:
        package = await SegmentPlanner(client).plan(
            source, baseline, time_budget_s=int(config.target_duration_s), voices=voices
        )
    topic_map = resolve_topic_map(package)
    coverage = CoverageState.initial()
    mind = HostMind(client)
    turns: list[dict[str, Any]] = []
    last: dict[str, Any] | None = None
    speaker: Literal["BOT1", "BOT2"] = "BOT1"
    stop_reason = "turn cap"

    for index in range(1, max_turns + 1):
        if coverage.map_complete:
            stop_reason = coverage.stop_reason or TOPIC_EXHAUSTED
            break
        thought, turn = await mind.reply(
            package,
            speaker=speaker,
            last_line=last,
            own_lines=tuple(
                item["text"] for item in turns if item["speaker"] == speaker
            ),
            coverage=coverage,
            voices=voices,
        )
        coverage = advance_coverage(coverage, thought, topic_map)
        row = {"turn": index, **turn}
        turns.append(row)
        last = {
            "speaker": thought.speaker,
            "text": thought.text,
            "move": turn["move"],
        }
        speaker = "BOT2" if speaker == "BOT1" else "BOT1"
        if coverage.map_complete:
            stop_reason = coverage.stop_reason or TOPIC_EXHAUSTED
            break

    if not turns:
        raise DiscussError("discuss produced no turns")

    discuss_id = f"discuss-{_stamp()}"
    work_dir = Path(out_dir or "out/discussions") / discuss_id
    work_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "discuss_id": discuss_id,
        "mode": "inspect",
        "stop_reason": stop_reason,
        "text_requests": limiter.attempts,
        "text_request_limit": max_text_requests,
        "turns": turns,
        "speakers": [item["speaker"] for item in turns],
        "package": {
            "item_id": package.item_id,
            "question": package.question,
            "chyron": package.chyron,
        },
    }
    (work_dir / "transcript.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    (work_dir / "transcript.txt").write_text(
        _transcript_text(payload), encoding="utf-8"
    )
    payload["work_dir"] = str(work_dir)
    return payload


class HostMind:
    def __init__(self, client: TextClient) -> None:
        self._client = client

    async def reply(
        self,
        package: SegmentPackage,
        *,
        speaker: Literal["BOT1", "BOT2"],
        last_line: dict[str, Any] | None,
        own_lines: tuple[str, ...],
        coverage: CoverageState,
        voices: tuple[HostVoice, ...],
    ) -> tuple[Thought, dict[str, Any]]:
        if speaker not in SPEAKERS:
            raise DiscussError("speaker must be BOT1 or BOT2")
        voice = _voice_for(voices, speaker)
        topic_map = resolve_topic_map(package)
        beat = current_beat(topic_map, coverage)
        user = {
            "speaker": speaker,
            "you": {
                **voice_payload(voice),
                "job": beat.bot1_job if speaker == "BOT1" else beat.bot2_job,
                "stance": STANCE[speaker],
            },
            "last_line": last_line,
            "you_already_said": list(own_lines),
            "card": {
                "question": package.question,
                "chyron": package.chyron,
                "facts": [
                    {"id": fact.id, "text": fact.text} for fact in package.facts
                ],
            },
            "current_beat": beat_as_dict(beat),
            "coverage": coverage_as_dict(coverage, topic_map),
            "angles": list(package.angles),
        }
        raw = await self._client.complete_json(system=HOST_SYSTEM, user=user)
        return _turn_from_model(raw, package, speaker, last_line, coverage)


def package_from_dict(raw: dict[str, Any]) -> SegmentPackage:
    if not isinstance(raw, dict):
        raise DiscussError("package must be a JSON object")
    facts_raw = raw.get("facts")
    if not isinstance(facts_raw, list):
        raise DiscussError("package facts must be an array")
    try:
        facts = tuple(
            Fact(
                id=item["id"],
                text=item["text"],
                source_url=item["source_url"],
            )
            for item in facts_raw
            if isinstance(item, dict)
        )
        center_raw = raw.get("center") or {}
        center = TweetCard(
            author=center_raw.get("author"),
            text=center_raw.get("text"),
            url=center_raw.get("url"),
        )
        topic_map = _topic_map_from_dict(raw.get("topic_map"), {fact.id for fact in facts})
        return SegmentPackage(
            item_id=raw.get("item_id"),
            question=raw.get("question"),
            framing=raw.get("framing"),
            angles=tuple(raw.get("angles") or ()),
            facts=facts,
            chyron=raw.get("chyron"),
            chyron_fact_ids=tuple(raw.get("chyron_fact_ids") or ()),
            center=center,
            topic_map=topic_map,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DiscussError(str(error)) from error


def load_package(path: Path) -> SegmentPackage:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DiscussError("package file is not valid JSON") from error
    if not isinstance(raw, dict):
        raise DiscussError("package must be a JSON object")
    return package_from_dict(raw)


def _topic_map_from_dict(raw: object, fact_ids: set[str]) -> TopicMap | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise DiscussError("topic_map must be an object")
    beats_raw = raw.get("beats")
    if not isinstance(beats_raw, list):
        raise DiscussError("topic_map beats must be an array")
    beats: list[Beat] = []
    for item in beats_raw:
        if not isinstance(item, dict):
            raise DiscussError("each beat must be an object")
        beat_fact_ids = item.get("fact_ids")
        if not isinstance(beat_fact_ids, list):
            raise DiscussError("beat fact_ids must be an array")
        for fact_id in beat_fact_ids:
            if fact_id not in fact_ids:
                raise DiscussError("beat fact_id does not reference a returned fact")
        beats.append(
            Beat(
                id=item.get("id"),
                question=item.get("question"),
                tension=item.get("tension"),
                bot1_job=item.get("bot1_job"),
                bot2_job=item.get("bot2_job"),
                fact_ids=tuple(beat_fact_ids),
                done_when=item.get("done_when"),
            )
        )
    return TopicMap(
        throughline=raw.get("throughline"),
        fight=raw.get("fight"),
        beats=tuple(beats),
        done_when=raw.get("done_when"),
    )


def _voice_for(voices: tuple[HostVoice, ...], speaker: str) -> HostVoice:
    for voice in voices:
        if voice.speaker == speaker:
            return voice
    raise DiscussError("missing host voice")


def _turn_from_model(
    raw: dict[str, Any],
    package: SegmentPackage,
    speaker: Literal["BOT1", "BOT2"],
    last_line: dict[str, Any] | None,
    coverage: CoverageState,
) -> tuple[Thought, dict[str, Any]]:
    if not isinstance(raw, dict):
        raise DiscussError("host result is not a JSON object")
    if raw.get("speaker") != speaker:
        raise DiscussError("speaker must equal the requested host")
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise DiscussError("line is empty")
    if any(unicodedata.category(char) == "Cc" for char in text):
        raise DiscussError("line contains a control character")
    if len(text) > MAX_LINE_CHARS:
        raise DiscussError("line exceeds 120 characters")
    move = raw.get("move")
    if move not in MOVES:
        raise DiscussError("move must be a known conversational move")
    reply_to = raw.get("reply_to")
    if last_line is None:
        if move != "frame":
            raise DiscussError("first line must frame")
        if reply_to is not None:
            raise DiscussError("first line reply_to must be null")
    else:
        if move == "frame":
            raise DiscussError("later lines must not frame")
        if reply_to != last_line.get("text"):
            raise DiscussError("reply_to must repeat the last line")
    angle_used = raw.get("angle_used")
    if angle_used not in package.angles:
        raise DiscussError("angle_used is not a package angle")
    landed_own_job = raw.get("landed_own_job", False)
    beat_exhausted = raw.get("beat_exhausted", False)
    if not isinstance(landed_own_job, bool) or not isinstance(beat_exhausted, bool):
        raise DiscussError("landed_own_job and beat_exhausted must be booleans")
    topic_map = resolve_topic_map(package)
    beat = current_beat(topic_map, coverage)
    thought = Thought(
        speaker=speaker,
        text=text,
        thought_open=False,
        angle_used=angle_used,
        beat_id=beat.id,
        landed_own_job=landed_own_job,
        beat_exhausted=beat_exhausted,
    )
    turn = {
        "speaker": speaker,
        "text": text,
        "move": move,
        "reply_to": reply_to,
        "angle_used": angle_used,
        "landed_own_job": landed_own_job,
        "beat_exhausted": beat_exhausted,
    }
    return thought, turn


def _transcript_text(payload: dict[str, Any]) -> str:
    lines = [
        f"discuss_id: {payload['discuss_id']}",
        f"stop_reason: {payload['stop_reason']}",
        f"turns: {len(payload['turns'])}  text_requests: {payload['text_requests']}",
        f"question: {payload['package']['question']}",
        "",
        "TRANSCRIPT",
    ]
    for item in payload["turns"]:
        lines.append(
            f"{item['turn']:02d} {item['speaker']} [{item['move']}]  {item['text']}"
        )
    return "\n".join(lines) + "\n"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
