"""Task 9: single-POST fal queue gateway. Fake HTTP only; no live fal jobs."""

from __future__ import annotations

import ast
import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from runtime_flight.fal_gateway import (
    QUEUE_SUBMIT_URL,
    FalGateway,
    FalGatewayError,
    FalUnknownSubmission,
    QueueHandle,
    QueueResult,
)
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

FAL_KEY = "fal-test-key-should-never-appear"
RATE = Decimal("0.08")
HASH_A = "a" * 64
ARGUMENTS = {
    "prompt": "locked wide two-shot",
    "duration": 5,
    "resolution": "768P",
    "enable_safety_checker": True,
    "prompt_expansion_mode": "balanced",
    "image_url": "https://v3.fal.media/files/hero.png",
}
REQUEST_ID = "req-h3-1"
STATUS_URL = f"https://queue.fal.run/minimax/h3-max/image-to-video/requests/{REQUEST_ID}/status"
RESPONSE_URL = f"https://queue.fal.run/minimax/h3-max/image-to-video/requests/{REQUEST_ID}"
CANCEL_URL = f"https://queue.fal.run/minimax/h3-max/image-to-video/requests/{REQUEST_ID}/cancel"


class FakeResponse:
    def __init__(self, status_code: int, body: Any = None) -> None:
        self.status_code = status_code
        self._body = {} if body is None else body

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _handle() -> QueueHandle:
    return QueueHandle(
        request_id=REQUEST_ID,
        status_url=STATUS_URL,
        response_url=RESPONSE_URL,
        cancel_url=CANCEL_URL,
    )


def _enqueue_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "request_id": REQUEST_ID,
        "status_url": STATUS_URL,
        "response_url": RESPONSE_URL,
        "cancel_url": CANCEL_URL,
    }
    body.update(overrides)
    return body


def _run(coro):
    return asyncio.run(coro)


def _gateway(http_request, clock: FakeClock | None = None) -> FalGateway:
    clock = clock or FakeClock()
    return FalGateway(
        fal_key=FAL_KEY,
        http_request=http_request,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )


def test_submit_posts_queue_once_with_key_authorization() -> None:
    calls: list[dict[str, Any]] = []

    async def http_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        calls.append({"method": method, "url": url, **kwargs})
        return FakeResponse(200, _enqueue_body())

    handle = _run(_gateway(http_request).submit(ARGUMENTS))
    assert handle == _handle()
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == QUEUE_SUBMIT_URL
    assert calls[0]["url"] == "https://queue.fal.run/minimax/h3-max/image-to-video"
    headers = calls[0]["headers"]
    assert headers["Authorization"] == f"Key {FAL_KEY}"
    assert headers["Content-Type"] == "application/json"
    assert calls[0]["json"] == ARGUMENTS


@pytest.mark.parametrize("failure", ["timeout", 429, 503])
def test_submit_performs_exactly_one_post_on_timeout_429_or_5xx(failure: Any) -> None:
    posts = 0

    async def http_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        nonlocal posts
        if method == "POST":
            posts += 1
            if failure == "timeout":
                raise TimeoutError("queue post timed out")
            return FakeResponse(int(failure), {"error": "busy"})
        raise AssertionError(f"unexpected {method} {url}")

    with pytest.raises((FalUnknownSubmission, FalGatewayError, TimeoutError)):
        _run(_gateway(http_request).submit(ARGUMENTS))
    assert posts == 1


def test_submit_rejects_non_https_or_wrong_host_urls() -> None:
    async def http_http(method: str, url: str, **kwargs: Any) -> FakeResponse:
        return FakeResponse(
            200,
            _enqueue_body(status_url="http://queue.fal.run/requests/x/status"),
        )

    async def http_host(method: str, url: str, **kwargs: Any) -> FakeResponse:
        return FakeResponse(
            200,
            _enqueue_body(status_url="https://evil.example/requests/x/status"),
        )

    with pytest.raises(FalGatewayError, match="https|host|queue.fal.run"):
        _run(_gateway(http_http).submit(ARGUMENTS))
    with pytest.raises(FalGatewayError, match="https|host|queue.fal.run"):
        _run(_gateway(http_host).submit(ARGUMENTS))


