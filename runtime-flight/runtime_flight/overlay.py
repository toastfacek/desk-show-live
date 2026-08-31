"""Loopback tweet overlay and OBS watchdog heartbeat server."""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_OVERLAY_DIR = Path(__file__).resolve().parent.parent / "overlay"
DEFAULT_MAX_STATE_BYTES = 65_536
HEARTBEAT_INTERVAL_S = 0.25
STALE_MS = 1_200

_STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def atomic_write_bytes(path: Path, data: bytes, *, max_bytes: int) -> None:
    if len(data) > max_bytes:
        raise ValueError("state exceeds size limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class OverlayServer:
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        overlay_dir: Path | None = None,
        state_dir: Path | None = None,
        max_state_bytes: int = DEFAULT_MAX_STATE_BYTES,
        heartbeat_interval_s: float = HEARTBEAT_INTERVAL_S,
    ) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("overlay server must bind loopback only")
        self._host = "127.0.0.1" if host == "localhost" else host
        self._port = port
        self._overlay_dir = Path(overlay_dir or DEFAULT_OVERLAY_DIR)
        self._state_dir = Path(state_dir) if state_dir is not None else None
        self._max_state_bytes = max_state_bytes
        self._heartbeat_interval_s = heartbeat_interval_s
        self._lock = threading.Lock()
        self._healthy = True
        self._sequence = 0
        self._card = {"author": "", "text": "", "timestamp": ""}
        self._heartbeat_written_at = time.monotonic()
        self._httpd: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_path: Path | None = None
        self._card_path: Path | None = None
        self._paused = False

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        if self._httpd is None:
            raise RuntimeError("overlay server is not running")
        return int(self._httpd.server_address[1])

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> str:
        if self._httpd is not None:
            return self.url
        if self._state_dir is None:
            self._state_dir = self._overlay_dir / "state"
        self._heartbeat_path = self._state_dir / "heartbeat.json"
        self._card_path = self._state_dir / "card.json"
        with self._lock:
            self._write_heartbeat_locked(increment=True)
            self._write_card_locked()

        handler = _make_handler(self)
        httpd = ThreadingHTTPServer((self._host, self._port), handler)
        httpd.overlay = self  # type: ignore[attr-defined]
        self._httpd = httpd
        self._stop.clear()
        self._http_thread = threading.Thread(
            target=httpd.serve_forever,
            name="overlay-http",
            daemon=True,
        )
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="overlay-heartbeat",
            daemon=True,
        )
        self._http_thread.start()
        self._heartbeat_thread.start()
        return self.url

    def stop(self) -> None:
        self._stop.set()
        httpd = self._httpd
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if self._http_thread is not None:
            self._http_thread.join(timeout=2.0)
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2.0)
        self._httpd = None
        self._http_thread = None
        self._heartbeat_thread = None

    def __enter__(self) -> OverlayServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def set_card(
        self,
        *,
        author: str,
        text: str,
        timestamp: str = "",
    ) -> None:
        with self._lock:
            self._card = {
                "author": author,
                "text": text,
                "timestamp": timestamp,
            }
            self._write_card_locked()

    def set_healthy(self, healthy: bool) -> None:
        with self._lock:
            self._healthy = bool(healthy)
            self._write_heartbeat_locked(increment=True)

    def mark_unhealthy(self) -> None:
        self.set_healthy(False)

    def pause_heartbeat_writer(self) -> None:
        with self._lock:
            self._paused = True

    def heartbeat_response(self) -> dict[str, Any]:
        with self._lock:
            return {
                "sequence": self._sequence,
                "healthy": self._healthy,
                "age_ms": self._age_ms_locked(),
            }

    def card_response(self) -> dict[str, str]:
        with self._lock:
            return dict(self._card)

    def static_bytes(self, filename: str) -> bytes:
        path = (self._overlay_dir / filename).resolve()
        overlay_root = self._overlay_dir.resolve()
        if overlay_root not in path.parents and path != overlay_root:
            raise FileNotFoundError(filename)
        if path.parent != overlay_root:
            raise FileNotFoundError(filename)
        return path.read_bytes()

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self._heartbeat_interval_s):
            with self._lock:
                if self._paused:
                    continue
                self._write_heartbeat_locked(increment=True)

    def _age_ms_locked(self) -> int:
        return int(max(0.0, (time.monotonic() - self._heartbeat_written_at) * 1000))

    def _write_heartbeat_locked(self, *, increment: bool) -> None:
        if increment:
            self._sequence += 1
        payload = {"sequence": self._sequence, "healthy": self._healthy}
        assert self._heartbeat_path is not None
        atomic_write_bytes(
            self._heartbeat_path,
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            max_bytes=self._max_state_bytes,
        )
        self._heartbeat_written_at = time.monotonic()

    def _write_card_locked(self) -> None:
        assert self._card_path is not None
        atomic_write_bytes(
            self._card_path,
            json.dumps(self._card, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            ),
            max_bytes=self._max_state_bytes,
        )


def _make_handler(overlay: OverlayServer) -> type[BaseHTTPRequestHandler]:
    class OverlayHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/heartbeat.json":
                self._send_json(overlay.heartbeat_response())
                return
            if path == "/card.json":
                self._send_json(overlay.card_response())
                return
            static = _STATIC_FILES.get(path)
            if static is None:
                self.send_error(404)
                return
            filename, content_type = static
            try:
                body = overlay.static_bytes(filename)
            except FileNotFoundError:
                self.send_error(404)
                return
            self._send(200, body, content_type)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
            self._send(200, body, "application/json; charset=utf-8")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(body)

    return OverlayHandler
