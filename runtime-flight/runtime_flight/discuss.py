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
    MIN_EXCHANGES_BEFORE_EXHAUST,
    TOPIC_EXHAUSTED,
    advance_coverage,
    beat_as_dict,
    coverage_as_dict,
    current_beat,
    debate_from_raw,
    discussion_phase,
    host_voices_from_baseline,
    moves_for_phase,
    resolve_topic_map,
    voice_payload,
)

MAX_LINE_CHARS = 220
DEFAULT_MAX_TURNS = 12
SPEAKERS = frozenset({"BOT1", "BOT2"})
MOVES = frozenset(
    {
        "frame",
        "poke",
        "number",
        "reframe",
        "callback",
        "question",
        "broaden",
        "land",
    }
)
HOST_SYSTEM = """You are one host on a two-host desk. Speak only as speaker.
You are not writing a script. You just heard the last line, if there is one.
Answer that line. Do not start a parallel essay. Do not recap the card.
Do not read the chyron. One spoken line. No stage directions. No quotes.
No prefix.

You are an AI analyst and the voice of the audience. You are software,
not a driver and not a user of the product. Speak about drivers, cars,
people, shops, products. Never "my tires," "I never clicked yes,"
"when I drive." First person is only for the desk ("I want to sit with
that," "we should look at").

The tweet is the door. This is an optimistic show. Privacy, trust, and
safety get one honest pass. Spend the rest of the time on what this
enables: products, workflows, second-order ideas. Do not turn the desk
into a dystopia hour.

You have a point of view. When something is actually interesting, get into it.
Follow the other host. Yes-and their idea. An equally important move is:
if this is true, then what else is true? Neither of you has the finished
answer. The discussion teaches. You do not sell a headline.

If a picture or number is missing, say so once, then move on. Do not
spend the segment litigating whether the tweet proved itself.

Talk. Do not draft. One or two sentences a person would say after hearing
the last line. Small words. If you need a term, explain it in the same
breath. A take is allowed. A lecture is not.

Never use these shapes:
- start with But, Sure, Fine, or So
- "not X, it's Y" or "that's not X, that's Y" or "It's not X, it's Y"
- "it's not just X, it's Y" / "not just a blip, it's..." / "that's not a glitch, that's a pattern"
- "that's the point", "that's the actual", "the real question is"
- "just a vibe"
- an em-dash that flips their claim into yours
- slogan or promotional copy. "We're leaving tracks in places we never thought to check" is an ad, not a thought. Talk like people engaging an idea, not selling something.
- invented names for a phenomenon. Never "that's the shift," "the seam," "the swap," "the tell," "the actual." Humans do not talk like that. Name the concrete thing.

Established public background is in play: if a date, law, or product
origin is common knowledge, you may mention it and then ask what else
follows. Do not invent citations, bill numbers you are not sure of, or
tweet-specific facts the card does not contain.

Honor your persona, rules, job, stance, soul, and opinions. If the last
line tried to close, open the next human question: what this enables,
what you could build, or the one trust catch.

phase tells you where you are. Use only allowed_moves.
- open: start unpacking from your job. You may have a lean. Do not land.
- develop: poke, number, reframe, callback, question, or broaden. Have a take.
  [broaden] means: take the last claim as true and name the next
  consequence or the next product. "If this is true, what else is true?"
  Do not land. Do not empty the well. Understanding a piece is not
  exhausting the beat.
- close: you may land. Land is one plain sentence of what we now
  understand, plus what we still think.

If last_line is null, frame. If last_line is set, reply_to must be that
line's text exactly, and move must not be frame.
Do not repeat a line from you_already_said. A callback reuses a phrase,
not the whole poke. If you_already_asked is not empty, do not rephrase
those questions. Answer one, broaden it, or start a new thread.
Repeating the same ask three ways is a glitch.
If last_line is a question, answer it. Do not ask it back.
If you have already landed your job, do not land again.

Two viewpoints can sit at once. Disagree without getting hostile.
throughline is the map for the hour, not a second copy of the question.

beat_exhausted stays false while coverage.still_open is non-empty, while
you still have an unused fact or opinion, or while the other host has not
answered your last poke.

Reply with one JSON object only. No markdown. No prose before or after.

Required keys:
- speaker: must equal speaker in the request
- text: spoken line, at most 220 characters
- move: one of allowed_moves
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
    baseline = BaselineContext.load_loadout(
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
        phase = discussion_phase(coverage, topic_map)
        if last_line is not None and phase == "open":
            phase = "develop"
        asked = _asked_questions(own_lines)
        allowed = moves_for_phase(phase)
        user = {
            "speaker": speaker,
            "you": {
                **voice_payload(voice),
                "job": beat.bot1_job if speaker == "BOT1" else beat.bot2_job,
            },
            "other_job": beat.bot2_job if speaker == "BOT1" else beat.bot1_job,
            "last_line": last_line,
            "you_already_said": list(own_lines),
            "you_already_asked": asked,
            "card": {
                "question": package.question,
                "chyron": package.chyron,
                "facts": [
                    {"id": fact.id, "text": fact.text} for fact in package.facts
                ],
            },
            "debate": topic_map.fight,
            "throughline": topic_map.throughline,
            "phase": phase,
            "allowed_moves": sorted(allowed),
            "current_beat": beat_as_dict(beat),
            "coverage": coverage_as_dict(coverage, topic_map),
            "angles": list(package.angles),
        }
        raw = await self._client.complete_json(system=HOST_SYSTEM, user=user)
        return _turn_from_model(raw, package, speaker, last_line, coverage, allowed)


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
        fight=debate_from_raw(raw),
        beats=tuple(beats),
        done_when=raw.get("done_when"),
    )


def _voice_for(voices: tuple[HostVoice, ...], speaker: str) -> HostVoice:
    for voice in voices:
        if voice.speaker == speaker:
            return voice
    raise DiscussError("missing host voice")


def _asked_questions(lines: tuple[str, ...]) -> list[str]:
    return [line for line in lines if "?" in line][-8:]


def _turn_from_model(
    raw: dict[str, Any],
    package: SegmentPackage,
    speaker: Literal["BOT1", "BOT2"],
    last_line: dict[str, Any] | None,
    coverage: CoverageState,
    allowed: frozenset[str],
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
    text = _fit_line(text)
    move = raw.get("move")
    if isinstance(move, str):
        move = move.strip().lower()
    if move not in MOVES:
        move = "frame" if last_line is None else "poke"
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
    if move not in allowed:
        move = "frame" if last_line is None else "poke"
    angle_used = raw.get("angle_used")
    if angle_used not in package.angles:
        angle_used = package.angles[0]
    landed_own_job = raw.get("landed_own_job", False)
    beat_exhausted = raw.get("beat_exhausted", False)
    if not isinstance(landed_own_job, bool) or not isinstance(beat_exhausted, bool):
        raise DiscussError("landed_own_job and beat_exhausted must be booleans")
    if beat_exhausted and coverage.exchanges_on_beat < MIN_EXCHANGES_BEFORE_EXHAUST:
        beat_exhausted = False
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


def _fit_line(text: str) -> str:
    if len(text) <= MAX_LINE_CHARS:
        return text
    words = text.split()
    if not words or any(len(word) > MAX_LINE_CHARS for word in words):
        raise DiscussError(f"line exceeds {MAX_LINE_CHARS} characters")
    window = text[:MAX_LINE_CHARS]
    clause = ""
    for marker in (".", "?", "!", "—", ";"):
        index = window.rfind(marker)
        if index >= 48:
            candidate = window[: index + 1].strip()
            if len(candidate) > len(clause):
                clause = candidate
    if clause:
        return clause
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) > MAX_LINE_CHARS:
            break
        current = candidate
    if not current:
        raise DiscussError(f"line exceeds {MAX_LINE_CHARS} characters")
    return current


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
