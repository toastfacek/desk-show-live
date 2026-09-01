"""Immutable, bounded models for the one-tweet live flight."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MAX_TWEET_CHARS = 2000
MAX_EXCERPT_BYTES = 1024 * 1024
MAX_QUESTION_CHARS = 280
MAX_FRAMING_CHARS = 1000
MAX_CHYRON_CHARS = 100
MAX_FACT_CHARS = 500
MIN_LIST_ITEMS = 1
MAX_LIST_ITEMS = 8
MIN_BEATS = 1
MAX_BEATS = 4
MAX_BEAT_CHARS = 280


def _require_str(value: object, label: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{label} must be a non-empty string")
    return value


@dataclass(frozen=True)
class Tweet:
    id: str
    author: str
    text: str
    url: str

    def __post_init__(self) -> None:
        _require_str(self.id, "tweet id")
        _require_str(self.author, "tweet author")
        _require_str(self.text, "tweet text")
        _require_str(self.url, "tweet url")
        if len(self.text) > MAX_TWEET_CHARS:
            raise ValueError("tweet text exceeds 2000 characters")


@dataclass(frozen=True)
class LinkedSource:
    title: str
    subtitle: str
    url: str
    excerpt: str
    excerpt_sha256: str

    def __post_init__(self) -> None:
        _require_str(self.title, "linked source title")
        _require_str(self.subtitle, "linked source subtitle")
        _require_str(self.url, "linked source url")
        _require_str(self.excerpt, "excerpt")
        _require_str(self.excerpt_sha256, "excerpt_sha256")
        if len(self.excerpt.encode("utf-8")) > MAX_EXCERPT_BYTES:
            raise ValueError("excerpt exceeds 1 MiB")


@dataclass(frozen=True)
class SourcePacket:
    tweet: Tweet
    linked_source: LinkedSource
    packet_sha256: str
    reviewed_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.tweet, Tweet):
            raise ValueError("tweet must be a Tweet")
        if not isinstance(self.linked_source, LinkedSource):
            raise ValueError("linked_source must be a LinkedSource")
        _require_str(self.packet_sha256, "packet_sha256")
        _require_str(self.reviewed_at, "reviewed_at")


@dataclass(frozen=True)
class TweetCard:
    author: str
    text: str
    url: str

    def __post_init__(self) -> None:
        _require_str(self.author, "card author")
        _require_str(self.text, "card text")
        _require_str(self.url, "card url")


@dataclass(frozen=True)
class Fact:
    id: str
    text: str
    source_url: str

    def __post_init__(self) -> None:
        _require_str(self.id, "fact id")
        _require_str(self.text, "fact text")
        _require_str(self.source_url, "fact source_url")
        if len(self.text) > MAX_FACT_CHARS:
            raise ValueError("fact text exceeds 500 characters")


@dataclass(frozen=True)
class Beat:
    id: str
    question: str
    tension: str
    bot1_job: str
    bot2_job: str
    fact_ids: tuple[str, ...]
    done_when: str

    def __post_init__(self) -> None:
        _require_str(self.id, "beat id")
        _require_str(self.question, "beat question")
        _require_str(self.tension, "beat tension")
        _require_str(self.bot1_job, "beat bot1_job")
        _require_str(self.bot2_job, "beat bot2_job")
        _require_str(self.done_when, "beat done_when")
        if len(self.question) > MAX_BEAT_CHARS:
            raise ValueError("beat question exceeds 280 characters")
        if len(self.tension) > MAX_BEAT_CHARS:
            raise ValueError("beat tension exceeds 280 characters")
        if len(self.bot1_job) > MAX_BEAT_CHARS:
            raise ValueError("beat bot1_job exceeds 280 characters")
        if len(self.bot2_job) > MAX_BEAT_CHARS:
            raise ValueError("beat bot2_job exceeds 280 characters")
        if len(self.done_when) > MAX_BEAT_CHARS:
            raise ValueError("beat done_when exceeds 280 characters")
        if not isinstance(self.fact_ids, tuple) or not self.fact_ids:
            raise ValueError("beat fact_ids must be a non-empty tuple")
        for index, fact_id in enumerate(self.fact_ids):
            _require_str(fact_id, f"beat fact_ids[{index}]")


@dataclass(frozen=True)
class TopicMap:
    throughline: str
    fight: str
    beats: tuple[Beat, ...]
    done_when: str

    def __post_init__(self) -> None:
        _require_str(self.throughline, "topic_map throughline")
        _require_str(self.fight, "topic_map fight")
        _require_str(self.done_when, "topic_map done_when")
        if len(self.throughline) > MAX_BEAT_CHARS:
            raise ValueError("topic_map throughline exceeds 280 characters")
        if len(self.fight) > MAX_BEAT_CHARS:
            raise ValueError("topic_map fight exceeds 280 characters")
        if len(self.done_when) > MAX_BEAT_CHARS:
            raise ValueError("topic_map done_when exceeds 280 characters")
        if not isinstance(self.beats, tuple) or not (
            MIN_BEATS <= len(self.beats) <= MAX_BEATS
        ):
            raise ValueError("topic_map beats must contain 1 to 4 entries")
        if not all(isinstance(beat, Beat) for beat in self.beats):
            raise ValueError("topic_map beats must be Beat values")
        ids = [beat.id for beat in self.beats]
        if len(ids) != len(set(ids)):
            raise ValueError("topic_map beat ids must be unique")


@dataclass(frozen=True)
class HostVoice:
    speaker: Literal["BOT1", "BOT2"]
    persona: str
    rules: tuple[str, ...]
    soul: str = ""
    opinions: tuple[str, ...] = ()
    stance: str = ""

    def __post_init__(self) -> None:
        if self.speaker not in {"BOT1", "BOT2"}:
            raise ValueError("host voice speaker must be BOT1 or BOT2")
        _require_str(self.persona, "host persona")
        if not isinstance(self.rules, tuple):
            raise ValueError("host rules must be a tuple")
        for index, rule in enumerate(self.rules):
            _require_str(rule, f"host rules[{index}]")
        if not isinstance(self.soul, str):
            raise ValueError("host soul must be a string")
        if not isinstance(self.opinions, tuple):
            raise ValueError("host opinions must be a tuple")
        for index, opinion in enumerate(self.opinions):
            _require_str(opinion, f"host opinions[{index}]")
        if not isinstance(self.stance, str):
            raise ValueError("host stance must be a string")


@dataclass(frozen=True)
class CoverageState:
    beat_index: int
    bot1_landed: frozenset[str]
    bot2_landed: frozenset[str]
    bot1_exhausted: frozenset[str]
    bot2_exhausted: frozenset[str]
    exchanges_on_beat: int
    map_complete: bool
    stop_reason: str

    @staticmethod
    def initial() -> CoverageState:
        return CoverageState(
            beat_index=0,
            bot1_landed=frozenset(),
            bot2_landed=frozenset(),
            bot1_exhausted=frozenset(),
            bot2_exhausted=frozenset(),
            exchanges_on_beat=0,
            map_complete=False,
            stop_reason="",
        )

    def __post_init__(self) -> None:
        if self.beat_index < 0:
            raise ValueError("beat_index must be >= 0")
        if self.exchanges_on_beat < 0:
            raise ValueError("exchanges_on_beat must be >= 0")
        if not isinstance(self.map_complete, bool):
            raise ValueError("map_complete must be a boolean")
        if not isinstance(self.stop_reason, str):
            raise ValueError("stop_reason must be a string")


@dataclass(frozen=True)
class SegmentPackage:
    item_id: str
    question: str
    framing: str
    angles: tuple[str, ...]
    facts: tuple[Fact, ...]
    chyron: str
    chyron_fact_ids: tuple[str, ...]
    center: TweetCard
    topic_map: TopicMap | None = None

    def __post_init__(self) -> None:
        _require_str(self.item_id, "item_id")
        _require_str(self.question, "question")
        _require_str(self.framing, "framing")
        _require_str(self.chyron, "chyron")
        if len(self.question) > MAX_QUESTION_CHARS:
            raise ValueError("question exceeds 280 characters")
        if len(self.framing) > MAX_FRAMING_CHARS:
            raise ValueError("framing exceeds 1000 characters")
        if len(self.chyron) > MAX_CHYRON_CHARS:
            raise ValueError("chyron exceeds 100 characters")
        if not isinstance(self.angles, tuple) or not (
            MIN_LIST_ITEMS <= len(self.angles) <= MAX_LIST_ITEMS
        ):
            raise ValueError("angles must contain 1 to 8 entries")
        for index, angle in enumerate(self.angles):
            _require_str(angle, f"angles[{index}]")
        if not isinstance(self.facts, tuple) or not (
            MIN_LIST_ITEMS <= len(self.facts) <= MAX_LIST_ITEMS
        ):
            raise ValueError("facts must contain 1 to 8 entries")
        if not all(isinstance(fact, Fact) for fact in self.facts):
            raise ValueError("facts must be Fact values")
        if not isinstance(self.chyron_fact_ids, tuple) or not self.chyron_fact_ids:
            raise ValueError("chyron_fact_ids must be a non-empty tuple")
        fact_ids = {fact.id for fact in self.facts}
        for fact_id in self.chyron_fact_ids:
            _require_str(fact_id, "chyron_fact_id")
            if fact_id not in fact_ids:
                raise ValueError("chyron_fact_id does not reference a returned fact")
        if not isinstance(self.center, TweetCard):
            raise ValueError("center must be a TweetCard")
        if self.topic_map is not None and not isinstance(self.topic_map, TopicMap):
            raise ValueError("topic_map must be a TopicMap")
        if self.topic_map is not None:
            fact_ids = {fact.id for fact in self.facts}
            for beat in self.topic_map.beats:
                for fact_id in beat.fact_ids:
                    if fact_id not in fact_ids:
                        raise ValueError("beat fact_id does not reference a returned fact")


@dataclass(frozen=True)
class Thought:
    speaker: Literal["BOT1", "BOT2"]
    text: str
    thought_open: bool
    angle_used: str
    beat_id: str | None = None
    landed_own_job: bool = False
    beat_exhausted: bool = False

    def __post_init__(self) -> None:
        if self.speaker not in {"BOT1", "BOT2"}:
            raise ValueError("speaker must be BOT1 or BOT2")
        _require_str(self.text, "thought text")
        if not isinstance(self.thought_open, bool):
            raise ValueError("thought_open must be a boolean")
        _require_str(self.angle_used, "angle_used")
        if self.beat_id is not None:
            _require_str(self.beat_id, "beat_id")
        if not isinstance(self.landed_own_job, bool):
            raise ValueError("landed_own_job must be a boolean")
        if not isinstance(self.beat_exhausted, bool):
            raise ValueError("beat_exhausted must be a boolean")
