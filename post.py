"""POST (§2): two ffmpeg jobs per take.

1. Last-frame extract as PNG (never JPEG — recompression compounds across the chain),
   uploaded to fal's CDN; that URL is the next take's image_url.
2. Audio: raw track always kept; with voice_effect on, the ready-queue copy is re-muxed
   through the fixed robot filtergraph (§6).
"""
from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path


async def _run(cmd: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {err.decode()[-400:]}")


async def extract_last_frame(mp4: str | Path, png: str | Path) -> None:
    await _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-sseof", "-0.1", "-i", str(mp4),
        "-frames:v", "1", "-update", "1", str(png),
    ])


async def upload_frame(png: str | Path, dry_run: bool = False) -> str:
    """fal CDN upload (no S3 to stand up). Dry-run: a file:// URL, unused anyway."""
    if dry_run:
        return Path(png).resolve().as_uri()
    import fal_client

    return await fal_client.upload_file_async(str(png))


async def apply_voice_effect(raw_mp4: str | Path, out_mp4: str | Path, filtergraph: str) -> None:
    await _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(raw_mp4),
        "-c:v", "copy", "-af", filtergraph,
        str(out_mp4),
    ])


async def post_take(
    raw_mp4: Path,
    ready_mp4: Path,
    frame_png: Path,
    voice_effect: bool,
    filtergraph: str,
    dry_run: bool = False,
) -> dict:
    """Full post step. Returns {'frame_url', 'frame_ok', 't_post_s'}.
    Frame extract/upload failure is reported, never raised — caller falls back to the
    hero anchor and never stalls the loop (§5)."""
    t0 = time.monotonic()

    if voice_effect:
        await apply_voice_effect(raw_mp4, ready_mp4, filtergraph)
    else:
        shutil.copyfile(raw_mp4, ready_mp4)

    frame_url, frame_ok = "", False
    try:
        await extract_last_frame(raw_mp4, frame_png)
        frame_url = await upload_frame(frame_png, dry_run=dry_run)
        frame_ok = True
    except Exception:
        pass  # hero fallback happens in the loop

    return {
        "frame_url": frame_url,
        "frame_ok": frame_ok,
        "t_post_s": round(time.monotonic() - t0, 3),
    }
