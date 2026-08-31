"""Immutable, bounded models for the one-tweet live flight."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MAX_TWEET_CHARS = 2000
MAX_EXCERPT_BYTES = 1024 * 1024
MAX_QUESTION_CHARS = 280
MAX_FRAMING_CHARS = 500
MAX_CHYRON_CHARS = 100
MAX_FACT_CHARS = 500
MIN_LIST_ITEMS = 1
MAX_LIST_ITEMS = 8


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
class SegmentPackage:
    item_id: str
    question: str
    framing: str
    angles: tuple[str, ...]
    facts: tuple[Fact, ...]
    chyron: str
    chyron_fact_ids: tuple[str, ...]
    center: TweetCard

    def __post_init__(self) -> None:
        _require_str(self.item_id, "item_id")
        _require_str(self.question, "question")
        _require_str(self.framing, "framing")
        _require_str(self.chyron, "chyron")
        if len(self.question) > MAX_QUESTION_CHARS:
            raise ValueError("question exceeds 280 characters")
        if len(self.framing) > MAX_FRAMING_CHARS:
            raise ValueError("framing exceeds 500 characters")
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


@dataclass(frozen=True)
class Thought:
    speaker: Literal["BOT1", "BOT2"]
    text: str
    thought_open: bool
    angle_used: str

    def __post_init__(self) -> None:
        if self.speaker not in {"BOT1", "BOT2"}:
            raise ValueError("speaker must be BOT1 or BOT2")
        _require_str(self.text, "thought text")
        if not isinstance(self.thought_open, bool):
            raise ValueError("thought_open must be a boolean")
        _require_str(self.angle_used, "angle_used")
