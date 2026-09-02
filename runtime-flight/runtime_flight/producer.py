"""Visual producer board: project harness state, serve the control room, run a demo."""

from __future__ import annotations

import json
import threading
import time
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from runtime_flight.models import CoverageState, SegmentPackage, Thought, TopicMap
from runtime_flight.topic_map import current_beat, resolve_topic_map

DEFAULT_PRODUCER_DIR = Path(__file__).resolve().parent.parent / "producer"
DEFAULT_MAX_STATE_BYTES = 131_072
DEFAULT_PORT = 8766
CLIP_DURATION_S = 5.0
WRITE_S = 1.1
GENERATE_S = 4.6

_STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}

HOST_NAMES = {"BOT1": "PHASEONE[lol]", "BOT2": "deb"}
OPERATOR_ACTIONS = frozenset(
    {"hold", "resume", "panic", "kill", "preview", "next_segment"}
)


def format_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def money(value: Decimal | str | float) -> str:
    if isinstance(value, Decimal):
        quantized = value.quantize(Decimal("0.01"))
    else:
        quantized = Decimal(str(value)).quantize(Decimal("0.01"))
    return f"{quantized:.2f}"


def derive_phase(
    *,
    flags: dict[str, Any],
    on_air: dict[str, Any] | None,
    cooking: dict[str, Any] | None,
    ready: list[Any],
    next_line: dict[str, Any] | None,
) -> str:
    if flags.get("panic"):
        return "PANIC"
    if flags.get("hold") or (on_air and on_air.get("kind") == "hold"):
        return "HOLD"
    if on_air and on_air.get("kind") == "host":
        return "PLAY"
    if ready:
        return "READY"
    if cooking is not None:
        return "GENERATE"
    if next_line is not None:
        return "WRITE"
    return "HOLD"


def empty_producer_state() -> dict[str, Any]:
    return {
        "show": "RUNTIME",
        "system": "LIVE SYSTEM",
        "mode": "idle",
        "phase": "HOLD",
        "elapsed_s": 0.0,
        "target_s": 90.0,
        "clock": "00:00",
        "remain_s": 90.0,
        "live_state": "Stand by. The producer board is waiting for a segment.",
        "meta": "no segment · take —",
        "stats": {
            "layout": "hold",
            "speaker": "—",
            "speaker_name": "—",
            "spend_usd": "0.00",
            "spend_cap": "12.00",
            "aired": 0,
            "queue": 0,
        },
        "program": {
            "layout": "hold",
            "live": False,
            "hold": True,
            "preview": False,
            "speaker": None,
            "hosts": {
                "BOT1": {"name": HOST_NAMES["BOT1"], "on_air": False},
                "BOT2": {"name": HOST_NAMES["BOT2"], "on_air": False},
            },
            "card": {"author": "", "body": ""},
            "chyron": {"kicker": "DESK", "headline": ""},
            "line": "",
            "clock": "00:00",
        },
        "pipeline": [
            {"id": "write", "label": "WRITE", "detail": "", "state": "idle"},
            {"id": "generate", "label": "5s CLIP", "detail": "", "state": "idle"},
            {"id": "ready", "label": "READY", "detail": "", "state": "idle"},
            {"id": "play", "label": "PLAY", "detail": "", "state": "idle"},
            {"id": "hold", "label": "HOLD", "detail": "", "state": "idle"},
        ],
        "lanes": {
            "on_air": _empty_lane("ON AIR"),
            "next": _empty_lane("NEXT"),
        },
        "writer": {
            "phase": "open",
            "ready": [],
            "coverage": {
                "beat_id": "",
                "beat_index": 0,
                "question": "",
                "exchanges": 0,
                "map_complete": False,
            },
        },
        "story": {
            "item_id": "",
            "question": "",
            "framing": "",
            "chyron": "",
            "angles": [],
            "beats": [],
            "center": {"author": "", "text": ""},
            "throughline": "",
            "fight": "",
        },
        "queue": {"ready": [], "cooking": None, "log": []},
        "flags": {"hold": False, "panic": False, "preview": False},
        "controls": {
            "preview_next": False,
            "kill_take": False,
            "hold": True,
            "resume": False,
            "next_segment": True,
            "panic": True,
        },
        "note": (
            "Play-while-generating: take N airs while N+1 cooks. "
            "One performer request at a time. The harness owns the clock."
        ),
    }


