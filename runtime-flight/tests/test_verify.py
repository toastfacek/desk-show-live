"""Task 14B: independent flight evidence verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from runtime_flight.evidence import write_evidence_bundle
from runtime_flight.verify import (
    ARCH_KEYS,
    VOICE_KEYS,
    verify_bundle,
)
from test_evidence import BASELINE_ID, make_evidence


def _probe(duration_s: float = 90.0) -> dict:
    return {
        "duration_s": duration_s,
        "width": 1920,
        "height": 1080,
        "has_video": True,
        "has_audio": True,
    }


def _write_bundle(tmp_path: Path, **kwargs):
    evidence = make_evidence(tmp_path, **kwargs)
    return write_evidence_bundle(tmp_path / "out" / "flights", evidence, sleep=lambda _dt: None)


def _write_scores(bundle: Path, *, voice: int = 4, arch: int = 4, omit: str | None = None) -> None:
    payload = {key: voice for key in VOICE_KEYS}
    payload.update({key: arch for key in ARCH_KEYS})
    if omit:
        payload.pop(omit)
    (bundle / "voice_review.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_automated_passes_without_voice_review_and_leaves_verdict_null(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path)
    result = verify_bundle(
        bundle,
        mode="automated",
        ffprobe=lambda _path: _probe(),
        ffmpeg_filter=lambda _path, _filter: "",
        secrets=(),
    )
    assert result.ok is True
    assert result.exit_code == 0
    assert result.verdict is None
    flight = json.loads((bundle / "flight.json").read_text(encoding="utf-8"))
    assert flight["verdict"] is None
    assert flight["baseline_id"] == BASELINE_ID
    assert not (bundle / "voice_review.json").exists()


def test_final_pass_writes_f_pass(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path)
    _write_scores(bundle)
    result = verify_bundle(
        bundle,
        mode="final",
        ffprobe=lambda _path: _probe(),
        ffmpeg_filter=lambda _path, _filter: "",
        secrets=(),
    )
    assert result.ok is True
    assert result.exit_code == 0
    assert result.verdict == "F-PASS"
    flight = json.loads((bundle / "flight.json").read_text(encoding="utf-8"))
    assert flight["verdict"] == "F-PASS"


def test_final_voice_fail_is_f_path(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path)
    _write_scores(bundle, voice=2, arch=4)
    result = verify_bundle(
        bundle,
        mode="final",
        ffprobe=lambda _path: _probe(),
        ffmpeg_filter=lambda _path, _filter: "",
        secrets=(),
    )
    assert result.verdict == "F-PATH"
    assert result.exit_code == 0


def test_final_arch_fail_is_f_arch_even_if_voice_also_low(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path)
    _write_scores(bundle, voice=2, arch=2)
    result = verify_bundle(
        bundle,
        mode="final",
        ffprobe=lambda _path: _probe(),
        ffmpeg_filter=lambda _path, _filter: "",
        secrets=(),
    )
    assert result.verdict == "F-ARCH"
    assert result.exit_code == 0


def test_final_missing_scores_is_inconclusive(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path)
    result = verify_bundle(
        bundle,
        mode="final",
        ffprobe=lambda _path: _probe(),
        ffmpeg_filter=lambda _path, _filter: "",
        secrets=(),
    )
    assert result.verdict == "F-INCONCLUSIVE"
    assert result.exit_code == 1


def test_machine_gate_failure_is_f_fail(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path, take_count=3)
    result = verify_bundle(
        bundle,
        mode="automated",
        ffprobe=lambda _path: _probe(),
        ffmpeg_filter=lambda _path, _filter: "",
        secrets=(),
    )
    assert result.ok is False
    assert result.exit_code == 1
    assert result.verdict == "F-FAIL"
    assert any("aired" in item for item in result.failures)


def test_blackdetect_fails(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path)
    result = verify_bundle(
        bundle,
        mode="automated",
        ffprobe=lambda _path: _probe(),
        ffmpeg_filter=lambda _path, filt: (
            "black_start:1.0 black_end:1.4 black_duration:0.4" if "blackdetect" in filt else ""
        ),
        secrets=(),
    )
    assert result.verdict == "F-FAIL"
    assert any("blackdetect" in item for item in result.failures)


def test_freeze_on_host_fails_but_hold_is_covered(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path)
    host_fail = verify_bundle(
        bundle,
        mode="automated",
        ffprobe=lambda _path: _probe(),
        ffmpeg_filter=lambda _path, filt: (
            "freeze_start: 0.0\nfreeze_end: 2.0 freeze_duration: 2.0"
            if "freezedetect" in filt
            else ""
        ),
        secrets=(),
    )
    assert host_fail.verdict == "F-FAIL"
    assert any("freezedetect" in item for item in host_fail.failures)

    flight = json.loads((bundle / "flight.json").read_text(encoding="utf-8"))
    flight["scene_intervals"] = [{"layout": "hold", "kind": "hold", "t_start": 0.0, "t_end": 5.0}]
    flight["watchdog_visible_intervals"] = [
        {"t_start": 0.0, "t_end": 5.0, "reason": "hold"}
    ]
    (bundle / "flight.json").write_text(json.dumps(flight, indent=2) + "\n", encoding="utf-8")
    from runtime_flight.evidence import write_hashes

    write_hashes(bundle)
    covered = verify_bundle(
        bundle,
        mode="automated",
        ffprobe=lambda _path: _probe(),
        ffmpeg_filter=lambda _path, filt: (
            "freeze_start: 0.0\nfreeze_end: 2.0 freeze_duration: 2.0"
            if "freezedetect" in filt
            else ""
        ),
        secrets=(),
    )
    assert covered.ok is True
    assert covered.verdict is None


def test_hold_over_15s_fails(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path)
    flight = json.loads((bundle / "flight.json").read_text(encoding="utf-8"))
    flight["scene_intervals"].append(
        {"layout": "card_full", "kind": "card", "t_start": 0.0, "t_end": 20.0}
    )
    (bundle / "flight.json").write_text(json.dumps(flight, indent=2) + "\n", encoding="utf-8")
    from runtime_flight.evidence import write_hashes

    write_hashes(bundle)
    result = verify_bundle(
        bundle,
        mode="automated",
        ffprobe=lambda _path: _probe(),
        ffmpeg_filter=lambda _path, _filter: "",
        secrets=(),
    )
    assert result.verdict == "F-FAIL"
    assert any("hold" in item for item in result.failures)
