"""Download, validate, and extract the true final frame of an H3 take."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger("runtime_flight.media")

MAX_MEDIA_BYTES = 50 * 1024 * 1024
H3_DURATION_MIN_S = 4.7
H3_DURATION_MAX_S = 5.3
H3_WIDTH = 1344
H3_HEIGHT = 768
MAX_VOLUME_MIN_DBFS = -35.0
SILENCE_THRESHOLD_DBFS = -50.0
MIN_NONSILENT_S = 1.0
MP4_MIME = "video/mp4"

OpenStream = Callable[
    [str],
    Awaitable[tuple[Mapping[str, str], AsyncIterator[bytes]]],
]


class MediaError(Exception):
    """Raised when H3 media cannot be downloaded, validated, or framed."""


@dataclass(frozen=True)
class StreamFingerprint:
    codec_type: str
    codec_name: str
    codec_tag_string: str
    extra_data: str
    width: int | None = None
    height: int | None = None
    sample_rate: str | None = None
    channels: int | None = None
    channel_layout: str | None = None


@dataclass(frozen=True)
class MediaProbe:
    duration_s: float
    width: int
    height: int
    max_volume_dbfs: float
    nonsilent_s: float
    final_frame_timestamp_s: float
    video_fingerprint: StreamFingerprint
    audio_fingerprint: StreamFingerprint


async def run_ffmpeg(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    text = stderr.decode(errors="replace")
    if proc.returncode != 0:
        raise MediaError(f"ffmpeg failed: {text[-2000:]}")
    return text


async def run_ffprobe(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise MediaError(
            f"decode failure: {stderr.decode(errors='replace')[-500:]}"
        )
    return stdout.decode()


async def download_media(
    url: str,
    dest: Path,
    *,
    max_bytes: int = MAX_MEDIA_BYTES,
    open_stream: OpenStream | None = None,
) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.unlink(missing_ok=True)
    try:
        if open_stream is not None:
            headers, chunks = await open_stream(url)
            await _write_limited(tmp, headers, chunks, max_bytes)
        else:
            await _httpx_download(url, tmp, max_bytes)
        _require_mp4_signature(tmp.read_bytes()[:64])
        os.replace(tmp, dest)
        _fsync_dir(dest.parent)
        return dest
    except Exception:
        tmp.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        raise


async def validate_media(path: Path) -> MediaProbe:
    path = Path(path)
    _require_mp4_signature(path.read_bytes()[:64])
    payload = await _ffprobe_json(path)
    video = _first_stream(payload, "video")
    if video is None:
        raise MediaError("decode failure: missing video stream")
    audio = _first_stream(payload, "audio")
    if audio is None:
        raise MediaError("audio stream is missing")
    duration_s = _duration_s(payload, video, audio)
    if duration_s < H3_DURATION_MIN_S or duration_s > H3_DURATION_MAX_S:
        raise MediaError(
            f"duration {duration_s:.3f}s is outside {H3_DURATION_MIN_S}–{H3_DURATION_MAX_S}s"
        )
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width != H3_WIDTH or height != H3_HEIGHT:
        raise MediaError(f"dimensions {width}x{height} are not 1344x768")
    max_volume_dbfs, nonsilent_s = await _measure_audio(path, duration_s)
    logger.info(
        "audio measurements max_volume_dbfs=%.2f nonsilent_s=%.3f",
        max_volume_dbfs,
        nonsilent_s,
    )
    if max_volume_dbfs <= MAX_VOLUME_MIN_DBFS:
        raise MediaError(
            f"audio is silent or near-silent: max_volume_dbfs={max_volume_dbfs:.2f} "
            f"(must be above {MAX_VOLUME_MIN_DBFS})"
        )
    if nonsilent_s < MIN_NONSILENT_S:
        raise MediaError(
            f"audio is silent or near-silent: nonsilent_s={nonsilent_s:.3f} "
            f"(must be at least {MIN_NONSILENT_S})"
        )
    video_fp, audio_fp = await stream_fingerprints(path)
    timestamp = await final_frame_timestamp(path)
    return MediaProbe(
        duration_s=duration_s,
        width=width,
        height=height,
        max_volume_dbfs=max_volume_dbfs,
        nonsilent_s=nonsilent_s,
        final_frame_timestamp_s=timestamp,
        video_fingerprint=video_fp,
        audio_fingerprint=audio_fp,
    )


async def extract_final_frame(video_path: Path, frame_path: Path) -> float:
    frame_path = Path(frame_path)
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    await run_ffmpeg(
        "-sseof",
        "-1",
        "-i",
        str(video_path),
        "-map",
        "0:v:0",
        "-fps_mode",
        "passthrough",
        "-update",
        "1",
        str(frame_path),
    )
    _validate_png(frame_path)
    return await final_frame_timestamp(Path(video_path))


async def stream_fingerprints(path: Path) -> tuple[StreamFingerprint, StreamFingerprint]:
    payload = await _ffprobe_json(path)
    video = _first_stream(payload, "video")
    audio = _first_stream(payload, "audio")
    if video is None or audio is None:
        raise MediaError("stream fingerprints require video and audio")
    return _fingerprint(video), _fingerprint(audio)


async def final_frame_timestamp(path: Path) -> float:
    raw = await run_ffprobe(
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "frame=pts_time",
        "-of",
        "csv=p=0",
        str(path),
    )
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        raise MediaError("decode failure: no video frames")
    try:
        return float(lines[-1])
    except ValueError as error:
        raise MediaError("decode failure: invalid frame timestamp") from error


async def _ffprobe_json(path: Path) -> dict[str, Any]:
    raw = await run_ffprobe(
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise MediaError("decode failure: ffprobe json") from error
    if not isinstance(payload, dict):
        raise MediaError("decode failure: ffprobe json")
    return payload


async def _measure_audio(path: Path, duration_s: float) -> tuple[float, float]:
    try:
        log = await run_ffmpeg(
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            f"volumedetect,silencedetect=n={SILENCE_THRESHOLD_DBFS}dB:d=0.05",
            "-f",
            "null",
            "-",
        )
    except MediaError as error:
        raise MediaError("audio is missing or undecodable") from error
    max_volume = _parse_max_volume(log)
    nonsilent = _parse_nonsilent(log, duration_s)
    return max_volume, nonsilent


async def _httpx_download(url: str, tmp: Path, max_bytes: int) -> None:
    import httpx2

    async with httpx2.AsyncClient() as client:
        async with client.stream("GET", url) as response:
            status = response.status_code
            if not isinstance(status, int) or status < 200 or status >= 300:
                raise MediaError("download was not 2xx")
            await _write_limited(tmp, response.headers, response.aiter_bytes(), max_bytes)


async def _write_limited(
    tmp: Path,
    headers: Mapping[str, str],
    chunks: AsyncIterator[bytes],
    max_bytes: int,
) -> None:
    content_type = _header(headers, "content-type")
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type != MP4_MIME:
        raise MediaError(f"unexpected content-type MIME: {content_type!r}")
    length_raw = _header(headers, "content-length")
    if length_raw:
        try:
            length = int(length_raw)
        except ValueError as error:
            raise MediaError("download is oversized") from error
        if length > max_bytes:
            raise MediaError("download is oversized")
    written = 0
    with tmp.open("wb") as handle:
        async for chunk in chunks:
            written += len(chunk)
            if written > max_bytes:
                raise MediaError("download is oversized")
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())


def _require_mp4_signature(prefix: bytes) -> None:
    if len(prefix) < 8 or prefix[4:8] != b"ftyp":
        raise MediaError("file is not a valid MP4 (missing ftyp signature)")


def _first_stream(payload: dict[str, Any], codec_type: str) -> dict[str, Any] | None:
    streams = payload.get("streams")
    if not isinstance(streams, list):
        return None
    for stream in streams:
        if isinstance(stream, dict) and stream.get("codec_type") == codec_type:
            return stream
    return None


def _duration_s(
    payload: dict[str, Any],
    video: dict[str, Any],
    audio: dict[str, Any],
) -> float:
    candidates: list[float] = []
    fmt = payload.get("format")
    if isinstance(fmt, dict):
        _append_duration(candidates, fmt.get("duration"))
    _append_duration(candidates, video.get("duration"))
    _append_duration(candidates, audio.get("duration"))
    if not candidates:
        raise MediaError("decode failure: missing duration")
    return max(candidates)


def _append_duration(candidates: list[float], raw: Any) -> None:
    if raw is None:
        return
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return
    if value > 0:
        candidates.append(value)


def _fingerprint(stream: dict[str, Any]) -> StreamFingerprint:
    sample_rate = stream.get("sample_rate")
    return StreamFingerprint(
        codec_type=str(stream.get("codec_type") or ""),
        codec_name=str(stream.get("codec_name") or ""),
        codec_tag_string=str(stream.get("codec_tag_string") or ""),
        extra_data=str(stream.get("extradata") or stream.get("extra_data") or ""),
        width=int(stream["width"]) if stream.get("width") is not None else None,
        height=int(stream["height"]) if stream.get("height") is not None else None,
        sample_rate=str(sample_rate) if sample_rate is not None else None,
        channels=int(stream["channels"]) if stream.get("channels") is not None else None,
        channel_layout=(
            str(stream["channel_layout"]) if stream.get("channel_layout") is not None else None
        ),
    )


def _parse_max_volume(log: str) -> float:
    match = re.search(r"max_volume:\s+(-inf|-?\d+(?:\.\d+)?)\s+dB", log)
    if not match:
        raise MediaError("audio is missing or undecodable")
    if match.group(1) == "-inf":
        return float("-inf")
    return float(match.group(1))


def _parse_nonsilent(log: str, duration_s: float) -> float:
    starts = [float(value) for value in re.findall(r"silence_start:\s+(-?\d+(?:\.\d+)?)", log)]
    ends = [float(value) for value in re.findall(r"silence_end:\s+(-?\d+(?:\.\d+)?)", log)]
    silent = 0.0
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else duration_s
        silent += max(0.0, end - start)
    return max(0.0, duration_s - silent)


def _validate_png(path: Path) -> None:
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            fmt = image.format
    except MediaError:
        raise
    except Exception as error:
        raise MediaError("extracted frame PNG is undecodable") from error
    if fmt != "PNG":
        raise MediaError("extracted frame is not a PNG")
    if width != H3_WIDTH or height != H3_HEIGHT:
        raise MediaError(f"extracted frame dimensions {width}x{height} are not 1344x768")


def _header(headers: Mapping[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return str(value)
    return ""


def _fsync_dir(directory: Path) -> None:
    dir_fd = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