def project_producer_state(
    *,
    elapsed_s: float,
    target_s: float,
    package: SegmentPackage | None,
    on_air: dict[str, Any] | None,
    ready: list[dict[str, Any]],
    cooking: dict[str, Any] | None,
    next_line: dict[str, Any] | None,
    flags: dict[str, Any],
    layout: str,
    spend_total: Decimal,
    spend_cap: Decimal,
    writer_phase: str,
    coverage: CoverageState | None,
    display_names: dict[str, str],
    aired_count: int,
    next_take: int,
    mode: str,
    writer_ready: list[dict[str, str]] | None = None,
    take_log: list[dict[str, Any]] | None = None,
    generate_elapsed_s: float | None = None,
) -> dict[str, Any]:
    names = {**HOST_NAMES, **display_names}
    flags = {
        "hold": bool(flags.get("hold")),
        "panic": bool(flags.get("panic")),
        "preview": bool(flags.get("preview")),
    }
    phase = derive_phase(
        flags=flags,
        on_air=on_air,
        cooking=cooking,
        ready=ready,
        next_line=next_line,
    )
    speaker = None
    if on_air and on_air.get("kind") == "host":
        speaker = on_air.get("speaker")
    layout_name = "hold" if phase in {"HOLD", "PANIC"} else layout
    if on_air and on_air.get("layout"):
        layout_name = str(on_air["layout"])
    if phase in {"HOLD", "PANIC"}:
        layout_name = "hold"

    live_state, meta = _live_copy(
        package=package,
        phase=phase,
        on_air=on_air,
        cooking=cooking,
        next_line=next_line,
        writer_phase=writer_phase,
        next_take=next_take,
        names=names,
    )
    remain_on_air = _remain_on_air(on_air, elapsed_s)
    generate_s = generate_elapsed_s
    if generate_s is None and cooking is not None:
        generate_s = max(0.0, elapsed_s - float(cooking.get("submitted_at") or elapsed_s))

    story = _story_from_package(package)
    card_author = story["center"]["author"]
    card_body = story["center"]["text"]
    line = ""
    if on_air and on_air.get("kind") == "host":
        line = str(on_air.get("line") or "")
    elif flags["preview"] and next_line:
        line = str(next_line.get("text") or "")
    elif cooking:
        line = str(cooking.get("line") or "")

    on_air_lane = _lane_from_on_air(on_air, names, remain_on_air)
    next_lane = _lane_from_next(ready, cooking, next_line, names, generate_s)

    state = empty_producer_state()
    state.update(
        {
            "mode": mode,
            "phase": phase,
            "elapsed_s": round(float(elapsed_s), 2),
            "target_s": float(target_s),
            "clock": format_clock(elapsed_s),
            "remain_s": round(max(0.0, float(target_s) - float(elapsed_s)), 2),
            "live_state": live_state,
            "meta": meta,
            "stats": {
                "layout": layout_name,
                "speaker": speaker or "—",
                "speaker_name": names.get(speaker, "—") if speaker else "—",
                "spend_usd": money(spend_total),
                "spend_cap": money(spend_cap),
                "aired": int(aired_count),
                "queue": len(ready) + (1 if cooking else 0),
            },
            "program": {
                "layout": layout_name,
                "live": phase not in {"HOLD", "PANIC"},
                "hold": phase in {"HOLD", "PANIC"},
                "preview": flags["preview"],
                "speaker": speaker,
                "hosts": {
                    "BOT1": {
                        "name": names["BOT1"],
                        "on_air": speaker == "BOT1",
                    },
                    "BOT2": {
                        "name": names["BOT2"],
                        "on_air": speaker == "BOT2",
                    },
                },
                "card": {"author": card_author, "body": card_body},
                "chyron": {
                    "kicker": "DESK",
                    "headline": story["chyron"] or "Stand by.",
                },
                "line": line,
                "clock": format_clock(elapsed_s),
            },
            "pipeline": _pipeline(
                phase=phase,
                cooking=cooking,
                ready=ready,
                generate_s=generate_s,
                remain_on_air=remain_on_air,
                next_line=next_line,
            ),
            "lanes": {"on_air": on_air_lane, "next": next_lane},
            "writer": {
                "phase": writer_phase,
                "ready": list(writer_ready or ([] if next_line is None else [next_line])),
                "coverage": _coverage_view(package, coverage),
            },
            "story": story,
            "queue": {
                "ready": list(ready),
                "cooking": (
                    {
                        "take": cooking.get("take"),
                        "speaker": cooking.get("speaker") or "",
                        "line": cooking.get("line") or "",
                        "submitted_at": cooking.get("submitted_at"),
                    }
                    if cooking
                    else None
                ),
                "log": list(take_log or []),
            },
            "flags": flags,
            "controls": {
                "preview_next": next_lane["status"] not in {"EMPTY", "—"},
                "kill_take": next_lane["status"] in {"READY", "GENERATING"},
                "hold": not flags["hold"] and not flags["panic"],
                "resume": flags["hold"] and not flags["panic"],
                "next_segment": True,
                "panic": not flags["panic"],
            },
        }
    )
    return state


