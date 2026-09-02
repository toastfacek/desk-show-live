"""Topic map resolution and beat coverage. Clock does not live here."""

from __future__ import annotations

from typing import Literal

from runtime_flight.baseline import BaselineContext, CharacterPackTruth
from runtime_flight.models import (
    Beat,
    CoverageState,
    HostVoice,
    SegmentPackage,
    Thought,
    TopicMap,
)

TOPIC_EXHAUSTED = "topic exhausted"
MIN_EXCHANGES_BEFORE_EXHAUST = 6
MIN_EXCHANGES_BEFORE_COMPLETE = 8
OPEN_MOVES = frozenset({"frame"})
DEVELOP_MOVES = frozenset(
    {"poke", "number", "reframe", "callback", "question", "broaden"}
)
CLOSE_MOVES = DEVELOP_MOVES | {"land"}

DEFAULT_STANCE = {
    "BOT1": "Unpack the capability, then say what it unlocks and what someone could build.",
    "BOT2": "Yes-and the last claim. If this is true, what else is true?",
}
DEFAULT_SOUL = {
    "BOT1": (
        "You get interested in public. The fun part is what this enables, "
        "not whether the post proved itself. The conversation teaches. You "
        "do not deliver the finished answer."
    ),
    "BOT2": (
        "You learn in public. If they are litigating the tweet, ask what it "
        "unlocks. You do not deliver the answer. You make the next step "
        "visible, and you have a take on it."
    ),
}
DEFAULT_OPINIONS = {
    "BOT1": (
        "The interesting part is what you could build, and the one trust catch.",
        "If we skip a step, the audience skips it too.",
        "Privacy gets a pass. Products get the hour.",
    ),
    "BOT2": (
        "If I do not get why I should care, they do not get it.",
        "A missing screenshot is a caveat, not the show.",
        "Two analysts figuring out what this unlocks is the show.",
    ),
}


