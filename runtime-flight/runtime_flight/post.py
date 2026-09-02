"""Upload the extracted final-frame PNG and copy validated raw H3 media to ready."""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from runtime_flight.media import (
    StreamFingerprint,
    extract_final_frame,
    stream_fingerprints,
    validate_media,
)

UploadFn = Callable[[Path], Awaitable[str]]


class PostError(Exception):
    """Raised when frame upload or ready copy cannot be completed."""


@dataclass(frozen=True)
class ProcessedTake:
    frame_url: str
    frame_path: Path
    ready_path: Path
    final_frame_timestamp_s: float
    video_fingerprint: StreamFingerprint
    audio_fingerprint: StreamFingerprint
    stages_s: dict[str, float] | None = None


async def upload_frame(frame_path: Path, *, upload: UploadFn) -> str:
    url = await upload(Path(frame_path))
    if not isinstance(url, str) or url == "":
        raise PostError("upload returned an empty URL")
    return url


async def copy_to_ready(raw_path: Path, ready_path: Path) -> Path:
    raw_path = Path(raw_path)
    ready_path = Path(ready_path)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = ready_path.with_name(ready_path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    try:
        with raw_path.open("rb") as source, tmp.open("wb") as dest:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                dest.write(chunk)
            dest.flush()
            os.fsync(dest.fileno())
        os.replace(tmp, ready_path)
        _fsync_dir(ready_path.parent)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    raw_fp = await stream_fingerprints(raw_path)
    ready_fp = await stream_fingerprints(ready_path)
    if raw_fp != ready_fp:
        ready_path.unlink(missing_ok=True)
        raise PostError("ready copy stream fingerprints do not match raw H3 media")
    return ready_path


async def process_take(
    raw_video_path: Path,
    frame_path: Path,
    ready_path: Path,
    *,
    upload: UploadFn,
    expected_duration_s: int = 5,
) -> ProcessedTake:
    validate_t0 = time.monotonic()
    probe = await validate_media(
        Path(raw_video_path), expected_duration_s=expected_duration_s
    )
    t_validate_s = time.monotonic() - validate_t0
    extract_t0 = time.monotonic()
    timestamp = await extract_final_frame(Path(raw_video_path), Path(frame_path))
    t_extract_s = time.monotonic() - extract_t0
    upload_t0 = time.monotonic()
    frame_url = await upload_frame(Path(frame_path), upload=upload)
    t_upload_s = time.monotonic() - upload_t0
    copy_t0 = time.monotonic()
    copied = await copy_to_ready(Path(raw_video_path), Path(ready_path))
    t_copy_s = time.monotonic() - copy_t0
    return ProcessedTake(
        frame_url=frame_url,
        frame_path=Path(frame_path),
        ready_path=copied,
        final_frame_timestamp_s=timestamp,
        video_fingerprint=probe.video_fingerprint,
        audio_fingerprint=probe.audio_fingerprint,
        stages_s={
            "validate": round(t_validate_s, 3),
            "extract": round(t_extract_s, 3),
            "upload": round(t_upload_s, 3),
            "copy": round(t_copy_s, 3),
        },
    )


def _fsync_dir(directory: Path) -> None:
    dir_fd = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
