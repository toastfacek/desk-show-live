"""Parse and page a public X/Twitter list. No cook, no writer."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from runtime_flight.tweet_fetch import HttpGet, default_http_get
from runtime_flight.tweet_url import TweetRef, TweetUrlError, parse_tweet_url

LIST_ID_RE = re.compile(
    r"^https?://(?:(?:www|mobile|m)\.)?(?:twitter\.com|x\.com)/i/lists/(?P<id>\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)
LISTS_API = "https://api.twitter.com/2/lists"
BEARER_ENVS = ("X_BEARER_TOKEN", "TWITTER_BEARER_TOKEN")
DEFAULT_PAGE_SIZE = 50


class TweetListError(Exception):
    """Raised when a Twitter list cannot be parsed or paged."""


@dataclass(frozen=True)
class TwitterListRef:
    list_id: str
    url: str


@dataclass(frozen=True)
class ListPage:
    tweets: tuple[TweetRef, ...]
    next_token: str | None


def parse_list_url(raw: str) -> TwitterListRef:
    if not isinstance(raw, str) or not raw.strip():
        raise TweetListError("list url is missing")
    match = LIST_ID_RE.fullmatch(raw.strip())
    if match is None:
        raise TweetListError("not a public X/Twitter list URL (need https://x.com/i/lists/<id>)")
    list_id = match.group("id")
    return TwitterListRef(list_id=list_id, url=f"https://x.com/i/lists/{list_id}")


def bearer_token(env: dict[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    for key in BEARER_ENVS:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""


def fetch_list_page(
    list_id: str,
    *,
    bearer: str,
    pagination_token: str | None = None,
    max_results: int = DEFAULT_PAGE_SIZE,
    http_get: HttpGet | None = None,
) -> ListPage:
    if not list_id.isdigit():
        raise TweetListError("list id must be numeric")
    if not bearer:
        raise TweetListError("login required: set X_BEARER_TOKEN")
    getter = http_get or default_http_get
    query = {
        "max_results": str(min(max(max_results, 1), 100)),
        "tweet.fields": "author_id,text,created_at",
        "expansions": "author_id",
        "user.fields": "username",
    }
    if pagination_token:
        query["pagination_token"] = pagination_token
    url = f"{LISTS_API}/{list_id}/tweets?{urlencode(query)}"
    status, body, _content_type = getter(
        url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {bearer}"},
    )
    if status == 401:
        raise TweetListError("twitter list login was rejected")
    if status != 200:
        raise TweetListError(f"tweet list HTTP {status}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TweetListError("tweet list is not valid JSON") from error
    return _page_from_api(payload)


def load_list_file(path: Path) -> tuple[TwitterListRef, tuple[TweetRef, ...]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TweetListError("list file must be a JSON object")
    list_id = str(raw.get("list_id") or raw.get("id") or "")
    if not list_id.isdigit():
        raise TweetListError("list file is missing a numeric list_id")
    tweets_raw = raw.get("tweets")
    if not isinstance(tweets_raw, list) or not tweets_raw:
        raise TweetListError("list file tweets must be a non-empty array")
    tweets: list[TweetRef] = []
    for item in tweets_raw:
        if isinstance(item, str):
            tweets.append(_ref_from_url(item))
            continue
        if not isinstance(item, dict):
            raise TweetListError("list file tweet must be a url or object")
        url = item.get("url") or ""
        tweets.append(_ref_from_url(str(url)))
    return TwitterListRef(list_id=list_id, url=f"https://x.com/i/lists/{list_id}"), tuple(tweets)


def _ref_from_url(url: str) -> TweetRef:
    try:
        return parse_tweet_url(url)
    except TweetUrlError as error:
        raise TweetListError(str(error)) from error


def _page_from_api(payload: dict[str, Any]) -> ListPage:
    if not isinstance(payload, dict):
        raise TweetListError("tweet list is not a JSON object")
    users = {}
    includes = payload.get("includes")
    if isinstance(includes, dict):
        for user in includes.get("users") or []:
            if isinstance(user, dict) and user.get("id") and user.get("username"):
                users[str(user["id"])] = str(user["username"]).lstrip("@")
    tweets: list[TweetRef] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        tweet_id = str(item.get("id") or "")
        author = users.get(str(item.get("author_id") or ""), "")
        if not tweet_id.isdigit() or not author:
            continue
        tweets.append(
            TweetRef(id=tweet_id, author=author, url=f"https://x.com/{author}/status/{tweet_id}")
        )
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    next_token = meta.get("next_token")
    if not isinstance(next_token, str) or not next_token:
        next_token = None
    return ListPage(tweets=tuple(tweets), next_token=next_token)