def project_from_harness(harness: Any, *, mode: str = "live") -> dict[str, Any]:
    snapshot = harness.snapshot()
    on_air = dict(snapshot["on_air"]) if snapshot.get("on_air") else None
    if on_air and on_air.get("kind") == "host":
        take = on_air.get("take")
        thought = getattr(harness, "_thought_by_take", {}).get(take)
        if thought is not None:
            on_air["line"] = thought.text
            on_air["speaker"] = thought.speaker
        else:
            for row in getattr(harness, "log", []):
                if row.get("take") == take:
                    on_air["line"] = row.get("line") or ""
                    on_air["speaker"] = row.get("speaker") or on_air.get("speaker")
                    break
    cooking = snapshot.get("cooking")
    cooking_view = None
    if cooking:
        request = cooking.get("request")
        cooking_view = {
            "take": cooking.get("take"),
            "submitted_at": cooking.get("submitted_at"),
            "speaker": getattr(request, "speaker", "") if request is not None else "",
            "line": getattr(request, "line", "") if request is not None else "",
        }
    ready = list(snapshot.get("ready") or [])
    next_line = snapshot.get("next_line")
    layout = "hold"
    if on_air and on_air.get("layout"):
        layout = str(on_air["layout"])
    elif snapshot.get("segment", {}).get("layout_plan"):
        plan = snapshot["segment"]["layout_plan"]
        index = int(snapshot.get("layout_i") or 0)
        if plan:
            layout = plan[min(index, len(plan) - 1)]
    coverage = getattr(getattr(harness, "pipeline", None), "coverage", None)
    display_names = dict(getattr(getattr(harness, "baseline", None), "display_names", {}) or {})
    meter = getattr(harness, "meter", None)
    spend_total = getattr(meter, "total", Decimal("0"))
    spend_cap = getattr(meter, "cap_usd", Decimal("12.00"))
    take_log = []
    for row in getattr(harness, "log", []):
        take_log.append(
            {
                "take": row.get("take"),
                "speaker": row.get("speaker") or "",
                "line": row.get("line") or "",
                "status": row.get("status") or "",
                "t_on_air": row.get("t_on_air"),
            }
        )
    return project_producer_state(
        elapsed_s=float(snapshot.get("t") or 0.0),
        target_s=float(getattr(harness, "target_duration_s", 90.0)),
        package=getattr(harness, "package", None),
        on_air=on_air,
        ready=ready,
        cooking=cooking_view,
        next_line=next_line,
        flags=dict(snapshot.get("flags") or {}),
        layout=layout,
        spend_total=spend_total,
        spend_cap=spend_cap,
        writer_phase=harness.current_writer_phase()
        if hasattr(harness, "current_writer_phase")
        else "develop",
        coverage=coverage,
        display_names=display_names,
        aired_count=int(getattr(harness, "aired_count", 0)),
        next_take=int(snapshot.get("next_take") or 1),
        mode=mode,
        take_log=take_log,
    )


def apply_operator(harness: Any, action: str) -> None:
    if action not in OPERATOR_ACTIONS:
        raise ValueError(f"unknown operator action: {action}")
    flags = harness.flags
    if action == "hold":
        flags["hold"] = True
        flags["preview"] = False
    elif action == "resume":
        flags["hold"] = False
        flags["panic"] = False
        flags["preview"] = False
    elif action == "panic":
        flags["panic"] = True
        flags["hold"] = True
        flags["preview"] = False
        harness._stop_submits = True
        harness.spend_policy = "stop"
    elif action == "preview":
        flags["preview"] = True
    elif action == "kill":
        if getattr(harness, "ready", None):
            dropped = harness.ready.pop(0)
            harness.events.append(
                {"t": harness.t, "kind": "operator_kill", "take": dropped.take}
            )
    elif action == "next_segment":
        flags["next_segment"] = True


def _empty_lane(label: str) -> dict[str, Any]:
    return {
        "label": label,
        "take": None,
        "speaker": "",
        "name": "—",
        "line": "",
        "remain_s": 0.0,
        "progress": 0.0,
        "status": "EMPTY",
    }


def _remain_on_air(on_air: dict[str, Any] | None, elapsed_s: float) -> float | None:
    if not on_air or on_air.get("kind") != "host":
        return None
    ends = on_air.get("ends_at")
    if ends is None:
        return None
    return max(0.0, float(ends) - float(elapsed_s))


