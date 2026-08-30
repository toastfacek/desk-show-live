"""Local HTTP server so OBS can load graphics/overlay.html and out/overlay_state.json."""

from __future__ import annotations

import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def start_overlay_server(root: Path, port: int = 8765) -> ThreadingHTTPServer:
    root = Path(root).resolve()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, *_args) -> None:
            return

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        return None
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd
