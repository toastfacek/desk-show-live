"""Load and validate the operator-reviewed one-tweet source packet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from runtime_flight.models import (
    MAX_EXCERPT_BYTES,
    MAX_TWEET_CHARS,
    LinkedSource,
    SourcePacket,
    Tweet,
)

EXPECTED_TWEET_ID = "2093833419377815719"
EXPECTED_AUTHOR = "dwarkesh_sp"
EXPECTED_TWEET_URL = "https://x.com/dwarkesh_sp/status/2093833419377815719"
EXPECTED_LINKED_URL = "https://www.dwarkesh.com/p/openai-huggingface"


class SourceError(Exception):
    """Raised when the reviewed source packet cannot be loaded."""


def load_source_packet(packet_path: Path, lock_path: Path) -> SourcePacket:
    packet_root = packet_path.parent
    packet_bytes = _read_contained_source_file(packet_path, packet_root, "source packet")
    lock_bytes = _read_contained_source_file(lock_path, packet_root, "source lock")

    try:
        packet = json.loads(packet_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise SourceError("source packet is not valid UTF-8") from error
    except json.JSONDecodeError as error:
        raise SourceError("source packet is not valid JSON") from error
    if not isinstance(packet, dict):
        raise SourceError("source packet must be a JSON object")
    if packet.get("reviewed") is not True:
        raise SourceError("source packet is not reviewed")

    tweet_raw = packet.get("tweet")
    if not isinstance(tweet_raw, dict):
        raise SourceError("source packet tweet text is missing")
    tweet_text = tweet_raw.get("text")
    if tweet_text is None or not isinstance(tweet_text, str) or tweet_text == "":
        raise SourceError("source packet tweet text is missing")
    if len(tweet_text) > MAX_TWEET_CHARS:
        raise SourceError("tweet text exceeds 2000 characters")

    tweet_id = tweet_raw.get("id")
    tweet_author = tweet_raw.get("author")
    tweet_url = tweet_raw.get("url")
    if tweet_id != EXPECTED_TWEET_ID:
        raise SourceError("tweet id does not match the reviewed source")
    if tweet_author != EXPECTED_AUTHOR:
        raise SourceError("tweet author does not match the reviewed source")
    if tweet_url != EXPECTED_TWEET_URL:
        raise SourceError("tweet url does not match the reviewed source")

    linked_raw = packet.get("linked_source")
    if not isinstance(linked_raw, dict):
        raise SourceError("source packet excerpt_path is missing")
    excerpt_rel = linked_raw.get("excerpt_path")
    if not isinstance(excerpt_rel, str) or excerpt_rel == "":
        raise SourceError("source packet excerpt_path is missing")
    linked_url = linked_raw.get("url")
    if linked_url != EXPECTED_LINKED_URL:
        raise SourceError("linked source url does not match the reviewed source")
    title = linked_raw.get("title")
    subtitle = linked_raw.get("subtitle")
    if not isinstance(title, str) or title == "":
        raise SourceError("linked source title is missing")
    if not isinstance(subtitle, str) or subtitle == "":
        raise SourceError("linked source subtitle is missing")

    excerpt_path = packet_path.parent / excerpt_rel
    excerpt_bytes = _read_contained_source_file(excerpt_path, packet_root, "excerpt")
    try:
        excerpt_text = excerpt_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceError("excerpt is not valid UTF-8") from error

    try:
        lock = json.loads(lock_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise SourceError("source lock is not valid UTF-8") from error
    except json.JSONDecodeError as error:
        raise SourceError("source lock is not valid JSON") from error
    if not isinstance(lock, dict):
        raise SourceError("source lock must be a JSON object")
    reviewed_at = lock.get("reviewed_at")
    if not isinstance(reviewed_at, str) or not reviewed_at:
        raise SourceError("source lock missing reviewed_at")

    actual = {
        "source_packet_sha256": _canonical_packet_digest(packet),
        "tweet_text_sha256": hashlib.sha256(tweet_text.encode("utf-8")).hexdigest(),
        "excerpt_sha256": hashlib.sha256(excerpt_bytes).hexdigest(),
    }
    for key, digest in actual.items():
        if lock.get(key) != digest:
            raise SourceError(f"{key} mismatch")

    try:
        tweet = Tweet(
            id=tweet_id,
            author=tweet_author,
            text=tweet_text,
            url=tweet_url,
        )
        linked = LinkedSource(
            title=title,
            subtitle=subtitle,
            url=linked_url,
            excerpt=excerpt_text,
            excerpt_sha256=actual["excerpt_sha256"],
        )
        return SourcePacket(
            tweet=tweet,
            linked_source=linked,
            packet_sha256=actual["source_packet_sha256"],
            reviewed_at=reviewed_at,
        )
    except ValueError as error:
        raise SourceError(str(error)) from error


def _canonical_packet_digest(packet: dict[str, Any]) -> str:
    canonical = json.dumps(
        packet,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _read_contained_source_file(path: Path, parent: Path, label: str) -> bytes:
    if path.is_symlink():
        raise SourceError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as error:
        raise SourceError(f"{label} not found") from error
    parent_resolved = parent.resolve()
    if not resolved.is_relative_to(parent_resolved):
        raise SourceError(f"{label} path escape")
    if resolved.is_symlink() or not resolved.is_file():
        raise SourceError(f"{label} must be a regular file")
    size = resolved.stat().st_size
    if size == 0:
        raise SourceError(f"{label} is empty")
    if size > MAX_EXCERPT_BYTES:
        raise SourceError(f"{label} exceeds 1 MiB")
    data = resolved.read_bytes()
    if not data:
        raise SourceError(f"{label} is empty")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceError(f"{label} is not valid UTF-8") from error
    return data
