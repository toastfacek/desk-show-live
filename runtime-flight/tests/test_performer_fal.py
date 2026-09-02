"""Task 11: FalPerformer is the sole reservation owner. Fake fal only."""

from __future__ import annotations

import ast
import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from runtime_flight.fal_gateway import (
    FalGatewayError,
    FalUnknownSubmission,
    QueueHandle,
    QueueResult,
)
from runtime_flight.media import MediaError, StreamFingerprint
from runtime_flight.post import ProcessedTake
from runtime_flight.spend import SpendLedger, SpendMeter, arguments_sha256

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}

RATE = Decimal("0.08")
NEXT_COST = RATE * Decimal(5)
PROMPT = "locked wide two-shot. BOT1 speaks."
HERO_UPLOAD_URL = "https://v3.fal.media/files/hero-cached.png"
CHAIN_URL = "https://v3.fal.media/files/exact-chain-frame.png"
FRAME_URL = "https://v3.fal.media/files/exact-final-frame.png"
VIDEO_URL = "https://v3.fal.media/files/out.mp4"
REQUEST_ID = "req-h3-1"
STATUS_URL = f"https://queue.fal.run/minimax/h3-max/image-to-video/requests/{REQUEST_ID}/status"
RESPONSE_URL = f"https://queue.fal.run/minimax/h3-max/image-to-video/requests/{REQUEST_ID}"
CANCEL_URL = f"https://queue.fal.run/minimax/h3-max/image-to-video/requests/{REQUEST_ID}/cancel"
FAL_KEY = "fal-test-key-should-never-appear"
BASELINE_A = "baseline-a"
BASELINE_B = "baseline-b"


def _handle() -> QueueHandle:
    return QueueHandle(
        request_id=REQUEST_ID,
        status_url=STATUS_URL,
        response_url=RESPONSE_URL,
        cancel_url=CANCEL_URL,
    )


def _completed(payload: dict[str, Any] | None = None) -> QueueResult:
    return QueueResult(
        request_id=REQUEST_ID,
        remote_state="COMPLETED",
        payload=payload if payload is not None else {"video": {"url": VIDEO_URL}},
        unknown_submission=False,
    )


def _fingerprint() -> StreamFingerprint:
    return StreamFingerprint(
        codec_type="video",
        codec_name="h264",
        codec_tag_string="avc1",
        extra_data="",
        width=1344,
        height=768,
    )


def _processed(work_dir: Path, take: int) -> ProcessedTake:
    frame_path = work_dir / "frames" / f"{take:03d}.png"
    ready_path = work_dir / "ready" / f"{take:03d}.mp4"
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1344, 768), (1, 2, 3)).save(frame_path, format="PNG")
    ready_path.write_bytes(b"ready-bytes")
    return ProcessedTake(
        frame_url=FRAME_URL,
        frame_path=frame_path,
        ready_path=ready_path,
        final_frame_timestamp_s=4.9,
        video_fingerprint=_fingerprint(),
        audio_fingerprint=_fingerprint(),
    )


def _request(
    *,
    take: int = 1,
    speaker: Literal["BOT1", "BOT2"] = "BOT1",
    line: str = "Hello from the desk.",
    prompt: str = PROMPT,
    anchor: Literal["hero", "chain"] = "hero",
    image_url: str = "https://should-not-win.example/unused.png",
    baseline_id: str = BASELINE_A,
) -> Any:
    from runtime_flight.performer_fal import TakeRequest

    return TakeRequest(
        take=take,
        speaker=speaker,
        line=line,
        prompt=prompt,
        anchor=anchor,
        image_url=image_url,
        baseline_id=baseline_id,
    )


def _meter(tmp_path: Path) -> SpendMeter:
    return SpendMeter(
        cap_usd=Decimal("12.00"),
        rate_768p_usd_per_s=RATE,
        duration_s=5,
        mode="live",
        ledger=SpendLedger(tmp_path / "reservations.jsonl"),
    )


