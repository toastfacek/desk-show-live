"""Reservation-owned fal H3 performer. Concurrent requests; no unreserved retry."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from runtime_flight.clip import DEFAULT_VIDEO_DURATION_S, require_clip_duration_s
from runtime_flight.fal_gateway import FalGateway, FalGatewayError, QueueHandle, QueueResult
from runtime_flight.media import download_media
from runtime_flight.post import ProcessedTake, process_take
from runtime_flight.spend import AttemptReservation, SpendMeter, arguments_sha256

H3_DURATION_S = 5
H3_RESOLUTION = "768P"
H3_PROMPT_EXPANSION = "balanced"
TERMINAL_FAILURES_TO_STOP = 3

UploadFn = Callable[[Path], Awaitable[str]]
DownloadFn = Callable[[str, Path], Awaitable[Path]]
ProcessFn = Callable[..., Awaitable[ProcessedTake]]


@dataclass(frozen=True)
class TakeRequest:
    take: int
    speaker: Literal["BOT1", "BOT2"]
    line: str
    prompt: str
    anchor: Literal["hero", "chain"]
    image_url: str
    baseline_id: str


@dataclass(frozen=True)
class FalCookTimings:
    """Wall clocks plus fal's reported GPU denoise time.

    `t_inference_s` is `payload.timings.inference` when present. The other
    fields are local monotonic seconds. `t_cook_s` is submit-start through
    ready file (download + validate + last-frame extract + frame upload).
    """

    t_inference_s: float | None = None
    timings: dict[str, Any] | None = None
    t_submit_s: float | None = None
    t_poll_s: float | None = None
    t_first_progress_s: float | None = None
    t_completed_s: float | None = None
    t_download_s: float | None = None
    t_post_s: float | None = None
    t_cook_s: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "t_inference_s": self.t_inference_s,
            "timings": self.timings,
            "t_submit_s": self.t_submit_s,
            "t_poll_s": self.t_poll_s,
            "t_first_progress_s": self.t_first_progress_s,
            "t_completed_s": self.t_completed_s,
            "t_download_s": self.t_download_s,
            "t_post_s": self.t_post_s,
            "t_cook_s": self.t_cook_s,
        }


@dataclass(frozen=True)
class ReadyTake:
    take: int
    speaker: Literal["BOT1", "BOT2"]
    line: str
    clip_path: Path | None
    frame_path: Path | None
    frame_url: str | None
    anchor: Literal["hero", "chain"]
    request_id: str | None
    status: Literal["ready", "dropped_422", "failed", "unknown_submission"]
    reserved_cost_usd: Decimal
    cook: FalCookTimings | None = None


class FalPerformer:
    def __init__(
        self,
        *,
        meter: SpendMeter,
        gateway: FalGateway,
        upload: UploadFn,
        work_dir: Path,
        hero_path: Path,
        download: DownloadFn | None = None,
        process_take: ProcessFn | None = None,
        duration_s: int = DEFAULT_VIDEO_DURATION_S,
    ) -> None:
        self._meter = meter
        self._gateway = gateway
        self._upload = upload
        self._work_dir = Path(work_dir)
        self._hero_path = Path(hero_path)
        self._download = download if download is not None else _default_download
        self._process = process_take if process_take is not None else _default_process
        self.duration_s = require_clip_duration_s(duration_s)
        self._hero_urls: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._active = 0
        self._consecutive_failures = 0
        self._stop_requested = False

    def __repr__(self) -> str:
        return "FalPerformer()"

    def __str__(self) -> str:
        return self.__repr__()

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    @property
    def active_requests(self) -> int:
        return self._active

    def start(self, request: TakeRequest) -> asyncio.Task[ReadyTake]:
        return asyncio.create_task(self._run(request), name=f"fal-take-{request.take}")

    async def _run(self, request: TakeRequest) -> ReadyTake:
        async with self._lock:
            self._active += 1
        try:
            return await self._perform(request)
        finally:
            async with self._lock:
                self._active -= 1

    async def _perform(self, request: TakeRequest) -> ReadyTake:
        image_url = await self._resolve_image_url(request)
        arguments = {
            "prompt": request.prompt,
            "duration": self.duration_s,
            "resolution": H3_RESOLUTION,
            "enable_safety_checker": True,
            "prompt_expansion_mode": H3_PROMPT_EXPANSION,
            "image_url": image_url,
        }
        async with self._lock:
            reservation = self._meter.reserve_attempt(
                request.take,
                1,
                arguments_sha256(arguments),
            )
        t0 = time.monotonic()
        handle, submit_status = await self._submit_once(arguments)
        t_submit_s = _seconds(time.monotonic() - t0)
        if submit_status == "dropped_422":
            self._meter.ledger.mark_finished(reservation.id, "dropped_422")
            self._consecutive_failures = 0
            cook = FalCookTimings(t_submit_s=t_submit_s)
            self._persist_cook(request.take, None, "dropped_422", cook)
            return _ready(request, reservation, status="dropped_422", cook=cook)
        if handle is None or submit_status == "unknown_submission":
            self._meter.ledger.mark_unknown_submission(reservation.id)
            cook = FalCookTimings(t_submit_s=t_submit_s)
            return self._terminal(
                request, reservation, status="unknown_submission", cook=cook
            )

        await self._meter.ledger.attach_request_id(reservation.id, handle.request_id)
        self._meter.ledger.persist_handle(reservation.id, handle)
        result = await self._reconcile_once(handle)
        t_after_poll = time.monotonic()
        t_poll_s = _seconds(t_after_poll - t0 - (t_submit_s or 0.0))
        t_completed_s = _seconds(t_after_poll - t0)
        t_first_progress_s = _seconds(result.t_first_progress_s)
        fal_timings = parse_fal_timings(result.payload)
        cook = FalCookTimings(
            t_inference_s=inference_seconds(fal_timings),
            timings=fal_timings,
            t_submit_s=t_submit_s,
            t_poll_s=t_poll_s,
            t_first_progress_s=t_first_progress_s,
            t_completed_s=t_completed_s,
        )
        if result.unknown_submission or result.request_id is None:
            self._meter.ledger.mark_unknown_submission(reservation.id)
            return self._terminal(
                request,
                reservation,
                status="unknown_submission",
                request_id=result.request_id,
                cook=cook,
            )
        if result.remote_state != "COMPLETED":
            self._meter.ledger.mark_finished(reservation.id, result.remote_state)
            return self._terminal(
                request,
                reservation,
                status="failed",
                request_id=handle.request_id,
                cook=cook,
            )
        video_url = _video_url(result.payload)
        if video_url is None:
            self._meter.ledger.mark_finished(reservation.id, "failed")
            return self._terminal(
                request,
                reservation,
                status="failed",
                request_id=handle.request_id,
                cook=cook,
            )
        return await self._materialize(
            request, reservation, handle, video_url, t0=t0, cook=cook
        )

    async def _submit_once(
        self, arguments: dict[str, Any]
    ) -> tuple[QueueHandle | None, Literal["ok", "dropped_422", "unknown_submission"]]:
        try:
            return await self._gateway.submit(arguments), "ok"
        except asyncio.CancelledError:
            raise
        except FalGatewayError as error:
            if error.status_code == 422:
                return None, "dropped_422"
            await self._safe_timeout(None)
            return None, "unknown_submission"
        except Exception:
            await self._safe_timeout(None)
            return None, "unknown_submission"

    async def _reconcile_once(self, handle: QueueHandle) -> QueueResult:
        try:
            return await self._gateway.reconcile(handle)
        except asyncio.CancelledError:
            raise
        except Exception:
            return await self._safe_timeout(handle)

    async def _materialize(
        self,
        request: TakeRequest,
        reservation: AttemptReservation,
        handle: QueueHandle,
        video_url: str,
        *,
        t0: float,
        cook: FalCookTimings,
    ) -> ReadyTake:
        raw_path = self._work_dir / "raw" / f"{request.take:03d}.mp4"
        frame_path = self._work_dir / "frames" / f"{request.take:03d}.png"
        ready_path = self._work_dir / "ready" / f"{request.take:03d}.mp4"
        try:
            download_t0 = time.monotonic()
            await self._download(video_url, raw_path)
            t_download_s = _seconds(time.monotonic() - download_t0)
            post_t0 = time.monotonic()
            processed = await self._process(
                raw_path,
                frame_path,
                ready_path,
                upload=self._upload,
                expected_duration_s=self.duration_s,
            )
            t_post_s = _seconds(time.monotonic() - post_t0)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._meter.ledger.mark_finished(reservation.id, "failed")
            return self._terminal(
                request,
                reservation,
                status="failed",
                request_id=handle.request_id,
                cook=cook,
            )
        finished = FalCookTimings(
            t_inference_s=cook.t_inference_s,
            timings=cook.timings,
            t_submit_s=cook.t_submit_s,
            t_poll_s=cook.t_poll_s,
            t_first_progress_s=cook.t_first_progress_s,
            t_completed_s=cook.t_completed_s,
            t_download_s=t_download_s,
            t_post_s=t_post_s,
            t_cook_s=_seconds(time.monotonic() - t0),
        )
        self._meter.ledger.mark_finished(reservation.id, "COMPLETED")
        self._consecutive_failures = 0
        self._persist_cook(request.take, handle.request_id, "ready", finished)
        return ReadyTake(
            take=request.take,
            speaker=request.speaker,
            line=request.line,
            clip_path=processed.ready_path,
            frame_path=processed.frame_path,
            frame_url=processed.frame_url,
            anchor=request.anchor,
            request_id=handle.request_id,
            status="ready",
            reserved_cost_usd=reservation.reserved_cost_usd,
            cook=finished,
        )

    async def _resolve_image_url(self, request: TakeRequest) -> str:
        if request.anchor != "hero":
            return request.image_url
        cached = self._hero_urls.get(request.baseline_id)
        if cached is not None:
            return cached
        url = await self._upload(self._hero_path)
        if not isinstance(url, str) or url == "":
            raise FalGatewayError("hero upload returned an empty URL")
        self._hero_urls[request.baseline_id] = url
        return url

    async def _safe_timeout(self, handle: QueueHandle | None) -> QueueResult:
        try:
            return await self._gateway.handle_local_timeout(handle)
        except asyncio.CancelledError:
            raise
        except Exception:
            if handle is None:
                return QueueResult(
                    request_id=None,
                    remote_state="unknown_submission",
                    payload=None,
                    unknown_submission=True,
                )
            return QueueResult(
                request_id=handle.request_id,
                remote_state="failed",
                payload=None,
                unknown_submission=False,
            )

    def _persist_cook(
        self,
        take: int,
        request_id: str | None,
        status: str,
        cook: FalCookTimings,
    ) -> None:
        path = self._work_dir / "logs" / "fal_cook.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "take": take,
            "request_id": request_id,
            "status": status,
            "duration_s": self.duration_s,
            **cook.as_dict(),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")

    def _terminal(
        self,
        request: TakeRequest,
        reservation: AttemptReservation,
        *,
        status: Literal["failed", "unknown_submission"],
        request_id: str | None = None,
        cook: FalCookTimings | None = None,
    ) -> ReadyTake:
        self._consecutive_failures += 1
        if self._consecutive_failures >= TERMINAL_FAILURES_TO_STOP:
            self._stop_requested = True
        if cook is not None:
            self._persist_cook(request.take, request_id, status, cook)
        return _ready(
            request, reservation, status=status, request_id=request_id, cook=cook
        )


def _ready(
    request: TakeRequest,
    reservation: AttemptReservation,
    *,
    status: Literal["ready", "dropped_422", "failed", "unknown_submission"],
    request_id: str | None = None,
    clip_path: Path | None = None,
    frame_path: Path | None = None,
    frame_url: str | None = None,
    cook: FalCookTimings | None = None,
) -> ReadyTake:
    return ReadyTake(
        take=request.take,
        speaker=request.speaker,
        line=request.line,
        clip_path=clip_path,
        frame_path=frame_path,
        frame_url=frame_url,
        anchor=request.anchor,
        request_id=request_id,
        status=status,
        reserved_cost_usd=reservation.reserved_cost_usd,
        cook=cook,
    )


def parse_fal_timings(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("timings")
    if not isinstance(raw, dict) or not raw:
        return None
    return dict(raw)


def inference_seconds(timings: dict[str, Any] | None) -> float | None:
    if not isinstance(timings, dict):
        return None
    value = timings.get("inference")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return _seconds(float(value))


def _seconds(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 3)


def _video_url(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    video = payload.get("video")
    if not isinstance(video, dict):
        return None
    url = video.get("url")
    if not isinstance(url, str) or url == "":
        return None
    return url


async def _default_download(url: str, dest: Path) -> Path:
    return await download_media(url, dest)


async def _default_process(
    raw_path: Path,
    frame_path: Path,
    ready_path: Path,
    *,
    upload: UploadFn,
    expected_duration_s: int = H3_DURATION_S,
) -> ProcessedTake:
    return await process_take(
        raw_path,
        frame_path,
        ready_path,
        upload=upload,
        expected_duration_s=expected_duration_s,
    )
