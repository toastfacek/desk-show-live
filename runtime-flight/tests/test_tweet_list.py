"""Twitter list URL and API page parsing. Fake HTTP only."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from runtime_flight.tweet_list import (
    TweetListError,
    fetch_list_page,
    load_list_file,
    parse_list_url,
)

FORBIDDEN = {
    "harness_live",
    "obs_session",
    "playhead",
    "writer",
    "run_live",
    "studio",
}


def test_parse_list_url_accepts_x_and_twitter() -> None:
    parsed = parse_list_url("https://x.com/i/lists/1234567890?s=20")
    assert parsed.list_id == "1234567890"
    assert parsed.url == "https://x.com/i/lists/1234567890"
    assert parse_list_url("https://twitter.com/i/lists/1234567890").list_id == "1234567890"
    with pytest.raises(TweetListError):
        parse_list_url("https://x.com/someone/status/1")


def test_fetch_list_page_maps_authors_in_api_order() -> None:
    def http_get(url, *, headers, timeout=None, max_bytes=None):
        del timeout, max_bytes
        assert "Authorization" in headers
        assert "123" in url
        body = {
            "data": [
                {"id": "333", "author_id": "u2", "text": "later"},
                {"id": "111", "author_id": "u1", "text": "earlier"},
            ],
            "includes": {
                "users": [
                    {"id": "u1", "username": "first"},
                    {"id": "u2", "username": "second"},
                ]
            },
            "meta": {"next_token": "page2"},
        }
        return 200, json.dumps(body).encode("utf-8"), "application/json"

    page = fetch_list_page("123", bearer="token", http_get=http_get)
    assert [item.id for item in page.tweets] == ["333", "111"]
    assert page.tweets[0].url == "https://x.com/second/status/333"
    assert page.next_token == "page2"


def test_fetch_list_page_requires_login() -> None:
    with pytest.raises(TweetListError, match="login"):
        fetch_list_page("123", bearer="")


def test_load_list_file_keeps_file_order(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text(
        json.dumps(
            {
                "list_id": "99",
                "tweets": [
                    {"url": "https://x.com/aaa/status/333"},
                    {"url": "https://x.com/bbb/status/111"},
                ],
            }
        ),
        encoding="utf-8",
    )
    ref, tweets = load_list_file(path)
    assert ref.list_id == "99"
    assert [item.id for item in tweets] == ["333", "111"]


def test_tweet_list_module_stays_isolated() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "tweet_list.py"
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
    assert "obs" not in source