class FakeGateway:
    def __init__(
        self,
        *,
        submit: Any = None,
        reconcile: Any = None,
        handle_local_timeout: Any = None,
    ) -> None:
        self.submits: list[dict[str, Any]] = []
        self.reconciles: list[QueueHandle] = []
        self.timeouts: list[QueueHandle | None] = []
        self._submit = submit
        self._reconcile = reconcile
        self._timeout = handle_local_timeout
        self._inflight = 0
        self.max_inflight = 0

    async def submit(self, arguments: dict[str, Any]) -> QueueHandle:
        self._inflight += 1
        self.max_inflight = max(self.max_inflight, self._inflight)
        try:
            self.submits.append(dict(arguments))
            if self._submit is not None:
                return await self._submit(arguments)
            return _handle()
        finally:
            self._inflight -= 1

    async def reconcile(self, handle: QueueHandle) -> QueueResult:
        self.reconciles.append(handle)
        if self._reconcile is not None:
            return await self._reconcile(handle)
        return _completed()

    async def handle_local_timeout(
        self,
        handle: QueueHandle | None,
        *,
        cancel: bool = False,
    ) -> QueueResult:
        self.timeouts.append(handle)
        if self._timeout is not None:
            return await self._timeout(handle, cancel=cancel)
        if handle is None:
            return QueueResult(
                request_id=None,
                remote_state="unknown_submission",
                payload=None,
                unknown_submission=True,
            )
        return QueueResult(
            request_id=handle.request_id,
            remote_state="IN_QUEUE",
            payload=None,
            unknown_submission=False,
        )

    def __repr__(self) -> str:
        return "FakeGateway()"


def _hero_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1344, 768), (9, 9, 9)).save(path, format="PNG")
    return path


def _performer(
    tmp_path: Path,
    *,
    meter: SpendMeter | None = None,
    gateway: FakeGateway | None = None,
    upload: Any = None,
    download: Any = None,
    process: Any = None,
    hero_path: Path | None = None,
    trace: list[str] | None = None,
    duration_s: int = 5,
):
    from runtime_flight.performer_fal import FalPerformer

    meter = meter or _meter(tmp_path)
    gateway = gateway or FakeGateway()
    uploads: list[Path] = []

    async def default_upload(path: Path) -> str:
        uploads.append(Path(path))
        if trace is not None:
            trace.append("upload")
        if Path(path).suffix.lower() == ".png" and "hero" in Path(path).name:
            return HERO_UPLOAD_URL
        return FRAME_URL

    async def default_download(url: str, dest: Path) -> Path:
        if trace is not None:
            trace.append("download")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"raw-h3")
        return dest

    async def default_process(
        raw: Path, frame: Path, ready: Path, *, upload: Any, **_kwargs: Any
    ) -> ProcessedTake:
        if trace is not None:
            trace.extend(["validate", "final_frame", "upload_frame"])
        return _processed(tmp_path, int(ready.stem))

    if upload is None:
        upload = default_upload
    if download is None:
        download = default_download
    if process is None:
        process = default_process

    performer = FalPerformer(
        meter=meter,
        gateway=gateway,
        upload=upload,
        work_dir=tmp_path,
        hero_path=hero_path or _hero_png(tmp_path / "hero.png"),
        download=download,
        process_take=process,
        duration_s=duration_s,
    )
    performer._test_uploads = uploads  # type: ignore[attr-defined]
    performer._test_gateway = gateway  # type: ignore[attr-defined]
    performer._test_meter = meter  # type: ignore[attr-defined]
    return performer


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_start_returns_task_and_runs_full_mocked_lifecycle(tmp_path: Path) -> None:
    from runtime_flight.performer_fal import FalPerformer, ReadyTake, TakeRequest

    trace: list[str] = []
    meter = _meter(tmp_path)
    ledger_path = meter.ledger.path
    original_reserve = meter.reserve_attempt

    def reserve(take: int, attempt: int, arguments_hash: str):
        trace.append("reserve")
        return original_reserve(take, attempt, arguments_hash)

    meter.reserve_attempt = reserve  # type: ignore[method-assign]

    async def submit(arguments: dict[str, Any]) -> QueueHandle:
        reloaded = SpendLedger(ledger_path)
        assert reloaded.records(), "reservation must exist on disk before queue POST"
        trace.append("submit")
        return _handle()

    async def reconcile(handle: QueueHandle) -> QueueResult:
        trace.append("request_id")
        trace.append("reconcile")
        assert handle.request_id == REQUEST_ID
        return _completed()

    gateway = FakeGateway(submit=submit, reconcile=reconcile)
    performer = _performer(
        tmp_path,
        meter=meter,
        gateway=gateway,
        trace=trace,
        hero_path=_hero_png(tmp_path / "hero.png"),
    )
    assert isinstance(performer, FalPerformer)

    async def run() -> ReadyTake:
        request = _request()
        assert isinstance(request, TakeRequest)
        task = performer.start(request)
        assert isinstance(task, asyncio.Task)
        return await task

    ready = _run(run())
    assert isinstance(ready, ReadyTake)
    assert ready.status == "ready"
    assert ready.take == 1
    assert ready.speaker == "BOT1"
    assert ready.line == "Hello from the desk."
    assert ready.anchor == "hero"
    assert ready.request_id == REQUEST_ID
    assert ready.reserved_cost_usd == NEXT_COST
    assert ready.clip_path is not None and ready.clip_path.is_file()
    assert ready.frame_path is not None and ready.frame_path.is_file()
    assert ready.frame_url == FRAME_URL
    assert trace[:6] == [
        "upload",
        "reserve",
        "submit",
        "request_id",
        "reconcile",
        "download",
    ]
    assert trace[6:] == ["validate", "final_frame", "upload_frame"]
    assert meter.ledger.records()[0].request_id == REQUEST_ID
    assert meter.ledger.records()[0].final_remote_state == "COMPLETED"


