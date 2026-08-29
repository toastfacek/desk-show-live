"""Writer: an async OpenAI-compatible chat client that drafts one line at a time.

Runs `beats_ahead` turns ahead of the playhead. Output contract: one spoken
line, plain text, <= max_words words, ending on a period. No stage directions.
"""

from __future__ import annotations

import logging
from collections import deque

from openai import AsyncOpenAI

logger = logging.getLogger("deskshow.writer")


class WriterUnavailable(Exception):
    """Raised when the writer endpoint fails and no canned fallback remains."""


class Writer:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        persona: str,
        topics: list[str],
        max_words: int = 12,
        history_len: int = 6,
        canned_fallback: list[str] | None = None,
    ) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._persona = persona
        self._topics = topics
        self._max_words = max_words
        self._history: deque[str] = deque(maxlen=history_len)
        self._canned_fallback = list(canned_fallback or [])
        self._consecutive_failures = 0
        self._topic_idx = 0

    def _next_topic(self) -> str:
        topic = self._topics[self._topic_idx % len(self._topics)]
        self._topic_idx += 1
        return topic

    def _messages(self, topic: str) -> list[dict]:
        transcript = "\n".join(self._history) or "(show is just starting)"
        system = (
            f"{self._persona}\n\n"
            f"Output rules: respond with ONLY the spoken line, nothing else. "
            f"No quotes, no host name prefix, no stage directions."
        )
        user = (
            f"Topic for this beat: {topic}\n\n"
            f"Recent lines:\n{transcript}\n\n"
            f"Write the next line."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _clean(self, text: str) -> str:
        line = text.strip().strip('"').strip()
        words = line.split()
        if len(words) > self._max_words:
            line = " ".join(words[: self._max_words])
        if not line.endswith("."):
            line = line.rstrip(".!?") + "."
        return line

    async def next_line(self) -> str:
        topic = self._next_topic()
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=self._messages(topic),
                max_tokens=40,
                temperature=0.9,
            )
            line = self._clean(resp.choices[0].message.content or "")
            if not line:
                raise ValueError("empty line from writer")
            self._consecutive_failures = 0
        except Exception:
            self._consecutive_failures += 1
            logger.warning(
                "writer call failed (%d consecutive)", self._consecutive_failures,
                exc_info=True,
            )
            if not self._canned_fallback:
                raise WriterUnavailable("writer down and no canned fallback configured")
            line = self._canned_fallback[
                (self._topic_idx - 1) % len(self._canned_fallback)
            ]

        self._history.append(line)
        return line
