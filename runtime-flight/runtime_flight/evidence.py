"""Immutable live-flight evidence bundle. Secrets are scanned, never stored."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from runtime_flight.config import REDACTED, RuntimeConfig, redacted_summary
from runtime_flight.models import SegmentPackage

RATE_EFFECTIVE_DATE = "2026-08-30"
BUNDLE_TEXT_NAMES = (
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
)
OPTIONAL_TEXT_NAMES = ("voice_review.json",)
HOST_LAYOUTS = frozenset({"wide", "split", "solo_l", "solo_r"})
HOLD_LAYOUTS = frozenset({"hold", "card_full", "card"})
SleepFn = Callable[[float], None]


class EvidenceError(Exception):
    """Raised when the evidence bundle cannot be written safely."""


@dataclass
class FlightEvidence:
    flight_id: str
    baseline_id: str
    mode: str
    target_duration_s: int
    stop_reason: str | None
    baseline_manifest_path: Path
    source_packet_path: Path
    source_lock_path: Path
    excerpt_path: Path
    package: SegmentPackage | Mapping[str, Any]
    takes: list[dict[str, Any]]
    events: list[dict[str, Any]]
    fal_requests: list[dict[str, Any]]
    recording_path: Path | None
    recording_duration_s: float
    reserved_cost_upper_bound_usd: Decimal
    spend_rate_768p_usd_per_s: Decimal
    spend_duration_s: int
    reservations: list[dict[str, Any]]
    source_hashes: Mapping[str, str]
    config: RuntimeConfig | Mapping[str, Any] | None = None
    beats: list[dict[str, Any]] = field(default_factory=list)
    scene_intervals: list[dict[str, Any]] | None = None
    watchdog_visible_intervals: list[dict[str, Any]] | None = None
    stream_status_samples: list[dict[str, Any]] | None = None
    request_intervals: list[dict[str, Any]] | None = None
    text_requests: int = 0
    text_request_limit: int = 24
    spend_cap_usd: Decimal | None = None
    secrets: tuple[str, ...] = ()
    overlay_unhealthy: bool = False
    t_end: float = 0.0


def package_as_dict(package: SegmentPackage | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(package, SegmentPackage):
        return {
            "item_id": package.item_id,
            "question": package.question,
            "framing": package.framing,
            "angles": list(package.angles),
            "facts": [
                {"id": fact.id, "text": fact.text, "source_url": fact.source_url}
                for fact in package.facts
            ],
            "chyron": package.chyron,
            "chyron_fact_ids": list(package.chyron_fact_ids),
            "center": {
                "author": package.center.author,
                "text": package.center.text,
                "url": package.center.url,
            },
        }
    return dict(package)


def derive_scene_intervals(
    beats: Iterable[dict[str, Any]], t_end: float
) -> list[dict[str, Any]]:
    items = list(beats)
    intervals: list[dict[str, Any]] = []
    for index, beat in enumerate(items):
        start = float(beat.get("at", 0.0))
        stop = float(items[index + 1].get("at", t_end)) if index + 1 < len(items) else float(t_end)
        layout = str(beat.get("layout") or "hold")
        if layout in HOST_LAYOUTS:
            kind = "host"
        elif "card" in layout:
            kind = "card"
        else:
            kind = "hold"
        intervals.append(
            {
                "layout": layout,
                "kind": kind,
                "t_start": start,
                "t_end": stop,
                "watchdog_visible": kind != "host",
            }
        )
    return intervals


def derive_request_intervals(takes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    intervals: list[dict[str, Any]] = []
    for row in takes:
        submitted = row.get("t_submit")
        if submitted is None:
            continue
        finished = row.get("t_ready")
        if finished is None:
            finished = row.get("t_on_air")
        intervals.append(
            {
                "take": row.get("take"),
                "t_start": submitted,
                "t_end": finished,
                "anchor": row.get("anchor"),
                "image_url": row.get("image_url"),
                "frame_url": row.get("frame_url"),
                "request_id": row.get("request_id"),
            }
        )
    return intervals


def derive_stream_samples(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"t": event.get("t"), "active": event.get("active")}
        for event in events
        if event.get("kind") == "stream_status"
    ]


def derive_watchdog_intervals(
    events: Iterable[dict[str, Any]], t_end: float
) -> list[dict[str, Any]]:
    start: float | None = None
    intervals: list[dict[str, Any]] = []
    for event in events:
        if event.get("kind") == "watchdog_unhealthy" and start is None:
            start = float(event.get("t", 0.0))
        elif event.get("kind") == "watchdog_healthy" and start is not None:
            intervals.append(
                {
                    "t_start": start,
                    "t_end": float(event.get("t", t_end)),
                    "reason": "unhealthy",
                }
            )
            start = None
    if start is not None:
        intervals.append({"t_start": start, "t_end": float(t_end), "reason": "unhealthy"})
    return intervals


def wait_for_recording_stable(
    path: Path,
    *,
    sleep: SleepFn = time.sleep,
    interval_s: float = 1.0,
    required_stable: int = 2,
) -> int:
    if not path.is_file():
        raise EvidenceError("recording file missing")
    previous = path.stat().st_size
    stable = 0
    while stable < required_stable:
        sleep(interval_s)
        if not path.is_file():
            raise EvidenceError("recording file missing")
        size = path.stat().st_size
        if size == previous:
            stable += 1
        else:
            stable = 0
            previous = size
    return previous


def configured_secrets(config: RuntimeConfig | Mapping[str, Any] | None) -> tuple[str, ...]:
    values: list[str] = []
    fal_key = os.environ.get("FAL_KEY")
    if fal_key:
        values.append(fal_key)
    if isinstance(config, RuntimeConfig):
        for item in (config.text_api_key, config.obs_password):
            if item:
                values.append(item)
    elif isinstance(config, Mapping):
        for key in ("text_api_key", "obs_password", "api_key"):
            item = config.get(key)
            if isinstance(item, str) and item:
                values.append(item)
        text = config.get("text")
        obs = config.get("obs")
        if isinstance(text, Mapping):
            key = text.get("api_key")
            if isinstance(key, str) and key and key != REDACTED:
                values.append(key)
        if isinstance(obs, Mapping):
            password = obs.get("password")
            if isinstance(password, str) and password and password != REDACTED:
                values.append(password)
    return tuple(values)


def write_evidence_bundle(
    out_root: Path,
    evidence: FlightEvidence,
    *,
    sleep: SleepFn = time.sleep,
) -> Path:
    bundle = Path(out_root) / evidence.flight_id
    if bundle.exists():
        raise EvidenceError(f"evidence directory already exists: {bundle}")
    bundle.mkdir(parents=True)
    (bundle / "baseline").mkdir()
    (bundle / "input").mkdir()
    (bundle / "segment").mkdir()
    (bundle / "logs").mkdir()

    recording_size = 0
    recording_path = evidence.recording_path
    if recording_path is not None:
        recording_size = wait_for_recording_stable(Path(recording_path), sleep=sleep)

    t_end = evidence.t_end
    if not t_end:
        aired = [row.get("t_on_air") for row in evidence.takes if row.get("t_on_air") is not None]
        t_end = max(aired) if aired else 0.0
        t_end = max(t_end, float(evidence.target_duration_s), float(evidence.recording_duration_s))

    scene_intervals = evidence.scene_intervals
    if scene_intervals is None:
        scene_intervals = derive_scene_intervals(evidence.beats, t_end)
    watchdog_intervals = evidence.watchdog_visible_intervals
    if watchdog_intervals is None:
        watchdog_intervals = derive_watchdog_intervals(evidence.events, t_end)
        watchdog_intervals.extend(
            {
                "t_start": item["t_start"],
                "t_end": item["t_end"],
                "reason": item["kind"],
            }
            for item in scene_intervals
            if item.get("watchdog_visible")
        )
    stream_samples = evidence.stream_status_samples
    if stream_samples is None:
        stream_samples = derive_stream_samples(evidence.events)
    request_intervals = evidence.request_intervals
    if request_intervals is None:
        request_intervals = derive_request_intervals(evidence.takes)

    anchors = [
        {
            "take": row.get("take"),
            "anchor": row.get("anchor"),
            "image_url": row.get("image_url"),
            "frame_url": row.get("frame_url"),
        }
        for row in evidence.takes
    ]

    cap = evidence.spend_cap_usd
    if cap is None and isinstance(evidence.config, RuntimeConfig):
        cap = evidence.config.spend_cap_usd

    flight = {
        "flight_id": evidence.flight_id,
        "baseline_id": evidence.baseline_id,
        "mode": evidence.mode,
        "target_duration_s": evidence.target_duration_s,
        "stop_reason": evidence.stop_reason,
        "verdict": None,
        "reserved_cost_upper_bound_usd": str(evidence.reserved_cost_upper_bound_usd),
        "spend_cap_usd": str(cap) if cap is not None else None,
        "spend": {
            "rate_768p_usd_per_s": str(evidence.spend_rate_768p_usd_per_s),
            "rate_effective_date": RATE_EFFECTIVE_DATE,
            "duration_s": evidence.spend_duration_s,
            "reservations": evidence.reservations,
        },
        "source_hashes": dict(evidence.source_hashes),
        "anchors": anchors,
        "scene_intervals": scene_intervals,
        "watchdog_visible_intervals": watchdog_intervals,
        "stream_status_samples": stream_samples,
        "request_intervals": request_intervals,
        "text_requests": evidence.text_requests,
        "text_request_limit": evidence.text_request_limit,
        "aired_speakers": sorted(
            {
                row["speaker"]
                for row in evidence.takes
                if row.get("t_on_air") is not None and row.get("speaker")
            }
        ),
    }
    _write_json(bundle / "flight.json", flight)

    if isinstance(evidence.config, RuntimeConfig):
        _write_json(bundle / "config.redacted.json", redacted_summary(evidence.config))
    elif isinstance(evidence.config, Mapping):
        payload = dict(evidence.config)
        for key in ("text_api_key", "obs_password", "api_key", "password"):
            if payload.get(key):
                payload[key] = REDACTED
        _write_json(bundle / "config.redacted.json", payload)
    else:
        _write_json(
            bundle / "config.redacted.json",
            {"mode": evidence.mode, "baseline_id": REDACTED},
        )

    shutil.copyfile(evidence.baseline_manifest_path, bundle / "baseline" / "manifest.json")
    shutil.copyfile(evidence.source_packet_path, bundle / "input" / "source_packet.json")
    shutil.copyfile(evidence.source_lock_path, bundle / "input" / "source_packet.lock.json")
    shutil.copyfile(
        evidence.excerpt_path, bundle / "input" / "dwarkesh-agent-civilizations.txt"
    )
    _write_json(bundle / "segment" / "package.json", package_as_dict(evidence.package))
    _write_jsonl(bundle / "logs" / "takes.jsonl", evidence.takes)
    _write_jsonl(bundle / "logs" / "events.jsonl", evidence.events)
    _write_jsonl(bundle / "logs" / "fal_requests.jsonl", evidence.fal_requests)
    _write_json(
        bundle / "recording.json",
        {
            "path": str(recording_path) if recording_path is not None else None,
            "duration_s": evidence.recording_duration_s,
            "size_bytes": recording_size,
            "stable": recording_path is not None,
        },
    )

    secrets = evidence.secrets or configured_secrets(evidence.config)
    scan_text_artifacts(bundle, secrets)
    write_hashes(bundle)
    return bundle


def scan_text_artifacts(bundle: Path, secrets: Iterable[str]) -> None:
    values = [secret for secret in secrets if secret]
    if not values:
        return
    for relative in (*BUNDLE_TEXT_NAMES, *OPTIONAL_TEXT_NAMES):
        path = bundle / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for secret in values:
            if secret and secret in text:
                raise EvidenceError("configured secret leaked into evidence")


def write_hashes(bundle: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in (*BUNDLE_TEXT_NAMES, *OPTIONAL_TEXT_NAMES):
        path = bundle / relative
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[relative] = digest
    _write_json(bundle / "hashes.json", hashes)
    return hashes


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows
    ]
    path.write_text("".join(lines), encoding="utf-8")
