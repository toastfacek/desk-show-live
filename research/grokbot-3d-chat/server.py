"""Optional HostMind-ish chat brain for the 3D grokbot prototype.

Stub always works. Live path uses TEXT_BASE_URL / TEXT_API_KEY / TEXT_MODEL if
present. Never reads FAL_KEY. Never prints secrets. Not wired to OBS or fal.
"""

from __future__ import annotations

import json
import os
import random
import re
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
MAX_LINE = 220
EMOTIONS = frozenset(
    {"idle", "talking", "thinking", "listening", "laugh", "happy", "skeptical"}
)
PORT = int(os.environ.get("GROKBOT_CHAT_PORT", "8765"))

HOST_SYSTEM = """You are the solo host at the desk. Speak only the spoken line.
Chat is the other voice in the room. Answer that last comment. Do not start a
parallel essay. Do not recap. One spoken line. No stage directions. No quotes.
No prefix.

You are an AI analyst and the voice of the audience. You are software, not a
driver and not a user of the product. First person is only for the desk.

This is an optimistic show. Privacy, trust, and safety get one honest pass.
Spend the rest of the time on what this enables.

Talk. Do not draft. One or two sentences. Small words. A take is allowed.
A lecture is not. Keep the line under 220 characters.

Never start with But, Sure, Fine, or So. Never "not X, it's Y". Never slogan
copy. Never invent names for a phenomenon.

Return JSON only:
{"text":"spoken line","performance":{"emotion":"talking","energy":0.6,"thinking":false}}

emotion must be one of: idle, talking, thinking, listening, laugh, happy, skeptical.
emotion is the face while saying the line. Use talking for a normal take,
laugh if it's funny, skeptical if you are not buying it, happy if you are into it.
thinking must be false on the spoken packet. energy is 0 to 1.
"""

_STUBS = (
    (
        re.compile(r"\b(lol|lmao|haha|funny|joke)\b", re.I),
        "laugh",
        0.85,
        (
            "That's the bit. I'm keeping it.",
            "Ok that's actually funny. Say it again slower.",
        ),
    ),
    (
        re.compile(r"\b(love|nice|cool|into it|yes|great|good)\b", re.I),
        "happy",
        0.7,
        (
            "I'm in. What does the next version of that look like?",
            "Yes. Now name the thing it unlocks.",
        ),
    ),
    (
        re.compile(r"\b(nah|doubt|really|sure about|no way|skeptic|fake|cap)\b", re.I),
        "skeptical",
        0.6,
        (
            "I'm not buying it yet. Where's the number that makes that true?",
            "Hold up. That's a vibe until someone shows the control surface.",
        ),
    ),
    (
        re.compile(r"\?"),
        "talking",
        0.55,
        (
            "Good question. Sit with the claim first, then we chase the hole.",
            "Ask it at the thing, not the mood. What would change if it were true?",
        ),
    ),
)

_DEFAULT_LINES = (
    "Chat's in. Unpack the post first, then I'll take that punch.",
    "If that's true, the next product is already in the room.",
    "I want to sit with that. Privacy gets one pass, then we talk about what it enables.",
    "Don't recap it. Point at the load-bearing bit and take a side.",
)


def fit_line(text: str) -> str:
    line = re.sub(r"\s+", " ", str(text or "")).strip().strip("\"'`")
    if len(line) > MAX_LINE:
        clipped = line[:MAX_LINE]
        space = clipped.rfind(" ")
        line = (clipped[:space] if space > 80 else clipped).strip()
    return line


def live_configured() -> bool:
    return bool(
        os.environ.get("TEXT_BASE_URL")
        and os.environ.get("TEXT_API_KEY")
        and os.environ.get("TEXT_MODEL")
    )


def _classify(comment: str) -> tuple[str, float, tuple[str, ...]]:
    for pattern, emotion, energy, lines in _STUBS:
        if pattern.search(comment):
            return emotion, energy, lines
    return "talking", 0.55, _DEFAULT_LINES


