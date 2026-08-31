"""OBS recording and stream-safety lifecycle outside the public Player protocol."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator, Protocol

from runtime_flight.obs_setup import ensure_contract as validate_obs_contract


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
        finalize_timeout_s: float = 30.0,
        poll_interval_s: float = 0.05,
    ) -> None:
        if client is None and player is None:
            raise ValueError("ObsSession requires client or player")
        self._client = client if client is not None else player._client
        self.player = player
        self.finalize_timeout_s = finalize_timeout_s
        self.poll_interval_s = poll_interval_s
        self._owns_recording = False

    @property
    def owns_recording(self) -> bool:
        return self._owns_recording

    def ensure_contract(self) -> None:
        validate_obs_contract(self._client)

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

    def _confirm_recording_inactive(self) -> None:
        deadline = time.monotonic() + self.finalize_timeout_s
        while time.monotonic() < deadline:
            try:
                if not self._recording_active():
                    self._owns_recording = False
                    return
            except Exception as exc:
                raise RuntimeError("OBS recording status unavailable") from exc
            time.sleep(self.poll_interval_s)
        raise RuntimeError("OBS recording did not finalize")

    def _cleanup_owned_recording(self) -> None:
        if not self._owns_recording:
            return
        try:
            self._client.stop_record()
        except Exception:
            pass
        self._confirm_recording_inactive()

    def start_recording(self) -> None:
        self.refuse_streaming()
        if self._recording_active():
            raise RuntimeError("OBS is already recording; refusing to continue")

        self._client.start_record()
        self._owns_recording = True
        deadline = time.monotonic() + self.finalize_timeout_s
        try:
            while time.monotonic() < deadline:
                try:
                    if self._recording_active():
                        return
                except Exception:
                    try:
                        self._cleanup_owned_recording()
                    except RuntimeError:
                        pass
                    raise
                time.sleep(self.poll_interval_s)
        except Exception:
            raise

        try:
            self._cleanup_owned_recording()
        except RuntimeError:
            raise RuntimeError("OBS recording did not become active") from None
        raise RuntimeError("OBS recording did not become active")

    def stop_recording(self) -> str | None:
        if not self._owns_recording:
            return None
        if not self._recording_active():
            self._owns_recording = False
            return None
        result = self._client.stop_record()
        self._confirm_recording_inactive()
        return getattr(result, "output_path", None)

    @contextmanager
    def recording_session(self) -> Iterator[None]:
        self.start_recording()
        try:
            yield
        finally:
            try:
                self.stop_recording()
            except RuntimeError:
                pass