def test_reconcile_polls_status_with_auth_and_fetches_result_once_on_completed() -> None:
    clock = FakeClock()
    calls: list[tuple[str, str]] = []

    async def http_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        calls.append((method, url))
        headers = kwargs["headers"]
        assert headers["Authorization"] == f"Key {FAL_KEY}"
        if method == "GET" and url == STATUS_URL:
            if clock.now < 0.6:
                return FakeResponse(200, {"status": "IN_QUEUE", "queue_position": 1})
            return FakeResponse(200, {"status": "COMPLETED"})
        if method == "GET" and url == RESPONSE_URL:
            return FakeResponse(200, {"video": {"url": "https://v3.fal.media/files/out.mp4"}})
        raise AssertionError(f"unexpected {method} {url}")

    result = _run(_gateway(http_request, clock).reconcile(_handle()))
    assert isinstance(result, QueueResult)
    assert result.remote_state == "COMPLETED"
    assert result.payload == {"video": {"url": "https://v3.fal.media/files/out.mp4"}}
    assert result.unknown_submission is False
    status_gets = [c for c in calls if c == ("GET", STATUS_URL)]
    response_gets = [c for c in calls if c == ("GET", RESPONSE_URL)]
    assert status_gets
    assert len(response_gets) == 1
    assert all(interval == 0.25 for interval in clock.sleeps)


def test_poll_interval_schedule_250ms_then_500ms_then_2s() -> None:
    clock = FakeClock()

    async def http_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        if method == "GET" and url == STATUS_URL:
            if clock.now < 12.0:
                return FakeResponse(200, {"status": "IN_PROGRESS"})
            return FakeResponse(200, {"status": "COMPLETED"})
        if method == "GET" and url == RESPONSE_URL:
            return FakeResponse(200, {"ok": True})
        raise AssertionError(f"unexpected {method} {url}")

    _run(_gateway(http_request, clock).reconcile(_handle()))
    early = [s for s, t in _sleeps_at(clock) if t < 2.0]
    mid = [s for s, t in _sleeps_at(clock) if 2.0 <= t < 10.0]
    late = [s for s, t in _sleeps_at(clock) if t >= 10.0]
    assert early and all(s == 0.25 for s in early)
    assert mid and all(s == 0.5 for s in mid)
    assert late and all(s == 2.0 for s in late)


def _sleeps_at(clock: FakeClock) -> list[tuple[float, float]]:
    elapsed = 0.0
    pairs: list[tuple[float, float]] = []
    for sleep in clock.sleeps:
        pairs.append((sleep, elapsed))
        elapsed += sleep
    return pairs


def test_reconcile_stops_after_120_seconds_without_second_post() -> None:
    clock = FakeClock()
    posts = 0

    async def http_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        nonlocal posts
        if method == "POST":
            posts += 1
            raise AssertionError("reconcile must not POST")
        if method == "GET" and url == STATUS_URL:
            return FakeResponse(200, {"status": "IN_PROGRESS"})
        raise AssertionError(f"unexpected {method} {url}")

    result = _run(_gateway(http_request, clock).reconcile(_handle()))
    assert posts == 0
    assert result.unknown_submission is False
    assert result.request_id == REQUEST_ID
    assert clock.now >= 120
    assert result.remote_state != "unknown_submission"


def test_cancel_is_one_put_then_status_poll_for_at_most_10s() -> None:
    clock = FakeClock()
    puts = 0

    async def http_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        nonlocal puts
        headers = kwargs["headers"]
        assert headers["Authorization"] == f"Key {FAL_KEY}"
        if method == "PUT":
            puts += 1
            assert url == CANCEL_URL
            return FakeResponse(200, {"status": "CANCELLING"})
        if method == "GET" and url == STATUS_URL:
            if clock.now < 1.0:
                return FakeResponse(200, {"status": "IN_PROGRESS"})
            return FakeResponse(200, {"status": "CANCELED"})
        if method == "POST":
            raise AssertionError("cancel must not submit")
        raise AssertionError(f"unexpected {method} {url}")

    result = _run(_gateway(http_request, clock).cancel(_handle()))
    assert puts == 1
    assert result.remote_state == "CANCELED"
    assert clock.now <= 10
    assert result.payload is None


def test_cancel_does_not_assume_canceled_until_remote_says_so() -> None:
    clock = FakeClock()

    async def http_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        if method == "PUT":
            return FakeResponse(200, {"accepted": True})
        if method == "GET" and url == STATUS_URL:
            return FakeResponse(200, {"status": "IN_PROGRESS"})
        raise AssertionError(f"unexpected {method} {url}")

    result = _run(_gateway(http_request, clock).cancel(_handle()))
    assert result.remote_state == "IN_PROGRESS"
    assert result.remote_state != "CANCELED"
    assert clock.now >= 10


def test_local_timeout_without_request_id_is_unknown_submission() -> None:
    result = _run(
        _gateway(lambda *a, **k: (_ for _ in ()).throw(AssertionError("no http"))).handle_local_timeout(
            None
        )
    )
    assert result.unknown_submission is True
    assert result.remote_state == "unknown_submission"
    assert result.request_id is None


