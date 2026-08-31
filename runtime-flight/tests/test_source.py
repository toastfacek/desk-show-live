"""Task 6: typed source packet loader. No network."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from runtime_flight.models import LinkedSource, SourcePacket, Thought, Tweet
from runtime_flight.source import (
    EXPECTED_AUTHOR,
    EXPECTED_LINKED_URL,
    EXPECTED_TWEET_ID,
    EXPECTED_TWEET_URL,
    SourceError,
    load_source_packet,
)

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}

TWEET_TEXT = "Hello café\nworld"
EXCERPT_TEXT = "Reviewed excerpt body.\n"
PACKET_NAME = "source_packet.local.json"
LOCK_NAME = "source_packet.lock.json"
EXCERPT_NAME = "dwarkesh-agent-civilizations.txt"
EXAMPLE_PACKET = (
    Path(__file__).resolve().parents[1] / "inputs" / "source_packet.example.json"
)


def _canonical_packet_digest(packet: dict) -> str:
    canonical = json.dumps(
        packet,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _packet_payload(**overrides) -> dict:
    payload = {
        "tweet": {
            "id": EXPECTED_TWEET_ID,
            "author": EXPECTED_AUTHOR,
            "text": TWEET_TEXT,
            "url": EXPECTED_TWEET_URL,
        },
        "linked_source": {
            "title": "The Rise and Fall of Agent Civilizations",
            "subtitle": "The whole OpenAI/Hugging Face story in plain English",
            "url": EXPECTED_LINKED_URL,
            "excerpt_path": EXCERPT_NAME,
        },
        "reviewed": True,
    }
    payload.update(overrides)
    return payload


def _write_source_files(
    inputs_dir: Path,
    *,
    packet: dict | None = None,
    excerpt: str | bytes = EXCERPT_TEXT,
) -> dict:
    inputs_dir.mkdir(parents=True, exist_ok=True)
    payload = packet if packet is not None else _packet_payload()
    packet_path = inputs_dir / PACKET_NAME
    excerpt_path = inputs_dir / EXCERPT_NAME
    lock_path = inputs_dir / LOCK_NAME
    packet_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if isinstance(excerpt, bytes):
        excerpt_path.write_bytes(excerpt)
        excerpt_bytes = excerpt
    else:
        excerpt_path.write_text(excerpt, encoding="utf-8")
        excerpt_bytes = excerpt_path.read_bytes()
    tweet_text = payload.get("tweet", {}).get("text") if isinstance(payload.get("tweet"), dict) else ""
    if not isinstance(tweet_text, str):
        tweet_text = ""
    lock = {
        "source_packet_sha256": _canonical_packet_digest(payload),
        "tweet_text_sha256": hashlib.sha256(tweet_text.encode("utf-8")).hexdigest(),
        "excerpt_sha256": hashlib.sha256(excerpt_bytes).hexdigest(),
        "reviewed_at": "2026-08-31T00:00:00+00:00",
    }
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return {
        "packet": packet_path,
        "lock": lock_path,
        "excerpt": excerpt_path,
        "lock_data": lock,
        "payload": payload,
    }


def test_load_source_packet_returns_reviewed_typed_packet(tmp_path: Path):
    written = _write_source_files(tmp_path / "inputs")
    source = load_source_packet(written["packet"], written["lock"])
    assert isinstance(source, SourcePacket)
    assert source.tweet == Tweet(
        id=EXPECTED_TWEET_ID,
        author=EXPECTED_AUTHOR,
        text=TWEET_TEXT,
        url=EXPECTED_TWEET_URL,
    )
    assert source.linked_source == LinkedSource(
        title="The Rise and Fall of Agent Civilizations",
        subtitle="The whole OpenAI/Hugging Face story in plain English",
        url=EXPECTED_LINKED_URL,
        excerpt=EXCERPT_TEXT,
        excerpt_sha256=written["lock_data"]["excerpt_sha256"],
    )
    assert source.packet_sha256 == written["lock_data"]["source_packet_sha256"]
    assert source.reviewed_at == "2026-08-31T00:00:00+00:00"
    with pytest.raises(FrozenInstanceError):
        source.tweet.text = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize("text", [None, ""])
def test_source_rejects_null_or_blank_tweet_text(tmp_path: Path, text):
    packet = _packet_payload()
    packet["tweet"]["text"] = text
    written = _write_source_files(tmp_path / "inputs", packet=packet)
    with pytest.raises(SourceError, match="text"):
        load_source_packet(written["packet"], written["lock"])


def test_source_rejects_unreviewed_packet(tmp_path: Path):
    packet = _packet_payload(reviewed=False)
    written = _write_source_files(tmp_path / "inputs", packet=packet)
    with pytest.raises(SourceError, match="reviewed"):
        load_source_packet(written["packet"], written["lock"])


def test_source_rejects_wrong_tweet_id(tmp_path: Path):
    packet = _packet_payload()
    packet["tweet"]["id"] = "0000000000000000000"
    written = _write_source_files(tmp_path / "inputs", packet=packet)
    with pytest.raises(SourceError, match="id"):
        load_source_packet(written["packet"], written["lock"])


def test_source_rejects_wrong_tweet_url(tmp_path: Path):
    packet = _packet_payload()
    packet["tweet"]["url"] = "https://x.com/other/status/2093833419377815719"
    written = _write_source_files(tmp_path / "inputs", packet=packet)
    with pytest.raises(SourceError, match="url"):
        load_source_packet(written["packet"], written["lock"])


def test_source_rejects_wrong_author(tmp_path: Path):
    packet = _packet_payload()
    packet["tweet"]["author"] = "not_dwarkesh"
    written = _write_source_files(tmp_path / "inputs", packet=packet)
    with pytest.raises(SourceError, match="author"):
        load_source_packet(written["packet"], written["lock"])


def test_source_rejects_wrong_linked_url(tmp_path: Path):
    packet = _packet_payload()
    packet["linked_source"]["url"] = "https://example.invalid/article"
    written = _write_source_files(tmp_path / "inputs", packet=packet)
    with pytest.raises(SourceError, match="url"):
        load_source_packet(written["packet"], written["lock"])


def test_source_rejects_path_escape(tmp_path: Path):
    inputs = tmp_path / "inputs"
    packet = _packet_payload()
    packet["linked_source"]["excerpt_path"] = "../outside.txt"
    (tmp_path / "outside.txt").write_text("escaped", encoding="utf-8")
    written = _write_source_files(inputs, packet=packet)
    with pytest.raises(SourceError, match="escape|excerpt"):
        load_source_packet(written["packet"], written["lock"])


def test_source_rejects_symlink_packet(tmp_path: Path):
    inputs = tmp_path / "inputs"
    written = _write_source_files(inputs)
    link = inputs / "linked_packet.json"
    link.symlink_to(written["packet"])
    with pytest.raises(SourceError, match="symlink"):
        load_source_packet(link, written["lock"])


def test_source_rejects_invalid_utf8(tmp_path: Path):
    inputs = tmp_path / "inputs"
    written = _write_source_files(inputs)
    written["packet"].write_bytes(b'{"reviewed": true, "tweet": "\xff"}')
    with pytest.raises(SourceError, match="UTF-8"):
        load_source_packet(written["packet"], written["lock"])


def test_source_rejects_oversized_excerpt(tmp_path: Path):
    written = _write_source_files(
        tmp_path / "inputs",
        excerpt=b"x" * (1024 * 1024 + 1),
    )
    with pytest.raises(SourceError, match="1 MiB|oversized"):
        load_source_packet(written["packet"], written["lock"])


@pytest.mark.parametrize("field", ["source_packet_sha256", "tweet_text_sha256", "excerpt_sha256"])
def test_source_rejects_hash_mismatch(tmp_path: Path, field: str):
    written = _write_source_files(tmp_path / "inputs")
    lock = written["lock_data"]
    lock[field] = "0" * 64
    written["lock"].write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(SourceError, match="mismatch"):
        load_source_packet(written["packet"], written["lock"])


def test_source_rejects_tweet_text_over_2000_characters(tmp_path: Path):
    packet = _packet_payload()
    packet["tweet"]["text"] = "a" * 2001
    written = _write_source_files(tmp_path / "inputs", packet=packet)
    with pytest.raises((SourceError, ValueError), match="2000|text"):
        load_source_packet(written["packet"], written["lock"])


def test_example_source_packet_uses_binding_identity():
    assert EXAMPLE_PACKET.is_file()
    payload = json.loads(EXAMPLE_PACKET.read_text(encoding="utf-8"))
    assert payload["tweet"]["id"] == EXPECTED_TWEET_ID
    assert payload["tweet"]["author"] == EXPECTED_AUTHOR
    assert payload["tweet"]["url"] == EXPECTED_TWEET_URL
    assert payload["linked_source"]["url"] == EXPECTED_LINKED_URL
    assert payload["reviewed"] is True
    assert payload["tweet"]["text"]
    assert payload["linked_source"]["excerpt_path"] == EXCERPT_NAME


def test_thought_requires_bot_speaker():
    thought = Thought(
        speaker="BOT1",
        text="A grounded opening claim.",
        thought_open=True,
        angle_used="scope",
    )
    assert thought.speaker == "BOT1"
    with pytest.raises(ValueError, match="BOT1|BOT2"):
        Thought(
            speaker="HOST",  # type: ignore[arg-type]
            text="nope",
            thought_open=False,
            angle_used="scope",
        )


def test_source_modules_do_not_import_root_scaffold() -> None:
    root = Path(__file__).resolve().parents[1] / "runtime_flight"
    for name in ("source.py", "models.py"):
        path = root / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(FORBIDDEN_ROOT_MODULES)
        assert "fal_client" not in imported
        assert "writer" not in path.read_text(encoding="utf-8")
