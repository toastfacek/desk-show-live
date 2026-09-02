"""Official X embed URL for the centre well. Digits only; no oEmbed HTML."""

from __future__ import annotations

import re

_TWEET_ID = re.compile(r"^\d{5,25}$")
EMBED_ORIGIN = "https://platform.twitter.com"
EMBED_PATH = "/embed/Tweet.html"


class TweetEmbedError(Exception):
    """Raised when a tweet id cannot be turned into an official embed."""


def _embed_id(tweet_id: str) -> str:
    if not _TWEET_ID.fullmatch(tweet_id or ""):
        raise TweetEmbedError("tweet id is not a numeric status id")
    return tweet_id


def _embed_theme(theme: str) -> str:
    return theme if theme in {"dark", "light"} else "dark"


def official_embed_url(tweet_id: str, *, theme: str = "dark") -> str:
    return (
        f"{EMBED_ORIGIN}{EMBED_PATH}"
        f"?dnt=true&hide_thread=true&theme={_embed_theme(theme)}&id={_embed_id(tweet_id)}"
    )


def embed_frame_path(tweet_id: str, *, theme: str = "dark") -> str:
    return f"/tweet-embed.html?id={_embed_id(tweet_id)}&theme={_embed_theme(theme)}"