def test_local_timeout_with_request_id_reconciles_or_cancels_once_never_resubmits() -> None:
    clock = FakeClock()
    posts = 0
    puts = 0

    async def http_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        nonlocal posts, puts
        if method == "POST":
            posts += 1
            raise AssertionError("must not submit a replacement")
        if method == "PUT":
            puts += 1
            return FakeResponse(200, {})
        if method == "GET" and url == STATUS_URL:
            return FakeResponse(200, {"status": "CANCELED"})
        raise AssertionError(f"unexpected {method} {url}")

    gateway = _gateway(http_request, clock)
    kept = _run(gateway.handle_local_timeout(_handle(), cancel=False))
    canceled = _run(gateway.handle_local_timeout(_handle(), cancel=True))
    assert posts == 0
    assert puts == 1
    assert kept.request_id == REQUEST_ID
    assert canceled.remote_state == "CANCELED"


def test_network_submission_requires_fsynced_reservation_first(tmp_path: Path) -> None:
    ledger_path = tmp_path / "reservations.jsonl"
    ledger = SpendLedger(ledger_path)
    meter = SpendMeter(
        cap_usd=Decimal("2.00"),
        rate_768p_usd_per_s=RATE,
        duration_s=5,
        mode="smoke",
        ledger=ledger,
    )
    seen_on_disk = []

    async def http_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        if method == "POST":
            reloaded = SpendLedger(ledger_path)
            seen_on_disk.append(list(reloaded.records()))
            return FakeResponse(200, _enqueue_body())
        raise AssertionError(f"unexpected {method} {url}")

    async def run() -> QueueHandle:
        reservation = meter.reserve_attempt(1, 1, arguments_sha256(ARGUMENTS))
        handle = await _gateway(http_request).submit(ARGUMENTS)
        await ledger.attach_request_id(reservation.id, handle.request_id)
        ledger.persist_handle(reservation.id, handle)
        return handle

    handle = _run(run())
    assert handle.request_id == REQUEST_ID
    assert len(seen_on_disk) == 1
    assert len(seen_on_disk[0]) == 1
    row = seen_on_disk[0][0]
    assert row.take == 1
    assert row.attempt == 1
    persisted = SpendLedger(ledger_path).get(row.id)
    assert persisted is not None
    assert persisted.request_id == REQUEST_ID
    assert persisted.status_url == STATUS_URL
    parsed = urlparse(persisted.status_url)
    assert parsed.scheme == "https"
    assert parsed.hostname == "queue.fal.run"


def test_unknown_submit_marks_reservation_and_never_posts_again(tmp_path: Path) -> None:
    meter = SpendMeter(
        cap_usd=Decimal("2.00"),
        rate_768p_usd_per_s=RATE,
        duration_s=5,
        mode="smoke",
        ledger=SpendLedger(tmp_path / "reservations.jsonl"),
    )
    posts = 0

    async def http_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        nonlocal posts
        if method == "POST":
            posts += 1
            raise TimeoutError("no request id")
        raise AssertionError("no follow-up http")

    async def run() -> None:
        reservation = meter.reserve_attempt(1, 1, HASH_A)
        with pytest.raises((FalUnknownSubmission, TimeoutError, FalGatewayError)):
            await _gateway(http_request).submit(ARGUMENTS)
        meter.ledger.mark_unknown_submission(reservation.id)

    _run(run())
    assert posts == 1
    row = meter.ledger.records()[0]
    assert row.final_remote_state == "unknown_submission"
    assert meter.total == Decimal("0.40")


def test_gateway_repr_and_errors_omit_secrets(capsys: pytest.CaptureFixture[str]) -> None:
    async def http_request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        raise TimeoutError("queue post timed out")

    gateway = _gateway(http_request)
    rendered = repr(gateway) + str(gateway)
    assert FAL_KEY not in rendered
    assert "Authorization" not in rendered
    with pytest.raises(Exception) as error:
        _run(gateway.submit(ARGUMENTS))
    assert FAL_KEY not in str(error.value)
    assert "Authorization" not in str(error.value)
    captured = capsys.readouterr()
    assert FAL_KEY not in captured.out
    assert FAL_KEY not in captured.err


def test_production_client_disables_transport_retries() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "fal_gateway.py"
    source = path.read_text(encoding="utf-8")
    assert "retries=0" in source
    assert "submit_async" not in source
    assert "fal_client" not in source
    client = FalGateway.no_retry_async_client()
    transport = client._transport
    retries = getattr(getattr(transport, "_pool", None), "_retries", None)
    if retries is None:
        retries = getattr(transport, "retries", 0)
    assert retries == 0


def test_fal_gateway_module_does_not_import_root_scaffold() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "fal_gateway.py"
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
    assert "from generator" not in source
    assert "from run_live" not in source
