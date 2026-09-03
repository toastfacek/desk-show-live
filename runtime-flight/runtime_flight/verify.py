"""Independent verification of a completed live-flight evidence bundle."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping

from runtime_flight.anchor import persist_anchor
from runtime_flight.harness_live import DEFAULT_MAX_INFLIGHT
from runtime_flight.evidence import (
    HOLD_LAYOUTS,
    HOST_LAYOUTS,
    OPTIONAL_TEXT_NAMES,
    configured_secrets,
    scan_text_artifacts,
    write_hashes,
)

VOICE_KEYS = (
    "bot1_voice_consistency",
    "bot2_voice_consistency",
    "between_host_voice_distinction",
    "speaker_attribution",
    "intelligibility",
    "dialogue_fidelity",
    "voice_gesture_alignment",
)
ARCH_KEYS = (
    "composition",
    "visual_identity",
    "set_persistence",
    "reanchor_quality",
)
BLACKDETECT_FILTER = "blackdetect=d=0.2:pix_th=0.10"
FREEZEDETECT_FILTER = "freezedetect=n=-50dB:d=1.0"
MIN_AIRED = 10
MAX_HOLD_S = 15.0
MIN_RECORDING_S = 90.0

FfprobeFn = Callable[[Path], Mapping[str, Any]]
FfmpegFilterFn = Callable[[Path, str], str]


class VerifyError(Exception):
    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"{gate}: {message}")
        self.gate = gate
        self.message = message


@dataclass
class VerifyResult:
    ok: bool
    exit_code: int
    verdict: str | None
    failures: list[str] = field(default_factory=list)
    gates: list[str] = field(default_factory=list)


def default_ffprobe(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise VerifyError("recording", f"ffprobe failed: {proc.stderr[-2000:]}")
    payload = json.loads(proc.stdout)
    duration = float(payload.get("format", {}).get("duration") or 0.0)
    streams = payload.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    return {
        "duration_s": duration,
        "width": (video or {}).get("width"),
        "height": (video or {}).get("height"),
        "has_video": video is not None,
        "has_audio": audio is not None,
    }


def default_ffmpeg_filter(path: Path, filtergraph: str) -> str:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-vf",
            filtergraph,
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return (proc.stderr or "") + (proc.stdout or "")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def parse_black_intervals(text: str) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    for match in re.finditer(
        r"black_start:\s*([0-9.]+)\s+black_end:\s*([0-9.]+)", text
    ):
        start = float(match.group(1))
        end = float(match.group(2))
        intervals.append((start, end))
    return intervals


def parse_freeze_intervals(text: str) -> list[tuple[float, float]]:
    starts = [
        float(match.group(1))
        for match in re.finditer(r"freeze_start:\s*([0-9.]+)", text)
    ]
    ends = [
        float(match.group(1))
        for match in re.finditer(r"freeze_end:\s*([0-9.]+)", text)
    ]
    intervals: list[tuple[float, float]] = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else start
        intervals.append((start, end))
    return intervals


def _max_request_inflight(intervals: Iterable[Mapping[str, Any]]) -> int:
    events: list[tuple[float, int]] = []
    for item in intervals:
        start = item.get("t_start")
        if start is None:
            continue
        events.append((float(start), 1))
        end = item.get("t_end")
        events.append((float(end) if end is not None else float("inf"), -1))
    events.sort(key=lambda item: (item[0], item[1]))
    current = 0
    peak = 0
    for _time, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def interval_overlap(
    start: float, end: float, windows: Iterable[Mapping[str, Any]]
) -> bool:
    for window in windows:
        left = float(window.get("t_start", 0.0))
        right = float(window.get("t_end", 0.0))
        if start < right and end > left:
            return True
    return False


def freeze_exposes_host(
    freeze: tuple[float, float],
    scene_intervals: Iterable[Mapping[str, Any]],
    covered: Iterable[Mapping[str, Any]],
) -> bool:
    start, end = freeze
    if end - start <= 1.0:
        return False
    host_windows = [
        item
        for item in scene_intervals
        if item.get("layout") in HOST_LAYOUTS or item.get("kind") == "host"
    ]
    if not interval_overlap(start, end, host_windows):
        return False
    if interval_overlap(start, end, covered):
        # Covered if the freeze window is fully inside watchdog/hold/card.
        covering = [
            item
            for item in covered
            if float(item.get("t_start", 0.0)) <= start
            and float(item.get("t_end", 0.0)) >= end
        ]
        return not covering
    return True


def verify_bundle(
    bundle: Path,
    *,
    mode: Literal["automated", "final"],
    ffprobe: FfprobeFn | None = None,
    ffmpeg_filter: FfmpegFilterFn | None = None,
    secrets: Iterable[str] | None = None,
) -> VerifyResult:
    bundle = Path(bundle)
    failures: list[str] = []
    gates: list[str] = []

    def fail(gate: str, message: str) -> None:
        failures.append(f"{gate}: {message}")

    try:
        flight = load_json(bundle / "flight.json")
        takes = load_jsonl(bundle / "logs" / "takes.jsonl")
        events = load_jsonl(bundle / "logs" / "events.jsonl")
        fal_requests = load_jsonl(bundle / "logs" / "fal_requests.jsonl")
        recording_meta = load_json(bundle / "recording.json")
        package = load_json(bundle / "segment" / "package.json")
        hashes = load_json(bundle / "hashes.json")
        lock = load_json(bundle / "input" / "source_packet.lock.json")
        source = load_json(bundle / "input" / "source_packet.json")
        manifest = load_json(bundle / "baseline" / "manifest.json")
    except FileNotFoundError as error:
        result = VerifyResult(
            ok=False,
            exit_code=1,
            verdict="F-FAIL",
            failures=[f"bundle: missing file {error.filename}"],
        )
        _write_verdict(bundle, "F-FAIL")
        return result

    if not isinstance(flight, dict):
        fail("bundle", "flight.json must be an object")
        return _finish(bundle, mode, failures, gates, scores=None)

    baseline_id = flight.get("baseline_id")
    if not baseline_id:
        fail("baseline", "flight.json must record baseline_id")
    else:
        gates.append("baseline_id")
        if isinstance(manifest, dict) and manifest.get("baseline_id") not in {
            None,
            baseline_id,
        }:
            fail("baseline", "baseline manifest id does not match flight")

    source_hashes = flight.get("source_hashes") or {}
    for key in ("source_packet_sha256", "tweet_text_sha256", "excerpt_sha256"):
        if source_hashes.get(key) != lock.get(key):
            fail("source", f"{key} does not match the lock")
    if source.get("reviewed") is not True:
        fail("source", "source packet is not reviewed")
    else:
        gates.append("source")

    if not isinstance(package, dict) or not package.get("item_id"):
        fail("segment", "segment package missing")
    else:
        center = package.get("center") or {}
        if not center.get("text") or not package.get("chyron"):
            fail("segment", "center card or chyron missing")
        else:
            gates.append("segment")

    aired = [row for row in takes if row.get("t_on_air") is not None]
    speakers = {row.get("speaker") for row in aired}
    if len(aired) < MIN_AIRED:
        fail("aired", f"need at least {MIN_AIRED} aired clips, found {len(aired)}")
    else:
        gates.append("aired_count")
    required_speakers = {"BOT1"}
    if isinstance(manifest, dict):
        host_map = manifest.get("host_map") or {}
        if isinstance(host_map, dict) and "BOT2" in host_map:
            required_speakers.add("BOT2")
    if not required_speakers.issubset(speakers):
        if required_speakers == {"BOT1"}:
            fail("hosts", "BOT1 must air")
        else:
            fail("hosts", "both BOT1 and BOT2 must air")
    else:
        gates.append("hosts")

    take1 = next((row for row in takes if row.get("take") == 1), None)
    if take1 is None or take1.get("anchor") != "hero":
        fail("chain", "take 1 must use anchor hero")
    else:
        hero_url = take1.get("image_url") or "hero"
        reanchor_every = 0
        if isinstance(manifest, dict):
            raw_interval = manifest.get("reanchor_every")
            if isinstance(raw_interval, int):
                reanchor_every = raw_interval
        by_take = {row.get("take"): row for row in takes}
        persist_ok = True
        for row in takes:
            take = row.get("take")
            if not isinstance(take, int) or take <= 1:
                continue
            previous = by_take.get(take - 1)
            expected_anchor, expected_url = persist_anchor(
                take=take,
                speaker=str(row.get("speaker") or ""),
                previous_speaker=(
                    str(previous.get("speaker"))
                    if previous and previous.get("speaker")
                    else None
                ),
                previous_frame_url=(
                    previous.get("frame_url") if previous else None
                ),
                reanchor_every=reanchor_every,
                hero_url=str(hero_url),
            )
            if row.get("anchor") != expected_anchor:
                fail(
                    "chain",
                    f"take {take} must use anchor {expected_anchor}",
                )
                persist_ok = False
                break
            if expected_anchor == "chain" and row.get("image_url") != expected_url:
                fail("chain", "a chained take must use the previous exact frame_url")
                persist_ok = False
                break
        if persist_ok:
            gates.append("chain")

    recording_path = recording_meta.get("path")
    probe_fn = ffprobe or default_ffprobe
    filter_fn = ffmpeg_filter or default_ffmpeg_filter
    if not recording_path:
        fail("recording", "recording path missing")
    else:
        probe = probe_fn(Path(recording_path))
        duration = float(probe.get("duration_s") or recording_meta.get("duration_s") or 0.0)
        if duration + 1e-9 < MIN_RECORDING_S:
            fail("recording", f"recording duration {duration}s is under 90s")
        if not probe.get("has_video") or not probe.get("has_audio"):
            fail("recording", "recording must contain video and native audio")
        if probe.get("width") is None or probe.get("height") is None:
            fail("recording", "recording dimensions missing")
        else:
            gates.append("recording")
        black_text = filter_fn(Path(recording_path), BLACKDETECT_FILTER)
        for start, end in parse_black_intervals(black_text):
            if end - start + 1e-9 >= 0.2:
                fail("blackdetect", f"black interval {start}-{end}")
                break
        else:
            gates.append("blackdetect")
        freeze_text = filter_fn(Path(recording_path), FREEZEDETECT_FILTER)
        scene_intervals = flight.get("scene_intervals") or []
        covered = list(flight.get("watchdog_visible_intervals") or [])
        covered.extend(
            item
            for item in scene_intervals
            if item.get("layout") in HOLD_LAYOUTS or item.get("kind") in {"hold", "card"}
        )
        exposed = False
        for freeze in parse_freeze_intervals(freeze_text):
            if freeze_exposes_host(freeze, scene_intervals, covered):
                fail("freezedetect", f"exposed host freeze {freeze[0]}-{freeze[1]}")
                exposed = True
                break
        if not exposed:
            gates.append("freezedetect")

    hold_fail = False
    for item in flight.get("scene_intervals") or []:
        layout = item.get("layout")
        kind = item.get("kind")
        if layout in HOLD_LAYOUTS or kind in {"hold", "card"}:
            duration = float(item.get("t_end", 0.0)) - float(item.get("t_start", 0.0))
            if duration > MAX_HOLD_S + 1e-9:
                fail("hold", f"hold/card interval exceeds 15s ({duration})")
                hold_fail = True
                break
    if not hold_fail:
        gates.append("hold")

    request_intervals = list(flight.get("request_intervals") or [])
    peak = _max_request_inflight(request_intervals)
    if peak > DEFAULT_MAX_INFLIGHT:
        fail("fal", f"fal inflight peaked at {peak}, cap is {DEFAULT_MAX_INFLIGHT}")
    else:
        gates.append("fal_overlap")

    reserved = Decimal(str(flight.get("reserved_cost_upper_bound_usd") or "0"))
    cap_raw = flight.get("spend_cap_usd")
    if cap_raw is None:
        fail("spend", "spend cap missing")
    else:
        cap = Decimal(str(cap_raw))
        if reserved > cap:
            fail("spend", f"reserved cost {reserved} exceeds cap {cap}")
        else:
            gates.append("spend")

    text_requests = int(flight.get("text_requests") or 0)
    text_limit = int(flight.get("text_request_limit") or 24)
    if text_requests > text_limit:
        fail("text", f"text requests {text_requests} exceed limit {text_limit}")
    else:
        gates.append("text")

    try:
        scan_text_artifacts(bundle, secrets if secrets is not None else configured_secrets(None))
        gates.append("secrets")
    except Exception as error:
        fail("secrets", str(error))

    expected_hash_files = [
        name
        for name in (
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
            *OPTIONAL_TEXT_NAMES,
        )
        if (bundle / name).is_file()
    ]
    for name in expected_hash_files:
        if name == "voice_review.json" and name not in hashes:
            continue
        digest = hashlib_file(bundle / name)
        if hashes.get(name) != digest:
            fail("hashes", f"{name} hash mismatch")
            break
    else:
        gates.append("hashes")

    spend = flight.get("spend") or {}
    if not spend.get("rate_768p_usd_per_s") or not spend.get("rate_effective_date"):
        fail("spend", "rate and effective date must be recorded")
    if not spend.get("reservations"):
        fail("spend", "reservation calculations missing")

    if not fal_requests:
        fail("fal", "fal request ledger missing")
    else:
        if not any("voice" in str(row.get("prompt") or "").lower() or "voice_direction" in row for row in fal_requests):
            if not any("Active host voice" in str(row.get("prompt") or "") for row in fal_requests):
                fail("prompt", "fal requests must record voice_direction injection")
            else:
                gates.append("voice_direction")
        else:
            gates.append("voice_direction")

    scores = None
    if mode == "final":
        review_path = bundle / "voice_review.json"
        if not review_path.is_file():
            return _finish(
                bundle,
                mode,
                failures + ["voice_review: missing voice_review.json"],
                gates,
                scores="missing",
            )
        review = load_json(review_path)
        if not isinstance(review, dict):
            return _finish(
                bundle,
                mode,
                failures + ["voice_review: voice_review.json must be an object"],
                gates,
                scores="missing",
            )
        missing = [key for key in (*VOICE_KEYS, *ARCH_KEYS) if key not in review]
        if missing:
            return _finish(
                bundle,
                mode,
                failures + [f"voice_review: missing {', '.join(missing)}"],
                gates,
                scores="missing",
            )
        scores = review

    _ = events
    return _finish(bundle, mode, failures, gates, scores=scores)


def hashlib_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finish(
    bundle: Path,
    mode: Literal["automated", "final"],
    failures: list[str],
    gates: list[str],
    scores: Mapping[str, Any] | Literal["missing"] | None,
) -> VerifyResult:
    if failures and scores != "missing":
        _write_verdict(bundle, "F-FAIL")
        return VerifyResult(
            ok=False, exit_code=1, verdict="F-FAIL", failures=failures, gates=gates
        )
    if mode == "automated":
        return VerifyResult(ok=True, exit_code=0, verdict=None, failures=[], gates=gates)
    if scores == "missing" or scores is None:
        extra = [item for item in failures if item.startswith("voice_review:")]
        _write_verdict(bundle, "F-INCONCLUSIVE")
        return VerifyResult(
            ok=False,
            exit_code=1,
            verdict="F-INCONCLUSIVE",
            failures=extra or ["voice_review: scores missing"],
            gates=gates,
        )
    voice_fail = any(_score(scores, key) < 3 for key in VOICE_KEYS)
    arch_fail = any(_score(scores, key) < 3 for key in ARCH_KEYS)
    if arch_fail:
        verdict = "F-ARCH"
    elif voice_fail:
        verdict = "F-PATH"
    else:
        verdict = "F-PASS"
    _write_verdict(bundle, verdict)
    return VerifyResult(ok=True, exit_code=0, verdict=verdict, failures=[], gates=gates)


def _score(scores: Mapping[str, Any], key: str) -> int:
    value = scores[key]
    return int(value)


def _write_verdict(bundle: Path, verdict: str) -> None:
    path = bundle / "flight.json"
    if not path.is_file():
        return
    flight = json.loads(path.read_text(encoding="utf-8"))
    flight["verdict"] = verdict
    path.write_text(json.dumps(flight, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_hashes(bundle)