def test_h3_arguments_are_exact_and_use_cached_hero_url(tmp_path: Path) -> None:
    gateway = FakeGateway()
    performer = _performer(tmp_path, gateway=gateway)

    async def run() -> None:
        await performer.start(_request(prompt=PROMPT, anchor="hero")) 

    _run(run())
    assert gateway.submits == [
        {
            "prompt": PROMPT,
            "duration": 5,
            "resolution": "768P",
            "enable_safety_checker": True,
            "prompt_expansion_mode": "balanced",
            "image_url": HERO_UPLOAD_URL,
        }
    ]


def test_h3_arguments_use_configured_fifteen_second_duration(tmp_path: Path) -> None:
    gateway = FakeGateway()
    performer = _performer(tmp_path, gateway=gateway, duration_s=15)

    async def run() -> None:
        await performer.start(_request(prompt=PROMPT, anchor="hero"))

    _run(run())
    assert gateway.submits[0]["duration"] == 15


def test_chain_take_uses_exact_anchor_url_without_reupload(tmp_path: Path) -> None:
    uploads: list[Path] = []

    async def upload(path: Path) -> str:
        uploads.append(Path(path))
        return FRAME_URL

    gateway = FakeGateway()
    performer = _performer(tmp_path, gateway=gateway, upload=upload)

    async def run() -> None:
        await performer.start(_request(anchor="chain", image_url=CHAIN_URL))

    _run(run())
    assert gateway.submits[0]["image_url"] == CHAIN_URL
    assert uploads == []


def test_hero_url_is_uploaded_once_per_baseline(tmp_path: Path) -> None:
    uploads: list[Path] = []

    async def upload(path: Path) -> str:
        uploads.append(Path(path))
        return HERO_UPLOAD_URL if "hero" in Path(path).name else FRAME_URL

    gateway = FakeGateway()
    performer = _performer(tmp_path, gateway=gateway, upload=upload)

    async def run() -> None:
        await performer.start(_request(take=1, baseline_id=BASELINE_A, anchor="hero"))
        await performer.start(_request(take=2, baseline_id=BASELINE_A, anchor="hero"))
        await performer.start(_request(take=3, baseline_id=BASELINE_B, anchor="hero"))

    _run(run())
    hero_uploads = [path for path in uploads if path.name == "hero.png"]
    assert len(hero_uploads) == 2
    assert gateway.submits[0]["image_url"] == HERO_UPLOAD_URL
    assert gateway.submits[1]["image_url"] == HERO_UPLOAD_URL
    assert gateway.submits[2]["image_url"] == HERO_UPLOAD_URL


