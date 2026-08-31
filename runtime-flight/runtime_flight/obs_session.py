"""OBS recording and stream-safety lifecycle outside the public Player protocol."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator, Protocol

from runtime_flight.obs_setup import ensure_contract


class ObsLifecycleClient(Protocol):
    def get_stream_status(self) -> Any: ...

    def get_record_status(self) -> Any: ...

    def start_record(self) -> Any: ...

    def stop_record(self) -> Any: ...


class ObsSession:
    def __init__(
        self,
        *,
        client: ObsLifecycleClient | None = None,
        player: Any | None = None,
        live_mode: bool = False,
        finalize_timeout_s: float = 30.0,
        poll_interval_s: float = 0.05,
    ) -> None:
        if client is None and player is None:
            raise ValueError("ObsSession requires client or player")
        self._client = client if client is not None else player._client
        self.player = player
        self.live_mode = live_mode
        self.finalize_timeout_s = finalize_timeout_s
        self.poll_interval_s = poll_interval_s

    def ensure_contract(self) -> None:
        ensure_contract(self._client, create=not self.live_mode)

    def is_streaming(self) -> bool:
        return bool(getattr(self._client.get_stream_status(), "output_active", False))

    def refuse_streaming(self) -> None:
        if self.is_streaming():
            raise RuntimeError("OBS is already streaming; refusing to continue")

    def _record_status(self) -> Any:
        return self._client.get_record_status()

    def _recording_active(self) -> bool:
        return bool(getattr(self._record_status(), "output_active", False))

    def recording_duration_s(self) -> float:
        duration_ms = getattr(self._record_status(), "output_duration", 0) or 0
        return duration_ms / 1000.0

    def start_recording(self) -> None:
        self.refuse_streaming()
        self._client.start_record()
        deadline = time.monotonic() + self.finalize_timeout_s
        while time.monotonic() < deadline:
            if self._recording_active():
                return
            time.sleep(self.poll_interval_s)
        raise RuntimeError("OBS recording did not become active")

    def stop_recording(self) -> str | None:
        if not self._recording_active():
            return None
        result = self._client.stop_record()
        deadline = time.monotonic() + self.finalize_timeout_s
        while time.monotonic() < deadline:
            if not self._recording_active():
                return getattr(result, "output_path", None)
            time.sleep(self.poll_interval_s)
        raise RuntimeError("OBS recording did not finalize")

    @contextmanager
    def recording_session(self) -> Iterator[None]:
        try:
            yield
        finally:
            self.stop_recording()
