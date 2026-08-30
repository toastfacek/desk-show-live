"""Post: last-frame PNG extraction + CDN upload, and the fixed robot audio chain.

PNG, never JPEG, in the last-frame chain — recompression compounds across takes.
The voice filtergraph is frozen (see TDD §6); do not tune it per-take.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import fal_client

logger = logging.getLogger("deskshow.post")

# The fixed broadcast-robot treatment: band-limit + 30Hz modulation + light
# bit-crush. Frozen on purpose so drift in the underlying voice hides beneath it.
ROBOT_VOICE_FILTERGRAPH = (
    "highpass=f=150,lowpass=f=3800,apulsator=hz=30:amount=0.65,"
    "acrusher=bits=10:mode=log:aa=0.6,alimiter=limit=0.9"
)


class PostError(Exception):
    pass


async def run_ffmpeg(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise PostError(f"ffmpeg failed: {stderr.decode(errors='replace')[-2000:]}")


async def extract_last_frame(video_path: Path, frame_path: Path) -> None:
    """ffmpeg -sseof -0.1 -i take.mp4 -frames:v 1 -update 1 frame.png"""
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    await run_ffmpeg(
        "-sseof", "-0.1",
        "-i", str(video_path),
        "-frames:v", "1",
        "-update", "1",
        str(frame_path),
    )


async def upload_frame(frame_path: Path) -> str:
    """Upload the extracted frame to fal's CDN; returns the public URL used as
    the next take's image_url."""
    url = await fal_client.upload_file_async(str(frame_path))
    return url


async def apply_voice_effect(raw_path: Path, treated_path: Path) -> None:
    """Re-mux raw.mp4 through the fixed robot filtergraph, video stream copied."""
    treated_path.parent.mkdir(parents=True, exist_ok=True)
    await run_ffmpeg(
        "-i", str(raw_path),
        "-c:v", "copy",
        "-af", ROBOT_VOICE_FILTERGRAPH,
        str(treated_path),
    )


async def process_take(
    raw_video_path: Path,
    frame_path: Path,
    ready_path: Path,
    voice_effect: bool,
) -> str:
    """Runs frame extraction + upload, and (optionally) the voice effect chain.

    Returns the frame's CDN URL to anchor the next take.
    """
    await extract_last_frame(raw_video_path, frame_path)
    frame_url = await upload_frame(frame_path)

    if voice_effect:
        await apply_voice_effect(raw_video_path, ready_path)
    else:
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        ready_path.write_bytes(raw_video_path.read_bytes())

    return frame_url