def test_harness_never_creates_a_reservation(tmp_path: Path) -> None:
    meter = _meter(tmp_path)
    performer = _performer(tmp_path, meter=meter)
    assert meter.ledger.records() == []

    async def run() -> None:
        await performer.start(_request())

    _run(run())
    rows = meter.ledger.records()
    assert len(rows) == 1
    assert rows[0].take == 1
    assert rows[0].attempt == 1
    assert rows[0].reserved_cost_usd == NEXT_COST


def test_reserve_happens_immediately_before_the_single_queue_post(tmp_path: Path) -> None:
    meter = _meter(tmp_path)
    seen_before_post: list[int] = []
    posts = 0

    async def submit(arguments: dict[str, Any]) -> QueueHandle:
        nonlocal posts
        posts += 1
        seen_before_post.append(len(SpendLedger(meter.ledger.path).records()))
        return _handle()

    performer = _performer(tmp_path, meter=meter, gateway=FakeGateway(submit=submit))

    async def run() -> None:
        await performer.start(_request())

    _run(run())
    assert posts == 1
    assert seen_before_post == [1]
    expected = {
        "prompt": PROMPT,
        "duration": 5,
        "resolution": "768P",
        "enable_safety_checker": True,
        "prompt_expansion_mode": "balanced",
        "image_url": HERO_UPLOAD_URL,
    }
    row = meter.ledger.records()[0]
    assert row.arguments_sha256 == arguments_sha256(expected)


def test_multiple_fal_requests_may_be_active(tmp_path: Path) -> None:
    release = asyncio.Event()
    both_in_submit = asyncio.Event()
    entered = 0

    async def submit(arguments: dict[str, Any]) -> QueueHandle:
        nonlocal entered
        entered += 1
        if entered >= 2:
            both_in_submit.set()
        await release.wait()
        return _handle()

    gateway = FakeGateway(submit=submit)
    performer = _performer(tmp_path, gateway=gateway)

    async def run() -> None:
        first = performer.start(_request(take=1))
        second = performer.start(_request(take=2))
        await both_in_submit.wait()
        assert performer.active_requests == 2
        assert gateway.max_inflight == 2
        assert len(gateway.submits) == 2
        release.set()
        await asyncio.gather(first, second)

    _run(run())
    assert len(gateway.submits) == 2


def test_422_marks_dropped_keeps_reservation_and_does_not_retry(tmp_path: Path) -> None:
    posts = 0

    async def submit(arguments: dict[str, Any]) -> QueueHandle:
        nonlocal posts
        posts += 1
        raise FalGatewayError("queue submit rejected", status_code=422, unknown_submission=False)

    meter = _meter(tmp_path)
    gateway = FakeGateway(submit=submit)
    performer = _performer(tmp_path, meter=meter, gateway=gateway)

    async def run():
        return await performer.start(_request())

    ready = _run(run())
    assert ready.status == "dropped_422"
    assert ready.clip_path is None
    assert ready.frame_path is None
    assert ready.frame_url is None
    assert ready.request_id is None
    assert ready.reserved_cost_usd == NEXT_COST
    assert posts == 1
    assert gateway.reconciles == []
    row = meter.ledger.records()[0]
    assert row.reserved_cost_usd == NEXT_COST
    assert row.final_remote_state == "dropped_422"
    assert not performer.stop_requested


