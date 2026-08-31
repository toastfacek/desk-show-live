"""Panic and signal cleanup for live flight operator commands."""

from __future__ import annotations

import signal
from collections.abc import Callable
from types import FrameType
from typing import Any

CleanupFn = Callable[[], None]
SignalHandler = Callable[[int, FrameType | None], Any]


def install_panic_handler(
    cleanup: CleanupFn,
    *,
    signals: tuple[int, ...] = (signal.SIGINT, signal.SIGTERM),
) -> SignalHandler:
    def _handler(signum: int, frame: FrameType | None) -> None:
        cleanup()
        raise SystemExit(1)

    for item in signals:
        signal.signal(item, _handler)
    return _handler
