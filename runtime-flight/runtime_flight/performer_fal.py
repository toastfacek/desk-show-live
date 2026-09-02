"""Reservation-owned fal H3 performer. Concurrent requests; no unreserved retry."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

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
    ) -> None:
        self._meter = meter
        self._gateway = gateway
        self._upload = upload
        self._work_dir = Path(work_dir)
        self._hero_path = Path(hero_path)
        self._download = download if download is not None else _default_download
        self._process = process_take if process_take is not None else _default_process
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
            "duration": H3_DURATION_S,
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
        handle, submit_status = await self._submit_once(arguments)
        if submit_status == "dropped_422":
            self._meter.ledger.mark_finished(reservation.id, "dropped_422")
            self._consecutive_failures = 0
            return _ready(request, reservation, status="dropped_422")
        if handle is None or submit_status == "unknown_submission":
            self._meter.ledger.mark_unknown_submission(reservation.id)
            return self._terminal(request, reservation, status="unknown_submission")

        await self._meter.ledger.attach_request_id(reservation.id, handle.request_id)
        self._meter.ledger.persist_handle(reservation.id, handle)
        result = await self._reconcile_once(handle)
        if result.unknown_submission or result.request_id is None:
            self._meter.ledger.mark_unknown_submission(reservation.id)
            return self._terminal(
                request,
                reservation,
                status="unknown_submission",
                request_id=result.request_id,
            )
        if result.remote_state != "COMPLETED":
            self._meter.ledger.mark_finished(reservation.id, result.remote_state)
            return self._terminal(
                request,
                reservation,
                status="failed",
                request_id=handle.request_id,
            )
        video_url = _video_url(result.payload)
        if video_url is None:
            self._meter.ledger.mark_finished(reservation.id, "failed")
            return self._terminal(
                request,
                reservation,
                status="failed",
                request_id=handle.request_id,
            )
        return await self._materialize(request, reservation, handle, video_url)

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
    ) -> ReadyTake:
        raw_path = self._work_dir / "raw" / f"{request.take:03d}.mp4"
        frame_path = self._work_dir / "frames" / f"{request.take:03d}.png"
        ready_path = self._work_dir / "ready" / f"{request.take:03d}.mp4"
        try:
            await self._download(video_url, raw_path)
            processed = await self._process(
                raw_path,
                frame_path,
                ready_path,
                upload=self._upload,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            self._meter.ledger.mark_finished(reservation.id, "failed")
            return self._terminal(
                request,
                reservation,
                status="failed",
                request_id=handle.request_id,
            )
        self._meter.ledger.mark_finished(reservation.id, "COMPLETED")
        self._consecutive_failures = 0
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

    def _terminal(
        self,
        request: TakeRequest,
        reservation: AttemptReservation,
        *,
        status: Literal["failed", "unknown_submission"],
        request_id: str | None = None,
    ) -> ReadyTake:
        self._consecutive_failures += 1
        if self._consecutive_failures >= TERMINAL_FAILURES_TO_STOP:
            self._stop_requested = True
        return _ready(request, reservation, status=status, request_id=request_id)


def _ready(
    request: TakeRequest,
    reservation: AttemptReservation,
    *,
    status: Literal["ready", "dropped_422", "failed", "unknown_submission"],
    request_id: str | None = None,
    clip_path: Path | None = None,
    frame_path: Path | None = None,
    frame_url: str | None = None,
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
    )


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
) -> ProcessedTake:
    return await process_take(raw_path, frame_path, ready_path, upload=upload)
