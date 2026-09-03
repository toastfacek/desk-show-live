"""Pick interesting chat comments for the solo host. No cook, no writer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime_flight.text_client import TextClient

MAX_COMMENT_CHARS = 280
MAX_PICKS = 3
PICKER_SYSTEM = """You pick chat comments for a solo live host.
Return one JSON object and nothing else. Do not wrap it in markdown fences.
Do not invent comments. Use only supplied comment ids.
Pick comments that ask a real question, add a concrete fact, or poke a hole
in the idea on the desk. Skip spam, plus-ones, emoji-only, insults, and
off-topic noise.
Required keys:
- picks: array of 0 to max_picks objects
Each pick:
- comment_id: one of the supplied ids
- why: short reason the host should hear it
"""


class ChatPickError(Exception):
    """Raised when chat comments cannot be loaded or picked."""


@dataclass(frozen=True)
class ChatComment:
    id: str
    author: str
    text: str


@dataclass(frozen=True)
class ChatPick:
    comment_id: str
    text: str
    why: str


def load_chat_file(path: Path) -> tuple[ChatComment, ...]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ChatPickError("chat file must be a JSON object")
    items = raw.get("comments")
    if not isinstance(items, list) or not items:
        raise ChatPickError("chat file comments must be a non-empty array")
    comments: list[ChatComment] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ChatPickError("chat comment must be an object")
        comment_id = str(item.get("id") or "").strip()
        author = str(item.get("author") or "").strip()
        text = str(item.get("text") or "").strip()
        if not comment_id or not author or not text:
            raise ChatPickError("chat comment is missing id, author, or text")
        if comment_id in seen:
            raise ChatPickError("chat comment ids must be unique")
        if len(text) > MAX_COMMENT_CHARS:
            raise ChatPickError("chat comment exceeds 280 characters")
        seen.add(comment_id)
        comments.append(ChatComment(id=comment_id, author=author, text=text))
    return tuple(comments)


async def pick_chat(
    comments: tuple[ChatComment, ...] | list[ChatComment],
    *,
    client: TextClient,
    max_picks: int = 2,
    question: str = "",
) -> tuple[ChatPick, ...]:
    if max_picks < 1 or max_picks > MAX_PICKS:
        raise ChatPickError("max_picks must be 1 to 3")
    pool = tuple(comments)
    if not pool:
        return ()
    user = {
        "max_picks": max_picks,
        "question": question,
        "comments": [
            {"id": comment.id, "author": comment.author, "text": comment.text}
            for comment in pool
        ],
    }
    raw = await client.complete_json(system=PICKER_SYSTEM, user=user)
    return _picks_from_model(raw, pool, max_picks)


def _picks_from_model(
    raw: Any, comments: tuple[ChatComment, ...], max_picks: int
) -> tuple[ChatPick, ...]:
    if not isinstance(raw, dict):
        raise ChatPickError("chat pick is not an object")
    rows = raw.get("picks")
    if not isinstance(rows, list):
        raise ChatPickError("chat picks must be an array")
    by_id = {comment.id: comment for comment in comments}
    picked: list[ChatPick] = []
    seen: set[str] = set()
    for row in rows[:max_picks]:
        if not isinstance(row, dict):
            raise ChatPickError("chat pick must be an object")
        comment_id = str(row.get("comment_id") or "").strip()
        why = str(row.get("why") or "").strip()
        if comment_id not in by_id:
            raise ChatPickError("chat pick is not a supplied comment")
        if comment_id in seen:
            continue
        if not why:
            raise ChatPickError("chat pick why is missing")
        seen.add(comment_id)
        picked.append(
            ChatPick(comment_id=comment_id, text=by_id[comment_id].text, why=why)
        )
    return tuple(picked)
