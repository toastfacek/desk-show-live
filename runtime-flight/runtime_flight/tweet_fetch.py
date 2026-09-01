"""Fetch one public tweet as operator-reviewed source data. Not a live path."""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from runtime_flight.models import MAX_TWEET_CHARS
from runtime_flight.tweet_url import TweetRef, TweetUrlError, parse_tweet_url

HttpGet = Callable[..., tuple[int, bytes, str]]

MAX_FETCH_BYTES = 1_048_576
FXTWITTER = "https://api.fxtwitter.com"
OEMBED = "https://publish.twitter.com/oembed"
USER_AGENT = "desk-show-live-stage/1.0"


class TweetFetchError(Exception):
    """Raised when a tweet cannot be fetched into a typed record."""


@dataclass(frozen=True)
class FetchedTweet:
    id: str
    author: str
    text: str
    url: str
    author_name: str
    media_urls: tuple[str, ...]
    linked_urls: tuple[str, ...]
    html: str = ""


def fetch_tweet(
    raw_url: str,
    *,
    http_get: HttpGet | None = None,
) -> FetchedTweet:
    try:
        ref = parse_tweet_url(raw_url)
    except TweetUrlError as error:
        raise TweetFetchError(str(error)) from error
    getter = http_get or default_http_get
    try:
        return _from_fxtwitter(ref, getter)
    except TweetFetchError:
        return _from_oembed(ref, getter)


def fetched_tweet_from_dict(raw: dict[str, Any], *, fallback_url: str = "") -> FetchedTweet:
    if not isinstance(raw, dict):
        raise TweetFetchError("tweet fixture must be a JSON object")
    url = str(raw.get("url") or fallback_url)
    try:
        ref = parse_tweet_url(url)
    except TweetUrlError as error:
        raise TweetFetchError(str(error)) from error
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise TweetFetchError("tweet text is missing")
    text = text.strip()
    if len(text) > MAX_TWEET_CHARS:
        raise TweetFetchError("tweet text exceeds 2000 characters")
    author = str(raw.get("author") or ref.author).lstrip("@")
    if not author:
        raise TweetFetchError("tweet author is missing")
    tweet_id = str(raw.get("id") or ref.id)
    if tweet_id != ref.id:
        raise TweetFetchError("tweet id does not match url")
    media = _string_tuple(raw.get("media_urls"))
    linked = _string_tuple(raw.get("linked_urls"))
    author_name = raw.get("author_name")
    if not isinstance(author_name, str) or not author_name.strip():
        author_name = author
    html_raw = raw.get("html")
    if not isinstance(html_raw, str):
        html_raw = ""
    return FetchedTweet(
        id=tweet_id,
        author=author,
        text=text,
        url=ref.url,
        author_name=author_name.strip(),
        media_urls=media,
        linked_urls=linked,
        html=html_raw,
    )


def default_http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float = 8.0,
    max_bytes: int = MAX_FETCH_BYTES,
) -> tuple[int, bytes, str]:
    _assert_public_http(url)
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_s) as response:  # noqa: S310
            status = int(getattr(response, "status", 200))
            content_type = str(response.headers.get("Content-Type") or "")
            body = response.read(max_bytes + 1)
    except HTTPError as error:
        raise TweetFetchError(f"tweet fetch HTTP {error.code}") from error
    except URLError as error:
        raise TweetFetchError("tweet fetch failed") from error
    if len(body) > max_bytes:
        raise TweetFetchError("tweet fetch exceeded size limit")
    return status, body, content_type


