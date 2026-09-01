"""Write a reviewed source packet, lock, and tweet image from one fetched tweet."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from runtime_flight.source import STAGED_BINDING, _canonical_packet_digest
from runtime_flight.tweet_fetch import (
    FetchedTweet,
    HttpGet,
    TweetFetchError,
    default_http_get,
    fetch_tweet,
    fetched_tweet_from_dict,
)
from runtime_flight.tweet_image import TweetImageError, render_tweet_card

PACKET_NAME = "source_packet.local.json"
LOCK_NAME = "source_packet.lock.json"
EXCERPT_NAME = "excerpt.txt"
IMAGE_NAME = "tweet.png"
CARD_NAME = "card.json"
FETCH_NAME = "fetch.json"
MAX_MEDIA_BYTES = 2_000_000


class IngestError(Exception):
    """Raised when a tweet cannot be staged into a reviewed source directory."""


def ingest_tweet(
    raw_url: str,
    dest_dir: Path,
    *,
    http_get: HttpGet | None = None,
    fixture: dict[str, Any] | None = None,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    getter = http_get or default_http_get
    try:
        fetched = (
            fetched_tweet_from_dict(fixture, fallback_url=raw_url)
            if fixture is not None
            else fetch_tweet(raw_url, http_get=getter)
        )
    except TweetFetchError as error:
        raise IngestError(str(error)) from error

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    media_path = _download_media(fetched, dest, getter)
    try:
        image_bytes = render_tweet_card(
            author=fetched.author,
            text=fetched.text,
            media_path=media_path,
        )
    except TweetImageError as error:
        raise IngestError(str(error)) from error
    image_path = dest / IMAGE_NAME
    image_path.write_bytes(image_bytes)

    linked = _linked_source(fetched)
    excerpt_path = dest / EXCERPT_NAME
    excerpt_path.write_text(linked["excerpt"], encoding="utf-8")
    packet = {
        "tweet": {
            "id": fetched.id,
            "author": fetched.author,
            "text": fetched.text,
            "url": fetched.url,
        },
        "linked_source": {
            "title": linked["title"],
            "subtitle": linked["subtitle"],
            "url": linked["url"],
            "excerpt_path": EXCERPT_NAME,
        },
        "reviewed": True,
    }
    stamp = reviewed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    excerpt_bytes = excerpt_path.read_bytes()
    lock = {
        "binding": STAGED_BINDING,
        "tweet_id": fetched.id,
        "tweet_author": fetched.author,
        "tweet_url": fetched.url,
        "source_packet_sha256": _canonical_packet_digest(packet),
        "tweet_text_sha256": hashlib.sha256(fetched.text.encode("utf-8")).hexdigest(),
        "excerpt_sha256": hashlib.sha256(excerpt_bytes).hexdigest(),
        "reviewed_at": stamp,
    }
    packet_path = dest / PACKET_NAME
    lock_path = dest / LOCK_NAME
    packet_path.write_text(
        json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lock_path.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    card = producer_card_payload(
        author=fetched.author,
        text=fetched.text,
        url=fetched.url,
        image_url=f"/{IMAGE_NAME}",
        photo_url="/media.png" if media_path is not None else "",
        chyron=_standby_chyron(fetched.text),
    )
    (dest / CARD_NAME).write_text(
        json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (dest / FETCH_NAME).write_text(
        json.dumps(
            {
                "id": fetched.id,
                "author": fetched.author,
                "author_name": fetched.author_name,
                "url": fetched.url,
                "media_count": len(fetched.media_urls),
                "linked_urls": list(fetched.linked_urls),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "source_dir": dest,
        "packet_path": packet_path,
        "lock_path": lock_path,
        "excerpt_path": excerpt_path,
        "image_path": image_path,
        "media_path": media_path,
        "card": card,
        "fetched": fetched,
    }


def producer_card_payload(
    *,
    author: str,
    text: str,
    url: str = "",
    chyron: str = "",
    ticker: list[str] | None = None,
    image_url: str = f"/{IMAGE_NAME}",
    photo_url: str = "",
    speaker: str = "a",
    seg: str = "",
    timestamp: str = "",
) -> dict[str, Any]:
    items = [item for item in (ticker or []) if isinstance(item, str) and item]
    return {
        "author": author,
        "text": text,
        "url": url,
        "timestamp": timestamp,
        "chyron": chyron,
        "ticker": items[:6],
        "image_url": image_url,
        "photo_url": photo_url if photo_url.startswith("/") else "",
        "speaker": speaker if speaker in {"a", "b"} else "a",
        "seg": seg,
    }


def _linked_source(fetched: FetchedTweet) -> dict[str, str]:
    if fetched.linked_urls:
        url = fetched.linked_urls[0]
        host = urlparse(url).hostname or "linked source"
        return {
            "title": host,
            "subtitle": "Linked from the source tweet",
            "url": url,
            "excerpt": fetched.text,
        }
    return {
        "title": fetched.author_name or fetched.author,
        "subtitle": "Source tweet",
        "url": fetched.url,
        "excerpt": fetched.text,
    }


def _download_media(
    fetched: FetchedTweet, dest: Path, http_get: HttpGet
) -> Path | None:
    if not fetched.media_urls:
        return None
    url = fetched.media_urls[0]
    try:
        status, body, content_type = http_get(
            url, headers={"Accept": "image/*"}, max_bytes=MAX_MEDIA_BYTES
        )
    except TypeError:
        status, body, content_type = http_get(url, headers={"Accept": "image/*"})
    except TweetFetchError:
        return None
    if status != 200 or not body:
        return None
    suffix = ".jpg"
    lowered = content_type.lower()
    if "png" in lowered:
        suffix = ".png"
    elif "webp" in lowered:
        suffix = ".webp"
    elif "gif" in lowered:
        suffix = ".gif"
    path = dest / f"media{suffix}"
    if len(body) > MAX_MEDIA_BYTES:
        return None
    path.write_bytes(body)
    return path


def _standby_chyron(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= 100:
        return compact
    return compact[:99].rstrip() + "…"