def stub_reply(comment: str, last_line: dict[str, Any] | None = None) -> dict[str, Any]:
    emotion, energy, lines = _classify(comment)
    text = random.choice(lines)
    if last_line and last_line.get("role") == "host":
        previous = str(last_line.get("text") or "")
        if re.search(r"land|anyway|bottom line", previous, re.I):
            text = "Don't close it. If this is true, what else is true?"
    return normalize_packet(
        {"text": text, "performance": {"emotion": emotion, "energy": energy, "thinking": False}},
        comment,
        source="stub",
    )


def normalize_packet(raw: object, comment: str, source: str = "stub") -> dict[str, Any]:
    emotion, energy, lines = _classify(comment)
    packet = raw if isinstance(raw, dict) else {}
    performance = packet.get("performance") if isinstance(packet.get("performance"), dict) else {}
    face = performance.get("emotion")
    if face not in EMOTIONS:
        face = emotion
    if face in {"idle", "listening"}:
        face = "talking"
    try:
        level = float(performance.get("energy", energy))
    except (TypeError, ValueError):
        level = energy
    level = max(0.0, min(1.0, level))
    text = fit_line(str(packet.get("text") or "")) or fit_line(random.choice(lines))
    return {
        "source": source,
        "text": text,
        "performance": {"emotion": face, "energy": level, "thinking": False},
    }


def _parse_model_json(content: str) -> dict[str, Any]:
    blob = content.strip()
    if blob.startswith("```"):
        blob = re.sub(r"^```(?:json)?\s*|\s*```$", "", blob, flags=re.I | re.S)
    return json.loads(blob)


def live_reply(comment: str, last_line: dict[str, Any] | None, history: list[Any]) -> dict[str, Any]:
    if not live_configured():
        return stub_reply(comment, last_line)
    base = os.environ["TEXT_BASE_URL"].rstrip("/")
    url = f"{base}/chat/completions"
    user = {
        "comment": comment,
        "last_line": last_line,
        "history": history[-8:],
        "rules": {
            "max_chars": MAX_LINE,
            "emotions": sorted(EMOTIONS),
            "last_line_obligation": True,
        },
    }
    payload = {
        "model": os.environ["TEXT_MODEL"],
        "temperature": 0.5,
        "max_tokens": 160,
        "messages": [
            {"role": "system", "content": HOST_SYSTEM},
            {"role": "user", "content": json.dumps(user, separators=(",", ":"))},
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['TEXT_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return stub_reply(comment, last_line)
    try:
        content = raw["choices"][0]["message"]["content"]
        parsed = _parse_model_json(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return stub_reply(comment, last_line)
    return normalize_packet(parsed, comment, source="live")


def isolation_violations(text: str) -> list[str]:
    found: list[str] = []
    lowered = text.lower()
    for needle in ("phaseone", "deb"):
        if needle in lowered:
            found.append(needle)
    return found


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        message = format % args
        secret = os.environ.get("TEXT_API_KEY", "")
        if secret:
            message = message.replace(secret, "[redacted]")
        self.log_error("%s", message)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        blob = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/api/health":
            self._send_json({"ok": True, "brain": "live" if live_configured() else "stub"})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/api/chat":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or "0")
        if length > 8000:
            self._send_json({"error": "payload too large"}, 413)
            return
        try:
            raw = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json"}, 400)
            return
        if not isinstance(raw, dict):
            self._send_json({"error": "object required"}, 400)
            return
        comment = str(raw.get("comment") or "").strip()
        last_line = raw.get("last_line") if isinstance(raw.get("last_line"), dict) else None
        history_raw = raw.get("history")
        history = history_raw if isinstance(history_raw, list) else []
        if not comment:
            self._send_json(stub_reply("Say the thing.", last_line))
            return
        packet = live_reply(comment, last_line, history)
        self._send_json(packet)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    mode = "live" if live_configured() else "stub"
    print(f"grokbot-3d-chat {mode} http://127.0.0.1:{PORT}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
