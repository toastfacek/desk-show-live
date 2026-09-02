"""Single-POST fal queue gateway. One HTTP POST; no transport or status retry."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx2

QUEUE_SUBMIT_URL = "https://queue.fal.run/minimax/h3-max/image-to-video"
QUEUE_HOST = "queue.fal.run"
RECONCILE_LIMIT_S = 120.0
CANCEL_POLL_LIMIT_S = 10.0
POST_TIMEOUT_S = 30.0
GET_TIMEOUT_S = 15.0

HttpRequest = Callable[..., Awaitable[Any]]
SleepFn = Callable[[float], Awaitable[None]]
MonotonicFn = Callable[[], float]


class FalGatewayError(Exception):
    """Raised when a queue submit or reconcile cannot be completed safely."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        unknown_submission: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.unknown_submission = unknown_submission


class FalUnknownSubmission(FalGatewayError):
    """POST finished without a usable request ID. Do not submit a replacement."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message, status_code=status_code, unknown_submission=True)


@dataclass(frozen=True)
class QueueHandle:
    request_id: str
    status_url: str
    response_url: str
    cancel_url: str


@dataclass(frozen=True)
class QueueResult:
    request_id: str | None
    remote_state: str
    payload: dict[str, Any] | None
    unknown_submission: bool
    t_first_progress_s: float | None = None
    t_completed_s: float | None = None


def poll_interval(elapsed_s: float) -> float:
    if elapsed_s < 2.0:
        return 0.25
    if elapsed_s < 10.0:
        return 0.5
    return 2.0


class FalGateway:
    def __init__(
        self,
        *,
        fal_key: str,
        http_request: HttpRequest | None = None,
        sleep: SleepFn | None = None,
        monotonic: MonotonicFn | None = None,
    ) -> None:
        self._fal_key = fal_key
        self._http_request = http_request
        self._sleep = sleep
        self._monotonic_fn = monotonic

    def __repr__(self) -> str:
        return "FalGateway()"

    def __str__(self) -> str:
        return self.__repr__()

    @staticmethod
    def no_retry_async_client(**kwargs: Any) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.AsyncHTTPTransport(retries=0),
            **kwargs,
        )

    async def submit(self, arguments: dict[str, Any]) -> QueueHandle:
        try:
            response = await self._request(
                "POST",
                QUEUE_SUBMIT_URL,
                json=arguments,
                timeout=POST_TIMEOUT_S,
            )
        except asyncio.CancelledError:
            raise
        except (TimeoutError, httpx2.TimeoutException) as error:
            raise FalUnknownSubmission("queue submit timed out") from error
        except FalGatewayError:
            raise
        except Exception as error:
            raise FalUnknownSubmission("queue submit failed") from error

        status = getattr(response, "status_code", None)
        if status == 422:
            raise FalGatewayError(
                "queue submit rejected",
                status_code=422,
                unknown_submission=False,
            )
        if not isinstance(status, int) or status < 200 or status >= 300:
            raise FalUnknownSubmission(
                "queue submit was not accepted",
                status_code=status if isinstance(status, int) else None,
            )
        try:
            body = response.json()
        except Exception as error:
            raise FalUnknownSubmission("queue submit body is not JSON") from error
        if not isinstance(body, dict):
            raise FalUnknownSubmission("queue submit body is not a JSON object")
        try:
            handle = QueueHandle(
                request_id=body["request_id"],
                status_url=body["status_url"],
                response_url=body["response_url"],
                cancel_url=body["cancel_url"],
            )
            self._validate_handle(handle)
        except (KeyError, TypeError, ValueError, FalGatewayError) as error:
            raise FalUnknownSubmission(
                "queue submit returned an unusable handle"
            ) from error
        return handle

    async def reconcile(self, handle: QueueHandle) -> QueueResult:
        self._validate_handle(handle)
        return await self._poll_until(
            handle,
            limit_s=RECONCILE_LIMIT_S,
            fetch_result=True,
        )

    async def cancel(self, handle: QueueHandle) -> QueueResult:
        self._validate_handle(handle)
        try:
            await self._request("PUT", handle.cancel_url, timeout=GET_TIMEOUT_S)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Local PUT success is not proof billing stopped; still poll status.
            pass
        return await self._poll_until(
            handle,
            limit_s=CANCEL_POLL_LIMIT_S,
            fetch_result=False,
        )

    async def handle_local_timeout(
        self,
        handle: QueueHandle | None,
        *,
        cancel: bool = False,
    ) -> QueueResult:
        if handle is None:
            return QueueResult(
                request_id=None,
                remote_state="unknown_submission",
                payload=None,
                unknown_submission=True,
            )
        if cancel:
            return await self.cancel(handle)
        return await self.reconcile(handle)

    async def _poll_until(
        self,
        handle: QueueHandle,
        *,
        limit_s: float,
        fetch_result: bool,
    ) -> QueueResult:
        start = self._now()
        last_state = "IN_QUEUE"
        first_progress_s: float | None = None
        while True:
            elapsed = self._now() - start
            if elapsed >= limit_s:
                break
            status = await self._read_status(handle.status_url)
            if status is not None:
                last_state = status
            if last_state == "IN_PROGRESS" and first_progress_s is None:
                first_progress_s = self._now() - start
            if last_state == "COMPLETED":
                payload = await self._read_result(handle.response_url) if fetch_result else None
                return QueueResult(
                    request_id=handle.request_id,
                    remote_state="COMPLETED",
                    payload=payload,
                    unknown_submission=False,
                    t_first_progress_s=first_progress_s,
                    t_completed_s=self._now() - start,
                )
            if last_state == "CANCELED":
                return QueueResult(
                    request_id=handle.request_id,
                    remote_state="CANCELED",
                    payload=None,
                    unknown_submission=False,
                )
            interval = poll_interval(elapsed)
            remaining = limit_s - (self._now() - start)
            if remaining <= 0:
                break
            await self._pause(min(interval, remaining))
        return QueueResult(
            request_id=handle.request_id,
            remote_state=last_state,
            payload=None,
            unknown_submission=False,
        )

    async def _read_status(self, url: str) -> str | None:
        try:
            response = await self._request("GET", url, timeout=GET_TIMEOUT_S)
        except (TimeoutError, httpx2.TimeoutException, FalGatewayError):
            return None
        except Exception:
            return None
        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int) or status_code < 200 or status_code >= 300:
            return None
        try:
            body = response.json()
        except Exception:
            return None
        if not isinstance(body, dict):
            return None
        status = body.get("status")
        if not isinstance(status, str) or status == "":
            return None
        return status

    async def _read_result(self, url: str) -> dict[str, Any]:
        response = await self._request("GET", url, timeout=GET_TIMEOUT_S)
        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int) or status_code < 200 or status_code >= 300:
            raise FalGatewayError("result GET was not 2xx")
        body = response.json()
        if not isinstance(body, dict):
            raise FalGatewayError("result body is not a JSON object")
        return body

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        timeout: float = GET_TIMEOUT_S,
    ) -> Any:
        headers = {
            "Authorization": f"Key {self._fal_key}",
            "Content-Type": "application/json",
        }
        if self._http_request is not None:
            return await self._http_request(
                method,
                url,
                headers=headers,
                json=json,
                timeout=timeout,
            )
        async with self.no_retry_async_client() as client:
            return await client.request(
                method,
                url,
                headers=headers,
                json=json,
                timeout=timeout,
            )

    async def _pause(self, seconds: float) -> None:
        if self._sleep is not None:
            await self._sleep(seconds)
            return
        await asyncio.sleep(seconds)

    def _now(self) -> float:
        if self._monotonic_fn is not None:
            return self._monotonic_fn()
        return time.monotonic()

    def _validate_handle(self, handle: QueueHandle) -> None:
        if not isinstance(handle.request_id, str) or handle.request_id == "":
            raise FalGatewayError("request_id must be a non-empty string")
        for label, url in (
            ("status_url", handle.status_url),
            ("response_url", handle.response_url),
            ("cancel_url", handle.cancel_url),
        ):
            _require_queue_url(url, label)


def _require_queue_url(url: str, label: str) -> None:
    if not isinstance(url, str) or url == "":
        raise FalGatewayError(f"{label} must be https host queue.fal.run")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != QUEUE_HOST:
        raise FalGatewayError(f"{label} must be https host queue.fal.run")
