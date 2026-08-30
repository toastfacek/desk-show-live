"""Playhead: mpv IPC. --keep-open gives the hold pattern (freeze on last frame)
for free when the ready queue runs dry. No custom player code beyond IPC.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger("deskshow.playhead")


class Playhead:
    def __init__(self, ipc_socket: str = "/tmp/deskshow.sock") -> None:
        self._ipc_socket = ipc_socket
        self._proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            "mpv",
            "--idle=yes",
            "--keep-open=yes",
            "--force-window=yes",
            f"--input-ipc-server={self._ipc_socket}",
        )
        # Give mpv a moment to open the IPC socket before the first append.
        await asyncio.sleep(0.5)

    async def append(self, clip_path: Path) -> None:
        await self._send({"command": ["loadfile", str(clip_path), "append-play"]})

    async def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            await self._proc.wait()

    async def _send(self, payload: dict) -> None:
        reader, writer = await asyncio.open_unix_connection(self._ipc_socket)
        try:
            writer.write((json.dumps(payload) + "\n").encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
