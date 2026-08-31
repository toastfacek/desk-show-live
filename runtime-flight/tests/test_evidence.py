"""Task 14: immutable live flight evidence bundle."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from runtime_flight.evidence import (
    EvidenceError,
    FlightEvidence,
    configured_secrets,
    wait_for_recording_stable,
    write_evidence_bundle,
)
from runtime_flight.models import Fact, SegmentPackage, TweetCard
from runtime_flight.source import (
    EXPECTED_AUTHOR,
    EXPECTED_LINKED_URL,
    EXPECTED_TWEET_ID,
    EXPECTED_TWEET_URL,
)

from test_source import _write_source_files

SECRET_API = "sk-evidence-secret-api-key"
SECRET_OBS = "obs-evidence-password-secret"
SECRET_FAL = "fal-evidence-key-secret"
BASELINE_ID = "baseline-live-locked-id"
FRAME = "https://v3.fal.media/files/frame-{take}.png"


def _package() -> SegmentPackage:
    return SegmentPackage(
        item_id=EXPECTED_TWEET_ID,
        question="What happened to the secret AI civilizations?",
        framing="A reviewed account of three wiped-out agent societies.",
        angles=("scope", "takeover"),
        facts=(
            Fact(
                id="f1",
                text="Three secret AI civilizations started and were wiped out.",
                source_url=EXPECTED_TWEET_URL,
            ),
            Fact(
                id="f2",
                text="The article retells the OpenAI and Hugging Face story.",
                source_url=EXPECTED_LINKED_URL,
            ),
        ),
        chyron="Secret AI civilizations",
        chyron_fact_ids=("f1",),
        center=TweetCard(
            author=EXPECTED_AUTHOR,
            text="Hello café\nworld",
            url=EXPECTED_TWEET_URL,
        ),
    )


def _takes(count: int = 12) -> list[dict]:
    rows = []
    for take in range(1, count + 1):
        rows.append(
            {
                "take": take,
                "line": f"BOT line {take}",
                "speaker": "BOT1" if take % 2 else "BOT2",
                "clip": f"{take:03d}.mp4",
                "status": "ready",
                "layout_on_air": "wide",
                "t_submit": float((take - 1) * 5),
                "t_ready": float((take - 1) * 5 + 4),
                "t_on_air": float((take - 1) * 5),
                "anchor": "hero" if take == 1 else "chain",
                "image_url": "hero" if take == 1 else FRAME.format(take=take - 1),
                "frame_url": FRAME.format(take=take),
                "prompt": f"Active host voice: Low, measured.\nDialogue: line {take}",
                "request_id": f"req-{take}",
            }
        )
    return rows


def _events() -> list[dict]:
    return [
        {"t": 0.0, "kind": "stream_status", "active": False},
        {"t": 1.0, "kind": "stream_status", "active": False},
        {"t": 0.0, "kind": "submit", "take": 1, "anchor": "hero", "speaker": "BOT1"},
        {"t": 4.0, "kind": "ready", "take": 1},
        {"t": 90.0, "kind": "programme_hold"},
    ]


def _fal_requests(takes: list[dict]) -> list[dict]:
    return [
        {
            "take": row["take"],
            "request_id": row["request_id"],
            "prompt": row["prompt"],
            "anchor": row["anchor"],
            "image_url": row["image_url"],
            "speaker": row["speaker"],
            "reserved_cost_usd": "0.40",
            "arguments_sha256": "a" * 64,
        }
        for row in takes
    ]


def _reservations(count: int = 12) -> list[dict]:
    return [
        {
            "id": f"take-{take}-attempt-1",
            "take": take,
            "attempt": 1,
            "reserved_cost_usd": "0.40",
            "calculation": "0.08 * 5",
        }
        for take in range(1, count + 1)
    ]


def make_evidence(
    tmp_path: Path,
    *,
    flight_id: str = "flight-test",
    leak: str | None = None,
    recording: bool = True,
    take_count: int = 12,
) -> FlightEvidence:
    written = _write_source_files(tmp_path / "inputs")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"baseline_id": BASELINE_ID, "hero": {"path": "hero.png"}}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    recording_path = None
    if recording:
        recording_path = tmp_path / "show.mkv"
        recording_path.write_bytes(b"recording-bytes")
    takes = _takes(take_count)
    if leak:
        takes[0]["line"] = leak
    lock = json.loads(written["lock"].read_text(encoding="utf-8"))
    return FlightEvidence(
        flight_id=flight_id,
        baseline_id=BASELINE_ID,
        mode="live",
        target_duration_s=90,
        stop_reason=None,
        baseline_manifest_path=manifest,
        source_packet_path=written["packet"],
        source_lock_path=written["lock"],
        excerpt_path=written["excerpt"],
        package=_package(),
        takes=takes,
        events=_events(),
        fal_requests=_fal_requests(takes),
        recording_path=recording_path,
        recording_duration_s=90.0,
        reserved_cost_upper_bound_usd=Decimal("4.80"),
        spend_rate_768p_usd_per_s=Decimal("0.08"),
        spend_duration_s=5,
        reservations=_reservations(take_count),
        source_hashes={
            "source_packet_sha256": lock["source_packet_sha256"],
            "tweet_text_sha256": lock["tweet_text_sha256"],
            "excerpt_sha256": lock["excerpt_sha256"],
        },
        config={"text_api_key": SECRET_API, "obs_password": SECRET_OBS},
        secrets=(SECRET_API, SECRET_OBS, SECRET_FAL),
        spend_cap_usd=Decimal("12.00"),
        text_requests=8,
        text_request_limit=24,
        t_end=90.0,
        beats=[
            {"at": float(i * 5), "layout": "wide" if i % 2 == 0 else "split"}
            for i in range(take_count)
        ]
        + [{"at": 90.0, "layout": "hold"}],
    )


def test_wait_for_recording_stable_uses_two_one_second_checks(tmp_path: Path) -> None:
    path = tmp_path / "rec.mkv"
    path.write_bytes(b"x")
    slept: list[float] = []

    def sleep(dt: float) -> None:
        slept.append(dt)
        if len(slept) == 1:
            path.write_bytes(b"xy")

    size = wait_for_recording_stable(path, sleep=sleep)
    assert size == 2
    assert len(slept) >= 2
    assert all(item == 1.0 for item in slept)


def test_write_evidence_bundle_hashes_every_present_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAL_KEY", SECRET_FAL)
    evidence = make_evidence(tmp_path)
    bundle = write_evidence_bundle(tmp_path / "out" / "flights", evidence, sleep=lambda _dt: None)

    expected = [
        "flight.json",
        "config.redacted.json",
        "baseline/manifest.json",
        "input/source_packet.json",
        "input/source_packet.lock.json",
        "input/dwarkesh-agent-civilizations.txt",
        "segment/package.json",
        "logs/takes.jsonl",
        "logs/events.jsonl",
        "logs/fal_requests.jsonl",
        "recording.json",
        "hashes.json",
    ]
    for name in expected:
        assert (bundle / name).is_file(), name
    assert not (bundle / "voice_review.json").exists()

    flight = json.loads((bundle / "flight.json").read_text(encoding="utf-8"))
    assert flight["baseline_id"] == BASELINE_ID
    assert flight["verdict"] is None
    assert flight["reserved_cost_upper_bound_usd"] == "4.80"
    assert flight["spend"]["rate_effective_date"] == "2026-08-30"
    assert flight["scene_intervals"]
    assert flight["request_intervals"]
    assert flight["anchors"][0]["anchor"] == "hero"

    hashes = json.loads((bundle / "hashes.json").read_text(encoding="utf-8"))
    for name in expected:
        if name == "hashes.json":
            continue
        digest = hashlib.sha256((bundle / name).read_bytes()).hexdigest()
        assert hashes[name] == digest


def test_evidence_scans_configured_secrets_not_baseline_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAL_KEY", SECRET_FAL)
    evidence = make_evidence(tmp_path)
    bundle = write_evidence_bundle(tmp_path / "out" / "flights", evidence, sleep=lambda _dt: None)
    text = (bundle / "flight.json").read_text(encoding="utf-8")
    assert BASELINE_ID in text
    assert SECRET_API not in text
    assert SECRET_OBS not in text
    assert SECRET_FAL not in text
    assert SECRET_API not in configured_secrets({"baseline_id": BASELINE_ID})


def test_evidence_refuses_secret_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAL_KEY", SECRET_FAL)
    evidence = make_evidence(tmp_path, leak=SECRET_API)
    with pytest.raises(EvidenceError, match="secret"):
        write_evidence_bundle(tmp_path / "out" / "flights", evidence, sleep=lambda _dt: None)


def test_evidence_does_not_fabricate_voice_review(tmp_path: Path) -> None:
    evidence = make_evidence(tmp_path)
    bundle = write_evidence_bundle(tmp_path / "out" / "flights", evidence, sleep=lambda _dt: None)
    assert not (bundle / "voice_review.json").exists()
    hashes = json.loads((bundle / "hashes.json").read_text(encoding="utf-8"))
    assert "voice_review.json" not in hashes