def _from_fxtwitter(ref: TweetRef, http_get: HttpGet) -> FetchedTweet:
    url = f"{FXTWITTER}/{ref.author}/status/{ref.id}"
    status, body, _content_type = http_get(url, headers={"Accept": "application/json"})
    if status != 200:
        raise TweetFetchError(f"tweet fetch HTTP {status}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TweetFetchError("tweet fetch is not valid JSON") from error
    tweet = payload.get("tweet") if isinstance(payload, dict) else None
    if not isinstance(tweet, dict):
        raise TweetFetchError("tweet fetch missing tweet")
    text = tweet.get("text")
    if not isinstance(text, str) or not text.strip():
        raise TweetFetchError("tweet text is missing")
    author_raw = tweet.get("author") if isinstance(tweet.get("author"), dict) else {}
    author = str(author_raw.get("screen_name") or ref.author).lstrip("@")
    author_name = str(author_raw.get("name") or author)
    media = _media_from_fxtwitter(tweet.get("media"))
    linked = _linked_from_text(text, ref)
    return FetchedTweet(
        id=ref.id,
        author=author,
        text=text.strip(),
        url=ref.url,
        author_name=author_name,
        media_urls=media,
        linked_urls=linked,
        html="",
    )


def _from_oembed(ref: TweetRef, http_get: HttpGet) -> FetchedTweet:
    url = f"{OEMBED}?url={quote(ref.url, safe='')}&omit_script=1"
    status, body, _content_type = http_get(url, headers={"Accept": "application/json"})
    if status != 200:
        raise TweetFetchError(f"tweet fetch HTTP {status}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TweetFetchError("tweet fetch is not valid JSON") from error
    if not isinstance(payload, dict):
        raise TweetFetchError("tweet fetch is not a JSON object")
    markup = payload.get("html")
    if not isinstance(markup, str) or not markup:
        raise TweetFetchError("tweet text is missing")
    text = _text_from_oembed_html(markup)
    if not text:
        raise TweetFetchError("tweet text is missing")
    if len(text) > MAX_TWEET_CHARS:
        raise TweetFetchError("tweet text exceeds 2000 characters")
    author_url = payload.get("author_url")
    author = ref.author
    if isinstance(author_url, str):
        try:
            author = parse_tweet_url(
                author_url.rstrip("/") + f"/status/{ref.id}"
            ).author
        except TweetUrlError:
            handle = author_url.rstrip("/").rsplit("/", 1)[-1]
            if re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle or ""):
                author = handle
    author_name = payload.get("author_name")
    if not isinstance(author_name, str) or not author_name.strip():
        author_name = author
    return FetchedTweet(
        id=ref.id,
        author=author,
        text=text,
        url=ref.url,
        author_name=author_name.strip(),
        media_urls=(),
        linked_urls=_linked_from_text(text, ref),
        html=markup,
    )


def _media_from_fxtwitter(media: object) -> tuple[str, ...]:
    if not isinstance(media, dict):
        return ()
    photos = media.get("photos")
    if not isinstance(photos, list):
        return ()
    urls: list[str] = []
    for item in photos:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if isinstance(url, str) and _is_public_http(url):
            urls.append(url)
    return tuple(urls)


def _linked_from_text(text: str, ref: TweetRef) -> tuple[str, ...]:
    found = re.findall(r"https?://[^\s]+", text)
    urls: list[str] = []
    for raw in found:
        cleaned = raw.rstrip(").,;\"'")
        if not _is_public_http(cleaned):
            continue
        host = urlparse(cleaned).netloc.lower()
        if host.endswith("twitter.com") or host.endswith("x.com") or host.endswith("t.co"):
            continue
        if cleaned == ref.url:
            continue
        urls.append(cleaned)
    return tuple(dict.fromkeys(urls))


def _text_from_oembed_html(markup: str) -> str:
    match = re.search(r"<p[^>]*>(.*)</p>", markup, flags=re.IGNORECASE | re.DOTALL)
    raw = match.group(1) if match else markup
    no_tags = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    no_tags = re.sub(r"<[^>]+>", "", no_tags)
    return html.unescape(no_tags).strip()


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items: list[str] = []
    for item in value:
        if isinstance(item, str) and _is_public_http(item):
            items.append(item)
    return tuple(items)


def _assert_public_http(url: str) -> None:
    if not _is_public_http(url):
        raise TweetFetchError("tweet fetch URL must be public http(s)")


def _is_public_http(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if not host or host in {"localhost", "127.0.0.1", "::1"}:
        return False
    return True
