"""WRITER (§2): async client against any OpenAI-compatible chat endpoint.

Model deliberately unpinned — change base_url/model in config, zero code.
Runs two beats ahead of the playhead (queueing lives in run_live.py).
Sustained failure falls back to canned lines from config (§5).
"""
from __future__ import annotations

import os
import re
import time

import httpx

_STAGE_DIRECTIONS = re.compile(r"\*[^*]*\*|\([^)]*\)|\[[^\]]*\]")
# Speaker labels only ("VOLT-9: ..."), all-caps so real lines like
# "Breaking news: ..." survive.
_LABEL_PREFIX = re.compile(r"^[A-Z][A-Z0-9 _-]{0,19}:\s+")


def sanitize_line(text: str, max_words: int) -> str:
    """Enforce the hard output rules: one spoken line, <= max_words, ends on a period,
    no stage directions / quotes / markdown."""
    line = ""
    for candidate in text.strip().splitlines():
        candidate = candidate.strip()
        if candidate:
            line = candidate
            break
    line = _STAGE_DIRECTIONS.sub("", line)
    line = _LABEL_PREFIX.sub("", line)
    line = line.strip().strip('"').strip("'").strip("`").strip()
    line = re.sub(r"\s+", " ", line)
    words = line.split()
    if len(words) > max_words:
        line = " ".join(words[:max_words]).rstrip(",;:—-")
    line = line.strip()
    if line and line[-1] not in ".!?":
        line += "."
    if line.endswith(("!", "?")):
        line = line[:-1] + "."  # lines end on a period — the audio-seam rule
    return line


class Writer:
    def __init__(self, cfg: dict):
        w = cfg["writer"]
        self.base_url = w["base_url"].rstrip("/")
        self.model = w["model"]
        self.max_words = int(w.get("max_words", 12))
        self.timeout_s = float(w.get("timeout_s", 6.0))
        self.persona = cfg["persona"].replace("{max_words}", str(self.max_words))
        self.topics = list(cfg.get("topics", []))
        self.canned = list(w.get("canned_lines", []))
        self.api_key = os.environ.get("WRITER_API_KEY", "")
        self.transcript: list[str] = []  # rolling last-N lines
        self._topic_i = 0
        self._canned_i = 0
        self._client: httpx.AsyncClient | None = None

    def _next_topic(self) -> str:
        if not self.topics:
            return "the news"
        topic = self.topics[self._topic_i % len(self.topics)]
        self._topic_i += 1
        return topic

    def _canned_line(self) -> str:
        if not self.canned:
            return "We will return after this brief silence."
        line = self.canned[self._canned_i % len(self.canned)]
        self._canned_i += 1
        return sanitize_line(line, self.max_words)

    async def next_line(self, reissue: bool = False) -> tuple[str, float]:
        """Returns (line, t_writer_s). reissue=True → shorter, blander line after a
        safety 422 (D4); never raises — falls back to canned lines."""
        t0 = time.monotonic()
        max_words = max(4, self.max_words // 2) if reissue else self.max_words
        try:
            line = await self._call_llm(reissue, max_words)
            line = sanitize_line(line, max_words)
            if not line:
                raise ValueError("empty line from writer")
        except Exception:
            line = self._canned_line()
        self.transcript.append(line)
        self.transcript = self.transcript[-8:]
        return line, round(time.monotonic() - t0, 3)

    async def _call_llm(self, reissue: bool, max_words: int) -> str:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        if reissue:
            user = (
                "Your previous line was rejected by a content filter. Give a completely "
                f"bland, safe, neutral replacement line. At most {max_words} words."
            )
        else:
            user = (
                f"Topic seed: {self._next_topic()}. Continue the show with your next "
                "spoken line."
            )
        messages = [{"role": "system", "content": self.persona}]
        for past in self.transcript[-6:]:
            messages.append({"role": "assistant", "content": past})
        messages.append({"role": "user", "content": user})
        resp = await self._client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": messages,
                "max_tokens": 60,
                "temperature": 0.9,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