def test_unknown_submission_reconciles_without_unreserved_retry(tmp_path: Path) -> None:
    posts = 0

    async def submit(arguments: dict[str, Any]) -> QueueHandle:
        nonlocal posts
        posts += 1
        raise FalUnknownSubmission("queue submit timed out")

    meter = _meter(tmp_path)
    timeout = AsyncMock(
        return_value=QueueResult(
            request_id=None,
            remote_state="unknown_submission",
            payload=None,
            unknown_submission=True,
        )
    )
    gateway = FakeGateway(submit=submit, handle_local_timeout=timeout)
    performer = _performer(tmp_path, meter=meter, gateway=gateway)

    async def run():
        return await performer.start(_request())

    ready = _run(run())
    assert ready.status == "unknown_submission"
    assert ready.request_id is None
    assert ready.reserved_cost_usd == NEXT_COST
    assert posts == 1
    timeout.assert_awaited()
    assert timeout.await_args.args[0] is None
    row = meter.ledger.records()[0]
    assert row.final_remote_state == "unknown_submission"
    assert meter.total == NEXT_COST
    assert performer.consecutive_failures == 1


def test_ambiguous_failure_after_handle_reconciles_and_does_not_resubmit(
    tmp_path: Path,
) -> None:
    posts = 0

    async def submit(arguments: dict[str, Any]) -> QueueHandle:
        nonlocal posts
        posts += 1
        return _handle()

    async def reconcile(handle: QueueHandle) -> QueueResult:
        raise FalGatewayError("status poll failed")

    async def timeout(handle: QueueHandle | None, *, cancel: bool = False) -> QueueResult:
        assert handle == _handle()
        return QueueResult(
            request_id=REQUEST_ID,
            remote_state="IN_QUEUE",
            payload=None,
            unknown_submission=False,
        )

    meter = _meter(tmp_path)
    gateway = FakeGateway(submit=submit, reconcile=reconcile, handle_local_timeout=timeout)
    performer = _performer(tmp_path, meter=meter, gateway=gateway)

    async def run():
        return await performer.start(_request())

    ready = _run(run())
    assert ready.status == "failed"
    assert ready.request_id == REQUEST_ID
    assert posts == 1
    assert len(gateway.reconciles) == 1
    assert gateway.timeouts == [_handle()]
    assert meter.ledger.records()[0].request_id == REQUEST_ID
    assert meter.ledger.records()[0].final_remote_state == "IN_QUEUE"


def test_missing_request_id_is_unknown_submission_not_a_clean_reject(
    tmp_path: Path,
) -> None:
    async def submit(arguments: dict[str, Any]) -> QueueHandle:
        raise FalGatewayError("queue submit returned an unusable handle")

    meter = _meter(tmp_path)
    performer = _performer(tmp_path, meter=meter, gateway=FakeGateway(submit=submit))

    async def run():
        return await performer.start(_request())

    ready = _run(run())
    assert ready.status == "unknown_submission"
    assert ready.request_id is None
    assert meter.ledger.records()[0].final_remote_state == "unknown_submission"


def test_three_consecutive_terminal_failures_signal_graceful_stop(tmp_path: Path) -> None:
    async def submit(arguments: dict[str, Any]) -> QueueHandle:
        raise FalUnknownSubmission("queue submit failed")

    performer = _performer(tmp_path, gateway=FakeGateway(submit=submit))

    async def run() -> None:
        for take in (1, 2, 3):
            ready = await performer.start(_request(take=take))
            assert ready.status == "unknown_submission"
        assert performer.stop_requested
        assert performer.consecutive_failures == 3

    _run(run())


def test_422_does_not_count_as_terminal_failure(tmp_path: Path) -> None:
    async def unknown(arguments: dict[str, Any]) -> QueueHandle:
        raise FalUnknownSubmission("queue submit failed")

    async def rejected(arguments: dict[str, Any]) -> QueueHandle:
        raise FalGatewayError("queue submit rejected", status_code=422)

    first = FakeGateway(submit=unknown)
    performer = _performer(tmp_path, gateway=first)

    async def run() -> None:
        await performer.start(_request(take=1))
        assert performer.consecutive_failures == 1
        performer._gateway = FakeGateway(submit=rejected)  # type: ignore[attr-defined]
        dropped = await performer.start(_request(take=2))
        assert dropped.status == "dropped_422"
        assert performer.consecutive_failures == 0
        assert not performer.stop_requested

    _run(run())


