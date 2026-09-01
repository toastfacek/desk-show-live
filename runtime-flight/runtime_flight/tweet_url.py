"""Parse public tweet / X status URLs. No network."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TWEET_RE = re.compile(
    r"^https?://(?:(?:www|mobile|m)\.)?(?:twitter\.com|x\.com)/"
    r"(?P<author>[A-Za-z0-9_]{1,15})/status/(?P<id>\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)


class TweetUrlError(Exception):
    """Raised when a string is not a public tweet URL."""


@dataclass(frozen=True)
class TweetRef:
    id: str
    author: str
    url: str


def parse_tweet_url(raw: str) -> TweetRef:
    if not isinstance(raw, str) or not raw.strip():
        raise TweetUrlError("tweet url is missing")
    text = raw.strip()
    match = _TWEET_RE.fullmatch(text)
    if match is None:
        raise TweetUrlError("not a public tweet or X status URL")
    author = match.group("author")
    tweet_id = match.group("id")
    return TweetRef(
        id=tweet_id,
        author=author,
        url=f"https://x.com/{author}/status/{tweet_id}",
    )
