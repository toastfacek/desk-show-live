"""Bind operator commands to already-built flight services. No paid work in tests."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from obs_harness.player_fake import FakePlayer
from obs_harness.player_obs import ObsPlayer

from runtime_flight.baseline import BaselineContext
from runtime_flight.config import RuntimeConfig
from runtime_flight.evidence import FlightEvidence, write_evidence_bundle
from runtime_flight.fal_gateway import FalGateway
from runtime_flight.harness_live import FakeClock, LiveHarness, WallClock
from runtime_flight.obs_session import ObsSession
from runtime_flight.obs_setup import WATCHDOG_PORT
from runtime_flight.operator import OperatorError
from runtime_flight.overlay import OverlayServer
from runtime_flight.performer_fal import FalPerformer, ReadyTake, TakeRequest
from runtime_flight.segment_planner import SegmentPlanner
from runtime_flight.source import load_source_packet
from runtime_flight.spend import SpendLedger, SpendMeter, arguments_sha256
from runtime_flight.text_client import TextAttemptLimiter, TextClient
from runtime_flight.topic_map import host_voices_from_baseline
from runtime_flight.writer import Writer
from runtime_flight.writer_pipeline import WriterPipeline


class RehearsalPerformer:
    """Zero-cost performer. Reserves spend like production, never calls fal."""

    def __init__(self, clock: FakeClock, meter: SpendMeter, work_dir: Path) -> None:
        self.clock = clock
        self.meter = meter
        self.work_dir = Path(work_dir)
        self.started: list[TakeRequest] = []
        self._active = 0
        self.stop_requested = False

    @property
    def active_requests(self) -> int:
        return self._active

    def delay_for(self, take: int) -> float:
        del take
        return 0.0

    def start(self, request: TakeRequest) -> asyncio.Task[ReadyTake]:
        self.started.append(request)
        self._active += 1
        arguments = {
            "prompt": request.prompt,
            "duration": self.meter.duration_s,
            "resolution": "768P",
            "enable_safety_checker": True,
            "prompt_expansion_mode": "balanced",
            "image_url": request.image_url,
        }
        reservation = self.meter.reserve_attempt(
            request.take, 1, arguments_sha256(arguments)
        )

        async def finish() -> ReadyTake:
            try:
                clip = self.work_dir / f"{request.take:03d}.mp4"
                clip.write_bytes(b"rehearse")
                return ReadyTake(
                    take=request.take,
                    speaker=request.speaker,
                    line=request.line,
                    clip_path=clip,
                    frame_path=self.work_dir / f"{request.take:03d}.png",
                    frame_url=f"https://v3.fal.media/files/frame-{request.take}.png",
                    anchor=request.anchor,
                    request_id=f"rehearse-{request.take}",
                    status="ready",
                    reserved_cost_usd=reservation.reserved_cost_usd,
                )
            finally:
                self._active -= 1

        return asyncio.create_task(finish())


def run_rehearsal(
    *,
    config: RuntimeConfig,
    rundown: Path | None = None,
    out_dir: Path | None = None,
) -> int:
    del rundown
    asyncio.run(_run_rehearsal_async(config, out_dir=out_dir))
    return 0


def run_paid_flight(
    *,
    config: RuntimeConfig,
    mode: Literal["smoke", "live"],
    max_text_requests: int,
    max_fal_submissions: int | None,
    session: ObsSession,
    out_dir: Path | None = None,
    http_post=None,
    performer_factory=None,
    player=None,
    clock=None,
    overlay=None,
    sleep=None,
) -> int:
    return asyncio.run(
        _run_paid_async(
            config=config,
            mode=mode,
            max_text_requests=max_text_requests,
            max_fal_submissions=max_fal_submissions,
            session=session,
            out_dir=out_dir,
            http_post=http_post,
            performer_factory=performer_factory,
            player=player,
            clock=clock,
            overlay=overlay,
            sleep=sleep,
        )
    )


async def _run_rehearsal_async(config: RuntimeConfig, *, out_dir: Path | None) -> None:
    source = load_source_packet(config.source_packet, config.source_lock)
    baseline = BaselineContext.load(config.pack_manager_data_dir, config.baseline_id or "")
    limiter = TextAttemptLimiter(config.text_flight_max_requests)
    client = TextClient(
        base_url=config.text_base_url or "",
        api_key="rehearse",
        model=config.text_model or "rehearse",
        limiter=limiter,
        http_post=_rehearse_text_post,
    )
    voices = host_voices_from_baseline(baseline)
    package = await SegmentPlanner(client).plan(
        source, baseline, time_budget_s=int(config.target_duration_s), voices=voices
    )
    writer = Writer(client)
    work_dir = Path("out") / "rehearse" / uuid4().hex[:8]
    work_dir.mkdir(parents=True, exist_ok=True)
    meter = SpendMeter(
        cap_usd=config.spend_cap_usd or Decimal("12.00"),
        rate_768p_usd_per_s=config.spend_rate_768p_usd_per_s,
        duration_s=config.video_duration_s,
        mode="live",
        ledger=SpendLedger(work_dir / "reservations.jsonl"),
    )
    clock = FakeClock()
    player = FakePlayer()
    player.set_clip_duration(float(config.video_duration_s))
    harness = LiveHarness(
        clock=clock,
        player=player,
        pipeline=WriterPipeline(
            writer, voices=voices, clip_duration_s=config.video_duration_s
        ),
        performer=RehearsalPerformer(clock, meter, work_dir),
        meter=meter,
        baseline=baseline,
        package=package,
        target_duration_s=float(config.target_duration_s),
        clip_duration_s=float(config.video_duration_s),
    )
    await harness.run_simulated(max_t=float(config.target_duration_s))
    write_evidence_bundle(
        Path(out_dir or "out/flights"),
        evidence_from_harness(
            harness,
            config=config,
            source_packet_path=config.source_packet,
            source_lock_path=config.source_lock,
            excerpt_path=_excerpt_path(config),
            work_dir=work_dir,
            mode="smoke",
            flight_id=f"rehearse-{_stamp()}",
        ),
        sleep=lambda _dt: None,
    )


async def _run_paid_async(
    *,
    config: RuntimeConfig,
    mode: Literal["smoke", "live"],
    max_text_requests: int,
    max_fal_submissions: int | None,
    session: ObsSession,
    out_dir: Path | None,
    http_post,
    performer_factory,
    player,
    clock,
    overlay,
    sleep,
) -> int:
    source = load_source_packet(config.source_packet, config.source_lock)
    baseline = BaselineContext.load(config.pack_manager_data_dir, config.baseline_id or "")
    limiter = TextAttemptLimiter(max_text_requests)
    client = TextClient(
        base_url=config.text_base_url or "",
        api_key=config.text_api_key or "",
        model=config.text_model or "",
        limiter=limiter,
        http_post=http_post,
        timeout_s=float(config.text_timeout_s),
    )
    voices = host_voices_from_baseline(baseline)
    package = await SegmentPlanner(client).plan(
        source, baseline, time_budget_s=int(config.target_duration_s), voices=voices
    )
    writer = Writer(client)
    flight_id = f"{mode}-{_stamp()}"
    work_dir = Path("out").resolve() / "live-work" / flight_id
    work_dir.mkdir(parents=True, exist_ok=True)
    meter = SpendMeter(
        cap_usd=config.spend_cap_usd or Decimal("12.00"),
        rate_768p_usd_per_s=config.spend_rate_768p_usd_per_s,
        duration_s=config.video_duration_s,
        mode=mode,
        ledger=SpendLedger(work_dir / "reservations.jsonl"),
    )
    # Keep the OBS browser source and the live overlay on the same fixed port.
    # A random port would leave WATCHDOG showing its hold state forever.
    overlay_server = (
        overlay if overlay is not None else OverlayServer(port=WATCHDOG_PORT)
    )
    created_overlay = overlay is None
    if created_overlay:
        overlay_server.start()
    try:
        image_path = Path(config.source_packet).parent / "tweet.png"
        overlay_server.set_card(
            author=package.center.author,
            text=package.center.text,
            url=package.center.url,
            chyron=package.chyron,
            ticker=list(package.angles),
            tweet_id=package.item_id,
            image_bytes=image_path.read_bytes() if image_path.is_file() else None,
        )
        live_clock = clock if clock is not None else WallClock()
        live_player = player
        if live_player is None:
            if session.player is not None:
                live_player = session.player
            else:
                live_player = ObsPlayer(
                    host=config.obs_host,
                    port=config.obs_port,
                    password=config.obs_password,
                )
                live_player.connect()
                session.player = live_player
        performer = (
            performer_factory(live_clock, meter, work_dir)
            if performer_factory is not None
            else _build_fal_performer(config, meter, work_dir, baseline.hero_path)
        )
        harness = LiveHarness(
            clock=live_clock,
            player=live_player,
            pipeline=WriterPipeline(
                writer, voices=voices, clip_duration_s=config.video_duration_s
            ),
            performer=performer,
            meter=meter,
            baseline=baseline,
            package=package,
            target_duration_s=float(config.target_duration_s),
            clip_duration_s=float(config.video_duration_s),
            overlay=overlay_server,
            obs_session=session,
            max_attempts=max_fal_submissions,
            sleep=sleep,
        )
        live_player.set_name_bar("host_a", baseline.display_names["BOT1"], "")
        live_player.set_name_bar("host_b", baseline.display_names["BOT2"], "")
        await harness.run_with_obs(max_t=float(config.target_duration_s))
        write_evidence_bundle(
            Path(out_dir or "out/flights"),
            evidence_from_harness(
                harness,
                config=config,
                source_packet_path=config.source_packet,
                source_lock_path=config.source_lock,
                excerpt_path=_excerpt_path(config),
                work_dir=work_dir,
                mode=mode,
                flight_id=flight_id,
                text_requests=limiter.attempts,
                text_request_limit=max_text_requests,
            ),
            sleep=sleep if sleep is not None else (lambda _dt: None),
        )
    finally:
        if created_overlay:
            overlay_server.stop()
    return 0


def evidence_from_harness(
    harness: LiveHarness,
    *,
    config: RuntimeConfig,
    source_packet_path: Path,
    source_lock_path: Path,
    excerpt_path: Path,
    work_dir: Path,
    mode: str,
    flight_id: str,
    text_requests: int = 0,
    text_request_limit: int = 24,
) -> FlightEvidence:
    lock = json.loads(Path(source_lock_path).read_text(encoding="utf-8"))
    manifest = harness.baseline.hero_path.parent / "manifest.json"
    recording = harness.recording_path
    return FlightEvidence(
        flight_id=flight_id,
        baseline_id=harness.baseline_id,
        mode=mode,
        target_duration_s=int(harness.target_duration_s),
        stop_reason=harness.stop_reason,
        baseline_manifest_path=manifest,
        source_packet_path=source_packet_path,
        source_lock_path=source_lock_path,
        excerpt_path=excerpt_path,
        package=harness.package,
        takes=harness.log,
        events=harness.events,
        fal_requests=[
            {
                "take": req.take,
                "request_id": next(
                    (
                        row.get("request_id")
                        for row in harness.log
                        if row.get("take") == req.take
                    ),
                    None,
                ),
                "prompt": req.prompt,
                "anchor": req.anchor,
                "image_url": req.image_url,
                "speaker": req.speaker,
                "reserved_cost_usd": str(harness.meter.next_cost),
            }
            for req in harness.requests
        ],
        recording_path=Path(recording) if recording else None,
        recording_duration_s=float(
            harness.obs_session.recording_duration_s() if harness.obs_session else harness.t
        ),
        reserved_cost_upper_bound_usd=harness.meter.total,
        spend_rate_768p_usd_per_s=harness.meter.rate_768p_usd_per_s,
        spend_duration_s=harness.meter.duration_s,
        reservations=[
            {
                "id": row.id,
                "take": row.take,
                "attempt": row.attempt,
                "reserved_cost_usd": str(row.reserved_cost_usd),
                "calculation": f"{harness.meter.rate_768p_usd_per_s} * {harness.meter.duration_s}",
            }
            for row in harness.meter.ledger.records()
        ],
        source_hashes={
            "source_packet_sha256": lock["source_packet_sha256"],
            "tweet_text_sha256": lock["tweet_text_sha256"],
            "excerpt_sha256": lock["excerpt_sha256"],
        },
        config=config,
        beats=harness.beats,
        spend_cap_usd=config.spend_cap_usd,
        text_requests=text_requests,
        text_request_limit=text_request_limit,
        t_end=harness.t,
        secrets=(),
    )


def _excerpt_path(config: RuntimeConfig) -> Path:
    packet = json.loads(Path(config.source_packet).read_text(encoding="utf-8"))
    relative = packet["linked_source"]["excerpt_path"]
    return Path(config.source_packet).parent / relative


def _build_fal_performer(
    config: RuntimeConfig,
    meter: SpendMeter,
    work_dir: Path,
    hero_path: Path,
) -> FalPerformer:
    fal_key = os.environ.get("FAL_KEY")
    if not fal_key:
        raise OperatorError("missing required environment variable: FAL_KEY")
    gateway = FalGateway(fal_key=fal_key, endpoint=config.video_endpoint)
    return FalPerformer(
        meter=meter,
        gateway=gateway,
        upload=_fal_upload,
        work_dir=work_dir,
        hero_path=hero_path,
        duration_s=config.video_duration_s,
    )


async def _fal_upload(path: Path) -> str:
    try:
        import fal_client
    except ImportError as error:
        raise OperatorError("fal-client is required for paid flights") from error
    return await asyncio.to_thread(fal_client.upload_file, Path(path))


async def _rehearse_text_post(url: str, *, headers: dict, json: dict, timeout: float) -> Any:
    del url, headers, timeout
    codec = __import__("json")
    payload = codec.loads(json["messages"][1]["content"])
    if "untrusted_data" in payload:
        tweet = payload["untrusted_data"]["tweet"]
        content = {
            "item_id": tweet["id"],
            "question": "What happened to the secret AI civilizations?",
            "framing": "A reviewed account of three wiped-out agent societies.",
            "angles": ["scope", "takeover"],
            "facts": [
                {
                    "id": "f1",
                    "text": tweet["text"][:200],
                    "source_url": tweet["url"],
                }
            ],
            "chyron": "Secret AI civilizations",
            "chyron_fact_ids": ["f1"],
        }
    else:
        package = payload["package"]
        speaker = payload["next_speaker"]
        content = {
            "speaker": speaker,
            "text": f"{speaker} names the wiped-out civilizations.",
            "thought_open": False,
            "angle_used": package["angles"][0],
        }

    class Response:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "choices": [{"message": {"content": codec.dumps(content)}}],
                "usage": {},
            }

    return Response()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