def test_success_resets_consecutive_terminal_failures(tmp_path: Path) -> None:
    async def unknown(arguments: dict[str, Any]) -> QueueHandle:
        raise FalUnknownSubmission("queue submit failed")

    performer = _performer(tmp_path, gateway=FakeGateway(submit=unknown))

    async def run() -> None:
        await performer.start(_request(take=1))
        await performer.start(_request(take=2))
        assert performer.consecutive_failures == 2
        performer._gateway = FakeGateway()  # type: ignore[attr-defined]
        ready = await performer.start(_request(take=3))
        assert ready.status == "ready"
        assert performer.consecutive_failures == 0
        assert not performer.stop_requested

    _run(run())


def test_media_failure_is_failed_and_never_returns_ready_paths(tmp_path: Path) -> None:
    async def boom(*_args: Any, **_kwargs: Any) -> ProcessedTake:
        raise MediaError("audio is silent")

    meter = _meter(tmp_path)
    performer = _performer(tmp_path, meter=meter, process=boom)

    async def run():
        return await performer.start(_request())

    ready = _run(run())
    assert ready.status == "failed"
    assert ready.clip_path is None
    assert ready.frame_url is None
    assert ready.request_id == REQUEST_ID
    assert meter.ledger.records()[0].final_remote_state == "failed"
    assert performer.consecutive_failures == 1


def test_ready_take_records_fal_inference_and_cook_clocks(tmp_path: Path) -> None:
    from runtime_flight.performer_fal import FalCookTimings, parse_fal_timings, inference_seconds

    assert parse_fal_timings({"timings": {"inference": 2.71, "queue": 0.4}}) == {
        "inference": 2.71,
        "queue": 0.4,
    }
    assert inference_seconds({"inference": 2.71}) == 2.71
    assert parse_fal_timings({"video": {"url": VIDEO_URL}}) is None

    async def reconcile(handle: QueueHandle) -> QueueResult:
        del handle
        return _completed(
            {
                "video": {"url": VIDEO_URL},
                "timings": {"inference": 2.71},
            }
        )

    performer = _performer(tmp_path, gateway=FakeGateway(reconcile=reconcile))

    async def run():
        return await performer.start(_request())

    ready = _run(run())
    assert ready.status == "ready"
    assert isinstance(ready.cook, FalCookTimings)
    assert ready.cook.t_inference_s == 2.71
    assert ready.cook.timings == {"inference": 2.71}
    assert ready.cook.t_submit_s is not None
    assert ready.cook.t_poll_s is not None
    assert ready.cook.t_completed_s is not None
    assert ready.cook.t_download_s is not None
    assert ready.cook.t_post_s is not None
    assert ready.cook.t_cook_s is not None
    log = tmp_path / "logs" / "fal_cook.jsonl"
    assert log.is_file()
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert row["t_inference_s"] == 2.71
    assert row["status"] == "ready"
    assert row["duration_s"] == 5
    timeline = tmp_path / "logs" / "timeline.html"
    assert timeline.is_file()
    assert "Flame graph" in timeline.read_text(encoding="utf-8")


def test_missing_fal_timings_leave_inference_none(tmp_path: Path) -> None:
    performer = _performer(tmp_path)

    async def run():
        return await performer.start(_request())

    ready = _run(run())
    assert ready.status == "ready"
    assert ready.cook is not None
    assert ready.cook.t_inference_s is None
    assert ready.cook.timings is None
    assert ready.cook.t_cook_s is not None


def test_source_does_not_use_harness_level_spend_check_or_root_scaffold() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "performer_fal.py"
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
    assert "spend.check" not in source
    assert "from run_live" not in source
    assert "from generator" not in source
    assert "import generator" not in source
    assert "submit_async" not in source


def test_repr_and_public_strings_omit_secrets(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    performer = _performer(tmp_path)
    rendered = repr(performer) + str(performer)
    assert FAL_KEY not in rendered
    assert "Authorization" not in rendered
    captured = capsys.readouterr()
    assert FAL_KEY not in captured.out
    assert FAL_KEY not in captured.err
