"""Chat picker. Fake text client. No fal, no writer import."""

from __future__ import annotations

import ast
import json as json_module
from pathlib import Path

import pytest

from runtime_flight.chat_pick import (
    ChatComment,
    ChatPickError,
    load_chat_file,
    pick_chat,
)
from runtime_flight.text_client import TextAttemptLimiter, TextClient

FORBIDDEN = {"writer", "fal_client", "harness_live", "obs_session"}


class FakeResponse:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> object:
        return self._body


def _client(body: object) -> TextClient:
    async def http_post(url, *, headers, json, timeout):
        del url, headers, json, timeout
        return FakeResponse(
            200,
            {"choices": [{"message": {"content": json_module.dumps(body)}}]},
        )

    return TextClient(
        base_url="https://text.example/v1",
        api_key="k",
        model="m",
        limiter=TextAttemptLimiter(4),
        http_post=http_post,
    )


def test_load_chat_file(tmp_path: Path) -> None:
    path = tmp_path / "chat.json"
    path.write_text(
        json_module.dumps(
            {
                "comments": [
                    {"id": "c1", "author": "sam", "text": "Who actually posted this?"},
                    {"id": "c2", "author": "lee", "text": "lol"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    comments = load_chat_file(path)
    assert comments[0].id == "c1"
    assert comments[0].text == "Who actually posted this?"


@pytest.mark.asyncio
async def test_pick_chat_keeps_supplied_text() -> None:
    comments = (
        ChatComment("c1", "sam", "Who actually posted this?"),
        ChatComment("c2", "lee", "lol"),
    )
    picks = await pick_chat(
        comments,
        client=_client(
            {"picks": [{"comment_id": "c1", "why": "asks who wrote it"}]}
        ),
        question="What does this unlock?",
    )
    assert picks[0].comment_id == "c1"
    assert picks[0].text == "Who actually posted this?"
    assert picks[0].why == "asks who wrote it"


@pytest.mark.asyncio
async def test_pick_chat_rejects_invented_id() -> None:
    comments = (ChatComment("c1", "sam", "Who actually posted this?"),)
    with pytest.raises(ChatPickError, match="supplied"):
        await pick_chat(
            comments,
            client=_client(
                {"picks": [{"comment_id": "nope", "why": "invented"}]}
            ),
        )


def test_picker_stays_isolated() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "chat_pick.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN)
    assert "from runtime_flight.writer" not in source
    assert "deb" not in source
    assert "PHASEONE" not in source