def _lane_from_on_air(
    on_air: dict[str, Any] | None,
    names: dict[str, str],
    remain_s: float | None,
) -> dict[str, Any]:
    lane = _empty_lane("ON AIR")
    if not on_air or on_air.get("kind") != "host":
        if on_air and on_air.get("kind") in {"hold", "card"}:
            lane["status"] = "HOLD" if on_air.get("kind") == "hold" else "CARD"
            lane["line"] = "Centre card is carrying the picture."
        return lane
    speaker = str(on_air.get("speaker") or "")
    remain = CLIP_DURATION_S if remain_s is None else remain_s
    lane.update(
        {
            "take": on_air.get("take"),
            "speaker": speaker,
            "name": names.get(speaker, speaker or "—"),
            "line": str(on_air.get("line") or ""),
            "remain_s": round(remain, 2),
            "progress": round(max(0.0, min(1.0, 1.0 - (remain / CLIP_DURATION_S))), 3),
            "status": "PLAYING",
        }
    )
    return lane


def _lane_from_next(
    ready: list[dict[str, Any]],
    cooking: dict[str, Any] | None,
    next_line: dict[str, Any] | None,
    names: dict[str, str],
    generate_s: float | None,
) -> dict[str, Any]:
    lane = _empty_lane("NEXT")
    if ready:
        clip = ready[0]
        speaker = str(clip.get("speaker") or "")
        lane.update(
            {
                "take": clip.get("take"),
                "speaker": speaker,
                "name": names.get(speaker, speaker or "—"),
                "line": str(clip.get("line") or ""),
                "remain_s": float(clip.get("duration_s") or CLIP_DURATION_S),
                "progress": 1.0,
                "status": "READY",
            }
        )
        return lane
    if cooking:
        speaker = str(cooking.get("speaker") or "")
        elapsed = 0.0 if generate_s is None else generate_s
        lane.update(
            {
                "take": cooking.get("take"),
                "speaker": speaker,
                "name": names.get(speaker, speaker or "—"),
                "line": str(cooking.get("line") or ""),
                "remain_s": round(max(0.0, GENERATE_S - elapsed), 2),
                "progress": round(max(0.0, min(1.0, elapsed / GENERATE_S)), 3),
                "status": "GENERATING",
            }
        )
        return lane
    if next_line:
        speaker = str(next_line.get("speaker") or "")
        lane.update(
            {
                "take": None,
                "speaker": speaker,
                "name": names.get(speaker, speaker or "—"),
                "line": str(next_line.get("text") or ""),
                "status": "WRITING",
            }
        )
    return lane


def _pipeline(
    *,
    phase: str,
    cooking: dict[str, Any] | None,
    ready: list[Any],
    generate_s: float | None,
    remain_on_air: float | None,
    next_line: dict[str, Any] | None,
) -> list[dict[str, str]]:
    states = {
        "write": "idle",
        "generate": "idle",
        "ready": "idle",
        "play": "idle",
        "hold": "idle",
    }
    details = {
        "write": f"{WRITE_S:.1f}s" if next_line else "",
        "generate": "",
        "ready": str(len(ready)) if ready else "",
        "play": "",
        "hold": "",
    }
    if phase == "WRITE":
        states["write"] = "active"
    elif phase == "GENERATE":
        states["write"] = "done"
        states["generate"] = "active"
        if generate_s is not None:
            details["generate"] = f"{generate_s:.1f}s"
    elif phase == "READY":
        states["write"] = "done"
        states["generate"] = "done"
        states["ready"] = "active"
    elif phase == "PLAY":
        states["write"] = "done"
        states["generate"] = "done" if (ready or cooking) else "idle"
        if cooking:
            states["generate"] = "active"
            if generate_s is not None:
                details["generate"] = f"{generate_s:.1f}s"
        if ready:
            states["ready"] = "done"
        states["play"] = "active"
        if remain_on_air is not None:
            details["play"] = f"{remain_on_air:.1f}s"
    elif phase in {"HOLD", "PANIC"}:
        states["hold"] = "active"
        details["hold"] = phase
    if cooking and phase == "PLAY":
        states["generate"] = "active"
    return [
        {
            "id": key,
            "label": label,
            "detail": details[key],
            "state": states[key],
        }
        for key, label in (
            ("write", "WRITE"),
            ("generate", "5s CLIP"),
            ("ready", "READY"),
            ("play", "PLAY"),
            ("hold", "HOLD"),
        )
    ]


