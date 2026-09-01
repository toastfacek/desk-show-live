"""Official X embed URL for the centre well. Digits only; no oEmbed HTML."""

from __future__ import annotations

import re

_TWEET_ID = re.compile(r"^\d{5,25}$")
EMBED_ORIGIN = "https://platform.twitter.com"
EMBED_PATH = "/embed/Tweet.html"


class TweetEmbedError(Exception):
    """Raised when a tweet id cannot be turned into an official embed."""


def official_embed_url(tweet_id: str, *, theme: str = "dark") -> str:
    if not _TWEET_ID.fullmatch(tweet_id or ""):
        raise TweetEmbedError("tweet id is not a numeric status id")
    if theme not in {"dark", "light"}:
        theme = "dark"
    return (
        f"{EMBED_ORIGIN}{EMBED_PATH}"
        f"?dnt=true&hide_thread=true&theme={theme}&id={tweet_id}"
    )


def embed_frame_path(tweet_id: str, *, theme: str = "dark") -> str:
    if not _TWEET_ID.fullmatch(tweet_id or ""):
        raise TweetEmbedError("tweet id is not a numeric status id")
    if theme not in {"dark", "light"}:
        theme = "dark"
    return f"/tweet-embed.html?id={tweet_id}&theme={theme}"
