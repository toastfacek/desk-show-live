"""Task 10: H3 media download, validation, and true final-frame extract."""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import subprocess
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from runtime_flight.media import (
    H3_DURATION_MAX_S,
    H3_DURATION_MIN_S,
    H3_HEIGHT,
    H3_WIDTH,
    MAX_MEDIA_BYTES,
    MediaError,
    download_media,
    extract_final_frame,
    stream_fingerprints,
    validate_media,
)

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _ffmpeg(*args: str) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])


def write_h3_clip(
    path: Path,
    *,
    duration_s: float = 5.0,
    width: int = H3_WIDTH,
    height: int = H3_HEIGHT,
    fps: int = 10,
    audio: str = "tone",
    color: str = "0x1E4D8C",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    video = f"color=c={color}:s={width}x{height}:d={duration_s}:r={fps}"
    args = ["-f", "lavfi", "-i", video]
    if audio == "none":
        args += [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(path),
        ]
        _ffmpeg(*args)
        return path
    if audio == "tone":
        audio_src = f"sine=frequency=440:duration={duration_s}"
    elif audio == "silence":
        audio_src = f"anullsrc=r=44100:cl=mono:d={duration_s}"
    elif audio == "quiet":
        audio_src = f"sine=frequency=440:duration={duration_s},volume=-40dB"
    elif audio == "short_beep":
        audio_src = "sine=frequency=1000:duration=0.3,apad=whole_dur=" + str(duration_s)
    else:
        raise ValueError(f"unknown audio fixture {audio!r}")
    args += [
        "-f",
        "lavfi",
        "-i",
        audio_src,
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    _ffmpeg(*args)
    return path


def write_last_frame_clip(path: Path) -> Path:
    """Red, then yellow in the last 0.3s, green only on the true last frame."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=1344x768:d=4.666667:r=24",
        "-f",
        "lavfi",
        "-i",
        "color=c=yellow:s=1344x768:d=0.291667:r=24",
        "-f",
        "lavfi",
        "-i",
        "color=c=green:s=1344x768:d=0.041667:r=24",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=5",
        "-filter_complex",
        "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map",
        "[v]",
        "-map",
        "3:a",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    )
    return path


def write_undecodable_audio_clip(path: Path) -> Path:
    """Video+audio container whose audio stream has no decoder."""
    write_h3_clip(path)
    data = bytearray(path.read_bytes())
    sample = data.find(b"mp4a")
    if sample < 0:
        raise RuntimeError("fixture mp4 is missing an mp4a audio sample entry")
    data[sample : sample + 4] = b"zzzz"
    esds = data.find(b"esds")
    if esds >= 0:
        data[esds + 8 : esds + 40] = b"\x00" * 32
    path.write_bytes(data)
    return path


async def _open_bytes(
    body: bytes,
    *,
    content_type: str = "video/mp4",
    content_length: str | None = None,
    chunk_size: int = 64,
) -> tuple[Mapping[str, str], AsyncIterator[bytes]]:
    headers: dict[str, str] = {"content-type": content_type}
    if content_length is not None:
        headers["content-length"] = content_length

    async def chunks() -> AsyncIterator[bytes]:
        for index in range(0, len(body), chunk_size):
            yield body[index : index + chunk_size]

    return headers, chunks()


def test_rejects_wrong_mp4_signature(tmp_path: Path) -> None:
    path = tmp_path / "not-mp4.bin"
    path.write_bytes(b"PNG\r\nnot an mp4 container")
    with pytest.raises(MediaError, match="signature|ftyp|mp4"):
        _run(validate_media(path))


def test_rejects_wrong_mime_on_download(tmp_path: Path) -> None:
    dest = tmp_path / "clip.mp4"
    body = write_h3_clip(tmp_path / "src.mp4").read_bytes()

    async def open_stream(_url: str) -> tuple[Mapping[str, str], AsyncIterator[bytes]]:
        return await _open_bytes(body, content_type="image/png")

    with pytest.raises(MediaError, match="MIME|mime|content-type"):
        _run(download_media("https://cdn.example/clip.mp4", dest, open_stream=open_stream))
    assert not dest.exists()


def test_rejects_missing_mime_on_download(tmp_path: Path) -> None:
    dest = tmp_path / "clip.mp4"
    body = write_h3_clip(tmp_path / "src.mp4").read_bytes()

    async def open_stream(_url: str) -> tuple[Mapping[str, str], AsyncIterator[bytes]]:
        return await _open_bytes(body, content_type="")

    with pytest.raises(MediaError, match="MIME|mime|content-type"):
        _run(download_media("https://cdn.example/clip.mp4", dest, open_stream=open_stream))
    assert not dest.exists()


def test_rejects_oversized_download_by_content_length(tmp_path: Path) -> None:
    dest = tmp_path / "clip.mp4"

    async def open_stream(_url: str) -> tuple[Mapping[str, str], AsyncIterator[bytes]]:
        return await _open_bytes(
            b"\x00\x00\x00\x18ftypisom",
            content_length=str(MAX_MEDIA_BYTES + 1),
        )

    with pytest.raises(MediaError, match="size|oversized|too large"):
        _run(download_media("https://cdn.example/clip.mp4", dest, open_stream=open_stream))
    assert not dest.exists()


def test_rejects_oversized_streamed_body(tmp_path: Path) -> None:
    dest = tmp_path / "clip.mp4"
    body = b"\x00\x00\x00\x18ftypisom" + (b"\x00" * 200)

    async def open_stream(_url: str) -> tuple[Mapping[str, str], AsyncIterator[bytes]]:
        return await _open_bytes(body, chunk_size=32)

    with pytest.raises(MediaError, match="size|oversized|too large"):
        _run(
            download_media(
                "https://cdn.example/clip.mp4",
                dest,
                max_bytes=64,
                open_stream=open_stream,
            )
        )
    assert not dest.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_rejects_decode_failure(tmp_path: Path) -> None:
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00" + b"\xff" * 64)
    with pytest.raises(MediaError, match="decode"):
        _run(validate_media(path))


def test_rejects_duration_shorter_than_h3_window(tmp_path: Path) -> None:
    path = write_h3_clip(tmp_path / "short.mp4", duration_s=2.0)
    with pytest.raises(MediaError, match="duration"):
        _run(validate_media(path))


def test_rejects_duration_longer_than_h3_window(tmp_path: Path) -> None:
    path = write_h3_clip(tmp_path / "long.mp4", duration_s=8.0)
    with pytest.raises(MediaError, match="duration"):
        _run(validate_media(path))


def test_validate_accepts_fifteen_second_clip_when_expected(tmp_path: Path) -> None:
    path = write_h3_clip(tmp_path / "long15.mp4", duration_s=15.0)
    probe = _run(validate_media(path, expected_duration_s=15))
    assert 14.7 <= probe.duration_s <= 15.3


def test_rejects_five_second_clip_when_fifteen_expected(tmp_path: Path) -> None:
    path = write_h3_clip(tmp_path / "short5.mp4", duration_s=5.0)
    with pytest.raises(MediaError, match="duration"):
        _run(validate_media(path, expected_duration_s=15))


def test_rejects_dimensions_other_than_1344x768(tmp_path: Path) -> None:
    path = write_h3_clip(tmp_path / "sd.mp4", width=640, height=480)
    with pytest.raises(MediaError, match="1344|768|dimension"):
        _run(validate_media(path))


def test_rejects_missing_audio(tmp_path: Path) -> None:
    path = write_h3_clip(tmp_path / "mute.mp4", audio="none")
    with pytest.raises(MediaError, match="audio"):
        _run(validate_media(path))


def test_rejects_undecodable_audio(tmp_path: Path) -> None:
    path = write_undecodable_audio_clip(tmp_path / "badaudio.mp4")
    with pytest.raises(MediaError, match="audio"):
        _run(validate_media(path))


def test_rejects_silent_audio(tmp_path: Path) -> None:
    path = write_h3_clip(tmp_path / "silent.mp4", audio="silence")
    with pytest.raises(MediaError, match="silent|volume"):
        _run(validate_media(path))


def test_rejects_near_silent_audio_below_minus_35_dbfs(tmp_path: Path) -> None:
    path = write_h3_clip(tmp_path / "quiet.mp4", audio="quiet")
    with pytest.raises(MediaError, match="silent|volume|-35"):
        _run(validate_media(path))


def test_rejects_audio_with_less_than_one_second_nonsilent(tmp_path: Path) -> None:
    path = write_h3_clip(tmp_path / "beep.mp4", audio="short_beep")
    with pytest.raises(MediaError, match="silent|nonsilent|1\\.0"):
        _run(validate_media(path))


def test_download_streams_to_temp_fsyncs_and_renames(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = write_h3_clip(tmp_path / "src.mp4")
    body = src.read_bytes()
    dest = tmp_path / "raw" / "take.mp4"
    fsyncs: list[int] = []
    original_fsync = os.fsync

    def spy_fsync(fd: int) -> None:
        fsyncs.append(fd)
        original_fsync(fd)

    monkeypatch.setattr(os, "fsync", spy_fsync)

    async def open_stream(_url: str) -> tuple[Mapping[str, str], AsyncIterator[bytes]]:
        return await _open_bytes(body, chunk_size=1024)

    result = _run(download_media("https://cdn.example/take.mp4", dest, open_stream=open_stream))
    assert result == dest
    assert dest.is_file()
    assert dest.read_bytes() == body
    assert not dest.with_name(dest.name + ".tmp").exists()
    assert fsyncs
    assert MAX_MEDIA_BYTES >= 50 * 1024 * 1024


def test_validate_accepts_h3_window_clip_and_logs_audio(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = write_h3_clip(tmp_path / "ok.mp4")
    with caplog.at_level(logging.INFO, logger="runtime_flight.media"):
        probe = _run(validate_media(path))
    assert H3_DURATION_MIN_S <= probe.duration_s <= H3_DURATION_MAX_S
    assert probe.width == 1344
    assert probe.height == 768
    assert probe.max_volume_dbfs > -35.0
    assert probe.nonsilent_s >= 1.0
    assert "max_volume_dbfs" in caplog.text
    assert "nonsilent_s" in caplog.text


def test_ffprobe_invocation_uses_required_flags() -> None:
    source = Path(__file__).resolve().parents[1] / "runtime_flight" / "media.py"
    text = source.read_text(encoding="utf-8")
    assert "-v" in text and "error" in text
    assert "-show_streams" in text
    assert "-show_format" in text
    assert "-of" in text and "json" in text


def test_extract_final_frame_uses_true_tail_command() -> None:
    source = Path(__file__).resolve().parents[1] / "runtime_flight" / "media.py"
    text = source.read_text(encoding="utf-8")
    assert "-sseof" in text
    assert '"-1"' in text or "'-1'" in text
    assert "-map" in text and "0:v:0" in text
    assert "-fps_mode" in text and "passthrough" in text
    assert "-update" in text
    assert "-sseof\", \"-0.1\"" not in text
    assert "-frames:v" not in text


def test_extract_final_frame_is_true_last_decoded_frame(tmp_path: Path) -> None:
    clip = write_last_frame_clip(tmp_path / "tail.mp4")
    frame = tmp_path / "frame.png"
    timestamp = _run(extract_final_frame(clip, frame))
    assert frame.is_file()
    with Image.open(frame) as image:
        image.load()
        assert image.size == (1344, 768)
        pixel = image.getpixel((672, 384))
    # yuv420p lavfi green is (0, 127, 0); yellow/red keep a high red channel.
    assert pixel[0] < 40
    assert pixel[1] >= 100
    assert pixel[2] < 40
    assert timestamp > 4.5


def test_extract_rejects_png_with_wrong_dimensions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clip = write_h3_clip(tmp_path / "ok.mp4")
    frame = tmp_path / "frame.png"

    async def fake_ffmpeg(*args: str) -> str:
        Image.new("RGB", (640, 480), (0, 255, 0)).save(frame, format="PNG")
        return ""

    monkeypatch.setattr("runtime_flight.media.run_ffmpeg", fake_ffmpeg)
    with pytest.raises(MediaError, match="1344|768|dimension"):
        _run(extract_final_frame(clip, frame))


def test_stream_fingerprints_include_video_and_audio(tmp_path: Path) -> None:
    path = write_h3_clip(tmp_path / "ok.mp4")
    video, audio = _run(stream_fingerprints(path))
    assert video.codec_type == "video"
    assert video.codec_name
    assert video.width == 1344
    assert video.height == 768
    assert audio.codec_type == "audio"
    assert audio.codec_name
    assert audio.sample_rate
    assert audio.channels


def test_media_module_does_not_import_root_scaffold() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "media.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN_ROOT_MODULES)
    assert "fal_client" not in imported
    assert "ROBOT_VOICE" not in source
    assert "acrusher" not in source
    assert "from post" not in source