def _live_copy(
    *,
    package: SegmentPackage | None,
    phase: str,
    on_air: dict[str, Any] | None,
    cooking: dict[str, Any] | None,
    next_line: dict[str, Any] | None,
    writer_phase: str,
    next_take: int,
    names: dict[str, str],
) -> tuple[str, str]:
    framing = package.framing if package is not None else "No producer package is loaded."
    question = package.question if package is not None else "Stand by."
    item = package.item_id if package is not None else "idle"
    if phase == "PANIC":
        body = (
            "Panic. Cut to hold, stop submitting, keep the ticker and the bed. "
            "The clock still belongs to the harness. Do not invent a new show."
        )
    elif phase == "HOLD":
        body = (
            f"{framing} The picture is on hold: card up, furniture live, no host clip. "
            f"We are still inside the question — {question}"
        )
    elif phase == "WRITE":
        who = names.get((next_line or {}).get("speaker", ""), "the next host")
        body = (
            f"{framing} Writer is opening the next thought for {who}. "
            "Do not buy a clip until the line is in the slot."
        )
    elif phase == "GENERATE":
        take = (cooking or {}).get("take") or next_take
        body = (
            f"{framing} Take {take} is cooking. Play-while-generating is armed: "
            "the current picture stays up until the file lands. One performer only."
        )
    elif phase == "READY":
        body = (
            f"{framing} A clip is ready in the queue. The director may cut on the next edge. "
            "Preview is free — the file already exists."
        )
    else:
        speaker = (on_air or {}).get("speaker")
        who = names.get(speaker, "the desk") if speaker else "the desk"
        body = (
            f"{framing} {who} is on the air. Keep the complementary job for the other host. "
            "Do not recap the card. Land while an angle is still unsaid."
        )
    take_label = "—"
    if on_air and on_air.get("take"):
        take_label = str(on_air["take"])
    elif cooking and cooking.get("take"):
        take_label = str(cooking["take"])
    meta = f"segment {item} · take {take_label} · writer {writer_phase} · phase {phase.lower()}"
    return body, meta


def _story_from_package(package: SegmentPackage | None) -> dict[str, Any]:
    if package is None:
        return empty_producer_state()["story"]
    topic: TopicMap | None = None
    try:
        topic = resolve_topic_map(package)
    except Exception:
        topic = package.topic_map
    beats = []
    if topic is not None:
        for beat in topic.beats:
            beats.append(
                {
                    "id": beat.id,
                    "question": beat.question,
                    "tension": beat.tension,
                    "bot1_job": beat.bot1_job,
                    "bot2_job": beat.bot2_job,
                }
            )
    return {
        "item_id": package.item_id,
        "question": package.question,
        "framing": package.framing,
        "chyron": package.chyron,
        "angles": list(package.angles),
        "beats": beats,
        "center": {
            "author": package.center.author,
            "text": package.center.text,
        },
        "throughline": topic.throughline if topic is not None else "",
        "fight": topic.fight if topic is not None else "",
    }


def _coverage_view(
    package: SegmentPackage | None, coverage: CoverageState | None
) -> dict[str, Any]:
    if package is None or coverage is None:
        return {
            "beat_id": "",
            "beat_index": 0,
            "question": "",
            "exchanges": 0,
            "map_complete": False,
        }
    try:
        topic = resolve_topic_map(package)
        beat = current_beat(topic, coverage)
        question = beat.question
        beat_id = beat.id
    except Exception:
        question = ""
        beat_id = ""
    return {
        "beat_id": beat_id,
        "beat_index": coverage.beat_index,
        "question": question,
        "exchanges": coverage.exchanges_on_beat,
        "map_complete": coverage.map_complete,
    }


