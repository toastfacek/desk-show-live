"""Load a Twitter list into the inbox. Ingest only; producers dissect later."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from runtime_flight.content_queue import (
    PENDING,
    _append_manifest,
    ensure_inbox,
    has_item,
)
from runtime_flight.ingest import IngestError, ingest_tweet
from runtime_flight.tweet_fetch import HttpGet
from runtime_flight.tweet_list import (
    ListPage,
    TweetListError,
    TwitterListRef,
    bearer_token,
    fetch_list_page,
    load_list_file,
    parse_list_url,
)
from runtime_flight.tweet_url import TweetRef

CURSOR_NAME = "list_cursor.json"


def load_list(
    inbox: Path,
    *,
    list_url: str | None = None,
    list_file: Path | None = None,
    bearer: str | None = None,
    http_get: HttpGet | None = None,
    fixtures: dict[str, dict[str, Any]] | None = None,
    max_pages: int = 1,
) -> dict[str, Any]:
    inbox = ensure_inbox(inbox)
    if list_file is not None:
        ref, tweets = load_list_file(list_file)
        added = _ingest_refs(inbox, tweets, http_get=http_get, fixtures=fixtures)
        _write_cursor(inbox, ref, next_token=None, exhausted=True)
        return {
            "inbox": str(inbox),
            "list_id": ref.list_id,
            "list_url": ref.url,
            "enqueued": added,
            "next_token": None,
            "exhausted": True,
        }
    if not list_url:
        raise TweetListError("load-list needs --list or --list-file")
    ref = parse_list_url(list_url)
    token = bearer if bearer is not None else bearer_token()
    added: list[str] = []
    next_token = _read_cursor_token(inbox, ref.list_id)
    exhausted = False
    for _ in range(max(max_pages, 1)):
        page = fetch_list_page(
            ref.list_id,
            bearer=token,
            pagination_token=next_token,
            http_get=http_get,
        )
        added.extend(_ingest_refs(inbox, page.tweets, http_get=http_get, fixtures=fixtures))
        next_token = page.next_token
        if next_token is None:
            exhausted = True
            break
    _write_cursor(inbox, ref, next_token=next_token, exhausted=exhausted)
    return {
        "inbox": str(inbox),
        "list_id": ref.list_id,
        "list_url": ref.url,
        "enqueued": added,
        "next_token": next_token,
        "exhausted": exhausted,
    }


def pull_next_page(
    inbox: Path,
    *,
    bearer: str | None = None,
    http_get: HttpGet | None = None,
    fixtures: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    inbox = ensure_inbox(inbox)
    cursor = _cursor_payload(inbox)
    if cursor.get("exhausted"):
        return []
    list_id = str(cursor.get("list_id") or "")
    if not list_id.isdigit():
        return []
    token = bearer if bearer is not None else bearer_token()
    page: ListPage = fetch_list_page(
        list_id,
        bearer=token,
        pagination_token=cursor.get("next_token") if isinstance(cursor.get("next_token"), str) else None,
        http_get=http_get,
    )
    added = _ingest_refs(inbox, page.tweets, http_get=http_get, fixtures=fixtures)
    _write_cursor(
        inbox,
        TwitterListRef(list_id=list_id, url=f"https://x.com/i/lists/{list_id}"),
        next_token=page.next_token,
        exhausted=page.next_token is None,
    )
    return added


def _ingest_refs(
    inbox: Path,
    tweets: tuple[TweetRef, ...] | list[TweetRef],
    *,
    http_get: HttpGet | None,
    fixtures: dict[str, dict[str, Any]] | None,
) -> list[str]:
    added: list[str] = []
    for tweet in tweets:
        if has_item(inbox, tweet.id):
            continue
        dest = inbox / PENDING / tweet.id
        fixture = None
        if fixtures is not None:
            fixture = fixtures.get(tweet.url) or fixtures.get(tweet.id)
        try:
            ingest_tweet(tweet.url, dest, http_get=http_get, fixture=fixture)
        except IngestError:
            if dest.exists():
                shutil.rmtree(dest)
            continue
        _append_manifest(inbox, tweet.id)
        added.append(tweet.id)
    return added


def _write_cursor(
    inbox: Path,
    ref: TwitterListRef,
    *,
    next_token: str | None,
    exhausted: bool,
) -> None:
    payload = {
        "list_id": ref.list_id,
        "list_url": ref.url,
        "next_token": next_token,
        "exhausted": exhausted,
    }
    (Path(inbox) / CURSOR_NAME).write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def _cursor_payload(inbox: Path) -> dict[str, Any]:
    path = Path(inbox) / CURSOR_NAME
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _read_cursor_token(inbox: Path, list_id: str) -> str | None:
    cursor = _cursor_payload(inbox)
    if cursor.get("list_id") != list_id:
        return None
    token = cursor.get("next_token")
    return token if isinstance(token, str) and token else None