def debate_from_raw(raw: dict[str, object]) -> object:
    for key in ("debate", "fight"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if value is not None and not isinstance(value, str):
            return value
    return raw.get("debate") if "debate" in raw else raw.get("fight")


def host_voices_from_baseline(baseline: BaselineContext) -> tuple[HostVoice, HostVoice]:
    voices = [_voice_from_character(character) for character in baseline.characters]
    voices.sort(key=lambda voice: voice.speaker)
    if len(voices) != 2 or {voice.speaker for voice in voices} != {"BOT1", "BOT2"}:
        raise ValueError("baseline must expose BOT1 and BOT2 host voices")
    return voices[0], voices[1]


def _voice_from_character(character: CharacterPackTruth) -> HostVoice:
    slot = character.slot
    persona = character.manifest.get("persona")
    rules = character.manifest.get("writer_rules")
    if not isinstance(persona, str) or not persona.strip():
        persona = (
            "Walk through the capability the post showed, then say what it unlocks."
            if slot == "BOT1"
            else "Yes-and the last claim, then have a take on what else is true."
        )
    clean_rules: list[str] = []
    if isinstance(rules, (list, tuple)):
        clean_rules.extend(
            rule for rule in rules if isinstance(rule, str) and rule.strip()
        )
    if not clean_rules:
        if slot == "BOT1":
            clean_rules.append("Name the capability, then what you could build.")
        else:
            clean_rules.append("Yes-and. If this is true, what else is true?")
    return HostVoice(
        speaker=slot,
        persona=persona,
        rules=tuple(clean_rules),
        soul=_optional_text(character.manifest.get("soul"), DEFAULT_SOUL[slot]),
        opinions=_optional_strings(
            character.manifest.get("opinions"), DEFAULT_OPINIONS[slot]
        ),
        stance=_optional_text(character.manifest.get("stance"), DEFAULT_STANCE[slot]),
    )


def _optional_text(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return fallback


def _optional_strings(value: object, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        cleaned = tuple(
            item for item in value if isinstance(item, str) and item.strip()
        )
        if cleaned:
            return cleaned
    return fallback


def moves_for_phase(phase: Literal["open", "develop", "close"]) -> frozenset[str]:
    if phase == "open":
        return OPEN_MOVES
    if phase == "close":
        return CLOSE_MOVES
    return DEVELOP_MOVES


def resolve_topic_map(package: SegmentPackage) -> TopicMap:
    if package.topic_map is not None:
        return package.topic_map
    return synthesize_topic_map(package)


def synthesize_topic_map(package: SegmentPackage) -> TopicMap:
    bot1_job = package.angles[0]
    bot2_job = package.angles[1] if len(package.angles) > 1 else package.angles[0]
    tension = package.framing[:280] if package.framing else package.question
    beat = Beat(
        id="b1",
        question=package.question,
        tension=tension,
        bot1_job=bot1_job,
        bot2_job=bot2_job,
        fact_ids=tuple(fact.id for fact in package.facts),
        done_when="Both hosts have landed their job and have nothing grounded left to add.",
    )
    return TopicMap(
        throughline=(
            "what this capability unlocks, what you could build from it, "
            "and the one privacy or trust catch that still matters"
        ),
        fight=(
            "optimistic product brainstorm versus the one trust catch, "
            "without treating the tweet as a crime scene"
        ),
        beats=(beat,),
        done_when="The throughline has been explored from both host jobs.",
    )


def current_beat(topic_map: TopicMap, coverage: CoverageState) -> Beat:
    index = min(coverage.beat_index, len(topic_map.beats) - 1)
    return topic_map.beats[index]


def discussion_phase(
    coverage: CoverageState, topic_map: TopicMap
) -> Literal["open", "develop", "close"]:
    if coverage.map_complete:
        return "close"
    nothing_said = (
        coverage.beat_index == 0
        and coverage.exchanges_on_beat == 0
        and not coverage.bot1_landed
        and not coverage.bot2_landed
    )
    if nothing_said:
        return "open"
    last_beat = coverage.beat_index >= len(topic_map.beats) - 1
    if last_beat and coverage.exchanges_on_beat >= MIN_EXCHANGES_BEFORE_COMPLETE:
        return "close"
    return "develop"


def advance_coverage(
    state: CoverageState, thought: Thought, topic_map: TopicMap
) -> CoverageState:
    if state.map_complete:
        return state
    beat = current_beat(topic_map, state)
    beat_id = thought.beat_id or beat.id
    if beat_id != beat.id:
        return state

    bot1_landed = set(state.bot1_landed)
    bot2_landed = set(state.bot2_landed)
    bot1_exhausted = set(state.bot1_exhausted)
    bot2_exhausted = set(state.bot2_exhausted)
    if thought.landed_own_job:
        if thought.speaker == "BOT1":
            bot1_landed.add(beat.id)
        else:
            bot2_landed.add(beat.id)
    exchanges = state.exchanges_on_beat + (0 if thought.thought_open else 1)
    if thought.beat_exhausted and exchanges >= MIN_EXCHANGES_BEFORE_EXHAUST:
        if thought.speaker == "BOT1":
            bot1_exhausted.add(beat.id)
        else:
            bot2_exhausted.add(beat.id)

    both_landed = beat.id in bot1_landed and beat.id in bot2_landed
    both_exhausted = beat.id in bot1_exhausted and beat.id in bot2_exhausted
    last_beat = state.beat_index >= len(topic_map.beats) - 1
    ready_to_leave = both_landed and both_exhausted
    if last_beat:
        ready_to_leave = ready_to_leave and exchanges >= MIN_EXCHANGES_BEFORE_COMPLETE
    if not ready_to_leave:
        return CoverageState(
            beat_index=state.beat_index,
            bot1_landed=frozenset(bot1_landed),
            bot2_landed=frozenset(bot2_landed),
            bot1_exhausted=frozenset(bot1_exhausted),
            bot2_exhausted=frozenset(bot2_exhausted),
            exchanges_on_beat=exchanges,
            map_complete=False,
            stop_reason="",
        )

    next_index = state.beat_index + 1
    if next_index >= len(topic_map.beats):
        return CoverageState(
            beat_index=state.beat_index,
            bot1_landed=frozenset(bot1_landed),
            bot2_landed=frozenset(bot2_landed),
            bot1_exhausted=frozenset(bot1_exhausted),
            bot2_exhausted=frozenset(bot2_exhausted),
            exchanges_on_beat=exchanges,
            map_complete=True,
            stop_reason=TOPIC_EXHAUSTED,
        )
    return CoverageState(
        beat_index=next_index,
        bot1_landed=frozenset(bot1_landed),
        bot2_landed=frozenset(bot2_landed),
        bot1_exhausted=frozenset(bot1_exhausted),
        bot2_exhausted=frozenset(bot2_exhausted),
        exchanges_on_beat=0,
        map_complete=False,
        stop_reason="",
    )


def coverage_as_dict(coverage: CoverageState, topic_map: TopicMap) -> dict[str, object]:
    beat = current_beat(topic_map, coverage)
    still_open: list[str] = []
    if beat.id not in coverage.bot1_landed:
        still_open.append("BOT1 has not landed their job yet")
    if beat.id not in coverage.bot2_landed:
        still_open.append("BOT2 has not landed their job yet")
    if beat.id in coverage.bot1_landed and beat.id not in coverage.bot1_exhausted:
        still_open.append("BOT1 still has more to say on this beat")
    if beat.id in coverage.bot2_landed and beat.id not in coverage.bot2_exhausted:
        still_open.append("BOT2 still has more to say on this beat")
    if coverage.exchanges_on_beat < MIN_EXCHANGES_BEFORE_COMPLETE:
        still_open.append("the well is not empty yet; keep the debate going")
    if coverage.map_complete:
        still_open = []
    return {
        "beat_id": beat.id,
        "beat_index": coverage.beat_index,
        "bot1_landed": beat.id in coverage.bot1_landed,
        "bot2_landed": beat.id in coverage.bot2_landed,
        "bot1_exhausted": beat.id in coverage.bot1_exhausted,
        "bot2_exhausted": beat.id in coverage.bot2_exhausted,
        "exchanges_on_beat": coverage.exchanges_on_beat,
        "map_complete": coverage.map_complete,
        "still_open": still_open,
    }


def beat_as_dict(beat: Beat) -> dict[str, object]:
    return {
        "id": beat.id,
        "question": beat.question,
        "tension": beat.tension,
        "bot1_job": beat.bot1_job,
        "bot2_job": beat.bot2_job,
        "fact_ids": list(beat.fact_ids),
        "done_when": beat.done_when,
    }


def topic_map_as_dict(topic_map: TopicMap) -> dict[str, object]:
    return {
        "throughline": topic_map.throughline,
        "debate": topic_map.fight,
        "fight": topic_map.fight,
        "done_when": topic_map.done_when,
        "beats": [beat_as_dict(beat) for beat in topic_map.beats],
    }


def voice_payload(voice: HostVoice) -> dict[str, object]:
    speaker = voice.speaker
    return {
        "persona": voice.persona,
        "writer_rules": list(voice.rules),
        "soul": voice.soul or DEFAULT_SOUL[speaker],
        "opinions": list(voice.opinions or DEFAULT_OPINIONS[speaker]),
        "stance": voice.stance or DEFAULT_STANCE[speaker],
    }