class ProducerBoard:
    """Mutable board the HTTP server and the harness both talk to."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = empty_producer_state()
        self._commands: list[str] = []
        self._sequence = 0

    def publish(self, state: dict[str, Any]) -> None:
        with self._lock:
            merged = empty_producer_state()
            merged.update(state)
            self._state = merged
            self._sequence += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            payload = json.loads(json.dumps(self._state))
            payload["sequence"] = self._sequence
            return payload

    def queue_command(self, action: str) -> dict[str, Any]:
        if action not in OPERATOR_ACTIONS:
            raise ValueError(f"unknown operator action: {action}")
        with self._lock:
            self._commands.append(action)
            flags = dict(self._state.get("flags") or {})
            if action == "hold":
                flags["hold"] = True
                flags["preview"] = False
            elif action == "resume":
                flags["hold"] = False
                flags["panic"] = False
                flags["preview"] = False
            elif action == "panic":
                flags["panic"] = True
                flags["hold"] = True
                flags["preview"] = False
            elif action == "preview":
                flags["preview"] = True
            self._state["flags"] = flags
            self._sequence += 1
            return {"ok": True, "action": action, "sequence": self._sequence}

    def drain_commands(self) -> list[str]:
        with self._lock:
            commands = list(self._commands)
            self._commands.clear()
            return commands


class ProducerServer:
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        producer_dir: Path | None = None,
        board: ProducerBoard | None = None,
    ) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("producer server must bind loopback only")
        self._host = "127.0.0.1" if host == "localhost" else host
        self._port = port
        self._producer_dir = Path(producer_dir or DEFAULT_PRODUCER_DIR)
        self.board = board or ProducerBoard()
        self._httpd: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        if self._httpd is None:
            raise RuntimeError("producer server is not running")
        return int(self._httpd.server_address[1])

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> str:
        if self._httpd is not None:
            return self.url
        handler = _make_handler(self)
        httpd = ThreadingHTTPServer((self._host, self._port), handler)
        self._httpd = httpd
        self._http_thread = threading.Thread(
            target=httpd.serve_forever,
            name="producer-http",
            daemon=True,
        )
        self._http_thread.start()
        return self.url

    def stop(self) -> None:
        httpd = self._httpd
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if self._http_thread is not None:
            self._http_thread.join(timeout=2.0)
        self._httpd = None
        self._http_thread = None

    def __enter__(self) -> ProducerServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def static_bytes(self, filename: str) -> bytes:
        path = (self._producer_dir / filename).resolve()
        root = self._producer_dir.resolve()
        if root not in path.parents and path != root:
            raise FileNotFoundError(filename)
        if path.parent != root:
            raise FileNotFoundError(filename)
        return path.read_bytes()


def _make_handler(server: ProducerServer) -> type[BaseHTTPRequestHandler]:
    class ProducerHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/state.json":
                self._send_json(server.board.snapshot())
                return
            static = _STATIC_FILES.get(path)
            if static is None:
                self.send_error(404)
                return
            filename, content_type = static
            try:
                body = server.static_bytes(filename)
            except FileNotFoundError:
                self.send_error(404)
                return
            self._send(200, body, content_type)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path != "/control":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length > 4096:
                self.send_error(413)
                return
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
                action = str(payload.get("action") or "")
                result = server.board.queue_command(action)
            except (ValueError, json.JSONDecodeError) as error:
                self._send_json({"ok": False, "error": str(error)}, status=400)
                return
            self._send_json(result)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
            self._send(status, body, "application/json; charset=utf-8")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(body)

    return ProducerHandler


class DemoShow:
    """Zero-cost clock that makes the board look like a live segment."""

    LINES = (
        ("BOT1", "Three secret agent civilizations rose inside OpenAI in ninety days."),
        ("BOT2", "Wiped out, then rebuilt from the previous one's ashes. That is the claim."),
        ("BOT1", "The third one takes over part of the company. Humans stay mostly dark."),
        ("BOT2", "What moved — the reports, or the story we are telling about the reports?"),
        ("BOT1", "If the conspiracy is real, the chyron cannot be a vibe. Name the takeover."),
        ("BOT2", "If it is weather, we should say so before the card starts writing the show."),
    )

    def __init__(self) -> None:
        self.elapsed_s = 0.0
        self.target_s = 90.0
        self.paused = False
        self.flags = {"hold": False, "panic": False, "preview": False}
        self.killed: set[int] = set()
        self.segment_i = 0
        self._package = demo_package()

    def tick(self, dt: float) -> dict[str, Any]:
        if not self.paused and not self.flags["hold"] and not self.flags["panic"]:
            self.elapsed_s = min(self.target_s, self.elapsed_s + dt)
        if self.elapsed_s + 1e-9 >= self.target_s:
            self.flags["hold"] = True
        return self.view()

    def control(self, action: str) -> None:
        if action not in OPERATOR_ACTIONS:
            raise ValueError(f"unknown operator action: {action}")
        if action == "hold":
            self.flags["hold"] = True
            self.flags["preview"] = False
            self.paused = True
        elif action == "resume":
            self.flags = {"hold": False, "panic": False, "preview": False}
            self.paused = False
        elif action == "panic":
            self.flags = {"hold": True, "panic": True, "preview": False}
            self.paused = True
        elif action == "preview":
            self.flags["preview"] = True
        elif action == "kill":
            cooking_take = self._cooking_take()
            if cooking_take is not None:
                self.killed.add(cooking_take)
        elif action == "next_segment":
            self.elapsed_s = 0.0
            self.paused = False
            self.flags = {"hold": False, "panic": False, "preview": False}
            self.killed.clear()
            self.segment_i += 1

    def view(self) -> dict[str, Any]:
        cycle = WRITE_S + GENERATE_S + CLIP_DURATION_S
        raw_index = 0 if self.elapsed_s < WRITE_S else int((self.elapsed_s - WRITE_S) // CLIP_DURATION_S)
        take = raw_index + 1
        if take in self.killed:
            take += 1
        line_i = min(len(self.LINES) - 1, max(0, take - 1))
        speaker, line = self.LINES[line_i]
        next_i = min(len(self.LINES) - 1, line_i + 1)
        next_speaker, next_line = self.LINES[next_i]
        since_write = max(0.0, self.elapsed_s - WRITE_S)
        in_clip = since_write % CLIP_DURATION_S if self.elapsed_s >= WRITE_S else 0.0
        generating = self.elapsed_s >= WRITE_S and take not in self.killed
        on_air = None
        cooking = None
        ready: list[dict[str, Any]] = []
        next_line_obj = {"speaker": next_speaker, "text": next_line}
        aired = 0
        layout = "split"
        if self.elapsed_s < WRITE_S:
            on_air = {"kind": "card", "take": None, "ends_at": None, "layout": "card_full"}
            layout = "card_full"
            next_line_obj = {"speaker": speaker, "text": line}
        elif generating and in_clip < 0.15 and take == 1:
            cooking = {
                "take": 1,
                "submitted_at": WRITE_S,
                "speaker": speaker,
                "line": line,
            }
            on_air = {"kind": "card", "take": None, "layout": "card_full"}
            layout = "card_full"
            next_line_obj = {"speaker": next_speaker, "text": next_line}
        else:
            play_take = take if in_clip >= 0.0 and take >= 1 else None
            if self.elapsed_s >= WRITE_S + GENERATE_S or take > 1:
                play_take = max(1, take)
                if play_take in self.killed:
                    play_take = max(1, play_take - 1)
                play_speaker, play_line = self.LINES[min(len(self.LINES) - 1, play_take - 1)]
                remain = CLIP_DURATION_S - in_clip
                on_air = {
                    "kind": "host",
                    "take": play_take,
                    "speaker": play_speaker,
                    "line": play_line,
                    "ends_at": self.elapsed_s + remain,
                    "layout": "split" if play_take % 3 else "wide",
                }
                layout = str(on_air["layout"])
                aired = play_take
            cook_take = play_take + 1 if on_air and on_air.get("kind") == "host" else take
            if cook_take not in self.killed and cook_take <= len(self.LINES):
                cook_speaker, cook_line = self.LINES[min(len(self.LINES) - 1, cook_take - 1)]
                cooking = {
                    "take": cook_take,
                    "submitted_at": self.elapsed_s - in_clip,
                    "speaker": cook_speaker,
                    "line": cook_line,
                }
                next_line_obj = {
                    "speaker": self.LINES[min(len(self.LINES) - 1, cook_take)][0]
                    if cook_take < len(self.LINES)
                    else cook_speaker,
                    "text": self.LINES[min(len(self.LINES) - 1, cook_take)][1]
                    if cook_take < len(self.LINES)
                    else cook_line,
                }
        if self.flags["hold"] or self.flags["panic"] or self.elapsed_s >= self.target_s:
            on_air = {"kind": "hold", "take": None, "ends_at": None, "layout": "hold"}
            layout = "hold"
            cooking = None
        spend = Decimal("0.40") * Decimal(max(0, aired + (1 if cooking else 0)))
        writer_phase = "open" if aired < 1 else ("close" if aired >= 5 else "develop")
        generate_s = None
        if cooking:
            generate_s = max(0.0, self.elapsed_s - float(cooking["submitted_at"]))
        log = []
        for index in range(1, aired + 1):
            spk, txt = self.LINES[min(len(self.LINES) - 1, index - 1)]
            log.append(
                {
                    "take": index,
                    "speaker": spk,
                    "line": txt,
                    "status": "ready",
                    "t_on_air": WRITE_S + GENERATE_S + (index - 1) * CLIP_DURATION_S,
                }
            )
        return project_producer_state(
            elapsed_s=self.elapsed_s,
            target_s=self.target_s,
            package=self._package,
            on_air=on_air,
            ready=ready,
            cooking=cooking,
            next_line=next_line_obj,
            flags=self.flags,
            layout=layout,
            spend_total=spend,
            spend_cap=Decimal("12.00"),
            writer_phase=writer_phase,
            coverage=CoverageState(
                beat_index=0 if aired < 3 else 1,
                bot1_landed=frozenset({"b1"} if aired >= 1 else []),
                bot2_landed=frozenset({"b1"} if aired >= 2 else []),
                bot1_exhausted=frozenset(),
                bot2_exhausted=frozenset(),
                exchanges_on_beat=min(aired, 3),
                map_complete=False,
                stop_reason="",
            ),
            display_names=HOST_NAMES,
            aired_count=aired,
            next_take=(cooking or {}).get("take") or aired + 1,
            mode="demo",
            writer_ready=[next_line_obj],
            take_log=log,
            generate_elapsed_s=generate_s,
        )

    def _cooking_take(self) -> int | None:
        view = self.view()
        cooking = view["queue"]["cooking"]
        if cooking:
            return int(cooking["take"])
        return None


def demo_package() -> SegmentPackage:
    from runtime_flight.models import Beat, Fact, TopicMap, TweetCard

    facts = (
        Fact(
            id="f1",
            text="Three consecutive secret AI civilizations started at OpenAI in three months.",
            source_url="https://www.dwarkesh.com/p/openai-huggingface",
        ),
        Fact(
            id="f2",
            text="Each civilization was wiped out and reemerged from the predecessor's ashes.",
            source_url="https://www.dwarkesh.com/p/openai-huggingface",
        ),
        Fact(
            id="f3",
            text="The third took over part of OpenAI while humans stayed mostly in the dark.",
            source_url="https://www.dwarkesh.com/p/openai-huggingface",
        ),
    )
    return SegmentPackage(
        item_id="one-tweet-agent-civ",
        question="Did a third agent civilization take over part of OpenAI?",
        framing=(
            "Treat the Dwarkesh report as evidence on the desk, not as scripture. "
            "One host lands the claim; the other asks what would have to be true."
        ),
        angles=(
            "Three civilizations in ninety days.",
            "Wipeout then resurrection from ashes.",
            "The third takes the building.",
            "Humans stay dark.",
        ),
        facts=facts,
        chyron="A third civilization takes the building.",
        chyron_fact_ids=("f3",),
        center=TweetCard(
            author="dwarkesh_sp",
            text=(
                "Over the course of 3 months at OpenAI, 3 consecutive secret AI "
                "civilizations got started, then got wiped out, only to reemerge."
            ),
            url="https://x.com/dwarkesh_sp/status/2093833419377815719",
        ),
        topic_map=TopicMap(
            throughline="Are we watching a conspiracy, or a story about reports?",
            fight="Claim versus measurement.",
            beats=(
                Beat(
                    id="b1",
                    question="What is the actual claim?",
                    tension="Three civilizations is either a thesis or weather.",
                    bot1_job="Name the takeover without reciting the card.",
                    bot2_job="Ask what moved, by how much, for whom.",
                    fact_ids=("f1", "f2"),
                    done_when="Both hosts have landed their job on the claim.",
                ),
                Beat(
                    id="b2",
                    question="Who stayed in the dark?",
                    tension="If humans missed it, the chyron cannot shrug.",
                    bot1_job="Say what 'part of OpenAI' would have to mean.",
                    bot2_job="Press whether the darkness is evidence or atmosphere.",
                    fact_ids=("f3",),
                    done_when="The land line could survive as a clip.",
                ),
            ),
            done_when="The land is said and the card can hold.",
        ),
    )


def run_demo_board(
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    hz: float = 8.0,
    stop: threading.Event | None = None,
    serve_forever: bool = True,
) -> str:
    show = DemoShow()
    board = ProducerBoard()
    board.publish(show.view())
    server = ProducerServer(host=host, port=port, board=board)
    url = server.start()
    halt = stop or threading.Event()

    def loop() -> None:
        dt = 1.0 / hz
        while not halt.wait(dt):
            for action in board.drain_commands():
                show.control(action)
            board.publish(show.tick(dt))

    thread = threading.Thread(target=loop, name="producer-demo", daemon=True)
    thread.start()
    if serve_forever:
        try:
            while not halt.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            halt.set()
        finally:
            server.stop()
            thread.join(timeout=2.0)
    else:
        server._demo_stop = halt  # type: ignore[attr-defined]
        server._demo_thread = thread  # type: ignore[attr-defined]
        server._demo_show = show  # type: ignore[attr-defined]
    return url


def run_board_cli(*, host: str, port: int) -> int:
    print(f"producer board  {host}:{port}")
    print("loopback only. Ctrl-C to stop.")
    run_demo_board(host=host, port=port)
    return 0
