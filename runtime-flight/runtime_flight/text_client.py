"""Shared OpenAI-shaped JSON text client with a request-count limiter."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2

HttpPost = Callable[..., Awaitable[Any]]


class TextClientError(Exception):
    """Raised when a text completion cannot be parsed into a JSON object."""


class TextAttemptLimiter:
    """Count text HTTP attempts before they are sent. Shared across callers."""

    def __init__(self, max_requests: int) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        self.max_requests = max_requests
        self.attempts = 0

    def count_before_request(self) -> None:
        if self.attempts >= self.max_requests:
            raise TextClientError("text request budget exceeded")
        self.attempts += 1


class TextClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        limiter: TextAttemptLimiter,
        http_post: HttpPost | None = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._limiter = limiter
        self._http_post = http_post

    def __repr__(self) -> str:
        return f"TextClient(model={self._model!r})"

    def __str__(self) -> str:
        return self.__repr__()

    async def complete_json(self, *, system: str, user: dict) -> dict:
        self._limiter.count_before_request()
        url = f"{self._base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, separators=(",", ":"))},
            ],
            "temperature": 0.4,
        }
        try:
            response = await self._post(url, headers, payload)
        except asyncio.CancelledError:
            raise
        except (TimeoutError, httpx2.TimeoutException) as error:
            raise TextClientError("text request timed out") from error
        except TextClientError:
            raise
        except Exception as error:
            raise TextClientError("text request failed") from error

        status = getattr(response, "status_code", None)
        if not isinstance(status, int) or status < 200 or status >= 300:
            raise TextClientError("HTTP response was not 2xx")
        try:
            body = response.json()
        except Exception as error:
            raise TextClientError("response body is not JSON") from error
        if not isinstance(body, dict):
            raise TextClientError("response body is not a JSON object")

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise TextClientError("response missing assistant content") from error
        if not isinstance(content, str):
            raise TextClientError("assistant content is not a string")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise TextClientError("assistant content is not JSON") from error
        if not isinstance(parsed, dict):
            raise TextClientError("assistant content is not a JSON object")
        if "usage" in body and not isinstance(body["usage"], dict):
            raise TextClientError("usage must be a JSON object")
        return parsed

    async def _post(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> Any:
        if self._http_post is not None:
            return await self._http_post(
                url,
                headers=headers,
                json=payload,
                timeout=8.0,
            )
        async with httpx2.AsyncClient() as client:
            return await client.post(
                url,
                headers=headers,
                json=payload,
                timeout=8.0,
            )
