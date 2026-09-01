"""PLAYHEAD (§2): pluggable output (DECISIONS.md D1).

- MpvPlayhead: mpv --idle --keep-open --input-ipc-server; append via IPC. --keep-open
  gives the hold pattern for free: playlist runs dry → freeze on last frame. This is
  also the OBS path (OBS window-captures the mpv window; see OBS.md).
- FolderPlayhead: no player; maintains out/ready/playlist.ffconcat for an external
  consumer (OBS VLC source, ffplay, ffmpeg concat).
- NullPlayhead: headless (experiments, tests).
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path


class NullPlayhead:
    async def start(self) -> None: ...
    async def append(self, path: str | Path) -> None: ...
    async def close(self) -> None: ...


class FolderPlayhead(NullPlayhead):
    def __init__(self, ready_dir: str | Path):
        self.playlist = Path(ready_dir) / "playlist.ffconcat"

    async def start(self) -> None:
        if not self.playlist.exists():
            self.playlist.write_text("ffconcat version 1.0\n")

    async def append(self, path: str | Path) -> None:
        name = str(Path(path).resolve()).replace("'", "'\\''")
        with open(self.playlist, "a") as f:
            f.write(f"file '{name}'\n")


class MpvPlayhead(NullPlayhead):
    def __init__(self, socket_path: str, extra_args: list[str] | None = None):
        self.socket_path = socket_path
        self.extra_args = extra_args or []
        self._proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        if shutil.which("mpv") is None:
            raise RuntimeError(
                "mpv not found. Install mpv, or set player: folder|none in config.yaml."
            )
        Path(self.socket_path).unlink(missing_ok=True)
        self._proc = await asyncio.create_subprocess_exec(
            "mpv",
            "--idle=yes",
            "--keep-open=yes",
            "--force-window=yes",
            f"--input-ipc-server={self.socket_path}",
            *self.extra_args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        for _ in range(50):  # wait for the IPC socket (≤5s)
            if Path(self.socket_path).exists():
                return
            await asyncio.sleep(0.1)
        raise RuntimeError("mpv IPC socket never appeared")

    async def _ipc(self, command: list) -> None:
        reader, writer = await asyncio.open_unix_connection(self.socket_path)
        try:
            writer.write(json.dumps({"command": command}).encode() + b"\n")
            await writer.drain()
            await asyncio.wait_for(reader.readline(), timeout=2.0)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def append(self, path: str | Path) -> None:
        await self._ipc(["loadfile", str(Path(path).resolve()), "append-play"])

    async def close(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                await self._ipc(["quit"])
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except Exception:
                self._proc.terminate()


def make_playhead(cfg: dict, ready_dir: Path, override: str | None = None):
    kind = (override or cfg.get("player", "mpv")).lower()
    if kind == "mpv":
        m = cfg.get("mpv", {})
        return MpvPlayhead(m.get("socket", "/tmp/deskshow.sock"), m.get("extra_args"))
    if kind == "folder":
        return FolderPlayhead(ready_dir)
    if kind == "none":
        return NullPlayhead()
    raise ValueError(f"unknown player: {kind}")
