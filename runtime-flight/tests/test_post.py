"""Task 10: frame upload seam and atomic ready copy of raw H3 media."""

from __future__ import annotations

import ast
import asyncio
import hashlib
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from runtime_flight.media import MediaError, stream_fingerprints, validate_media
from runtime_flight.post import PostError, copy_to_ready, process_take, upload_frame
from test_media import write_h3_clip

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}

FRAME_URL = "https://v3.fal.media/files/exact-final-frame.png"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _upload(path: Path) -> str:
    assert path.is_file()
    with Image.open(path) as image:
        image.load()
        assert image.size == (1344, 768)
    return FRAME_URL


def test_upload_frame_returns_exact_url_from_seam(tmp_path: Path) -> None:
    frame = tmp_path / "frame.png"
    Image.new("RGB", (1344, 768), (10, 20, 30)).save(frame, format="PNG")
    url = _run(upload_frame(frame, upload=_upload))
    assert url == FRAME_URL


def test_upload_frame_rejects_empty_url(tmp_path: Path) -> None:
    frame = tmp_path / "frame.png"
    Image.new("RGB", (1344, 768), (10, 20, 30)).save(frame, format="PNG")

    async def empty(_path: Path) -> str:
        return ""

    with pytest.raises(PostError, match="url|URL"):
        _run(upload_frame(frame, upload=empty))


def test_ready_copy_is_byte_identical_and_keeps_fingerprints(tmp_path: Path) -> None:
    raw = write_h3_clip(tmp_path / "raw.mp4")
    ready = tmp_path / "ready" / "take.mp4"
    copied = _run(copy_to_ready(raw, ready))
    assert copied == ready
    assert ready.is_file()
    assert hashlib.sha256(ready.read_bytes()).hexdigest() == hashlib.sha256(raw.read_bytes()).hexdigest()
    raw_fp = _run(stream_fingerprints(raw))
    ready_fp = _run(stream_fingerprints(ready))
    assert ready_fp == raw_fp


def test_ready_copy_is_atomic_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = write_h3_clip(tmp_path / "raw.mp4")
    ready = tmp_path / "ready" / "take.mp4"
    replacements: list[tuple[str, str]] = []
    original_replace = __import__("os").replace

    def spy_replace(src: str | Path, dst: str | Path) -> None:
        replacements.append((str(src), str(dst)))
        original_replace(src, dst)

    monkeypatch.setattr("os.replace", spy_replace)
    _run(copy_to_ready(raw, ready))
    assert replacements
    assert any(str(ready) == dst for _src, dst in replacements)
    assert not ready.with_name(ready.name + ".tmp").exists()


def test_process_take_validates_extracts_uploads_and_copies(tmp_path: Path) -> None:
    raw = write_h3_clip(tmp_path / "raw.mp4")
    frame = tmp_path / "frames" / "take.png"
    ready = tmp_path / "ready" / "take.mp4"
    result = _run(process_take(raw, frame, ready, upload=_upload))
    assert result.frame_url == FRAME_URL
    assert result.frame_path == frame
    assert result.ready_path == ready
    assert result.final_frame_timestamp_s > 0
    assert frame.is_file()
    assert ready.is_file()
    assert hashlib.sha256(ready.read_bytes()).hexdigest() == hashlib.sha256(raw.read_bytes()).hexdigest()
    with Image.open(frame) as image:
        image.load()
        assert image.size == (1344, 768)
    probe = _run(validate_media(ready))
    assert probe.video_fingerprint == result.video_fingerprint
    assert probe.audio_fingerprint == result.audio_fingerprint
    assert result.stages_s is not None
    assert set(result.stages_s) == {"validate", "extract", "upload", "copy"}
    assert all(value >= 0 for value in result.stages_s.values())


def test_failed_media_check_never_enters_ready(tmp_path: Path) -> None:
    raw = write_h3_clip(tmp_path / "silent.mp4", audio="silence")
    frame = tmp_path / "frames" / "take.png"
    ready = tmp_path / "ready" / "take.mp4"
    with pytest.raises(MediaError):
        _run(process_take(raw, frame, ready, upload=_upload))
    assert not ready.exists()
    assert not list((tmp_path / "ready").glob("*")) if (tmp_path / "ready").exists() else True


def test_failed_duration_check_never_enters_ready(tmp_path: Path) -> None:
    raw = write_h3_clip(tmp_path / "short.mp4", duration_s=2.0)
    ready = tmp_path / "ready" / "take.mp4"
    with pytest.raises(MediaError):
        _run(process_take(raw, tmp_path / "frame.png", ready, upload=_upload))
    assert not ready.exists()


def test_failed_upload_never_enters_ready(tmp_path: Path) -> None:
    raw = write_h3_clip(tmp_path / "raw.mp4")
    ready = tmp_path / "ready" / "take.mp4"

    async def boom(_path: Path) -> str:
        raise PostError("upload failed")

    with pytest.raises(PostError, match="upload failed"):
        _run(process_take(raw, tmp_path / "frame.png", ready, upload=boom))
    assert not ready.exists()


def test_process_take_does_not_remux_or_filter(tmp_path: Path) -> None:
    raw = write_h3_clip(tmp_path / "raw.mp4")
    ready = tmp_path / "ready" / "take.mp4"
    _run(process_take(raw, tmp_path / "frame.png", ready, upload=_upload))
    source = Path(__file__).resolve().parents[1] / "runtime_flight" / "post.py"
    text = source.read_text(encoding="utf-8")
    assert "ROBOT_VOICE" not in text
    assert "acrusher" not in text
    assert "apulsator" not in text
    assert "highpass=f=150" not in text
    assert "-af" not in text
    assert "-c:v" not in text
    assert hashlib.sha256(ready.read_bytes()).digest() == hashlib.sha256(raw.read_bytes()).digest()


def test_post_module_does_not_import_root_scaffold() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "post.py"
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
    assert "from post" not in source
    assert "import post" not in source
    assert "ROBOT_VOICE_FILTERGRAPH" not in source
