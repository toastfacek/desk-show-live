"""Sunday / until clock. No network."""

from datetime import datetime, timezone

import pytest

from runtime_flight.sunday import UntilError, resolve_until


def test_sunday_from_wednesday_is_that_weekend() -> None:
    now = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)
    until = resolve_until("sunday", now=now)
    assert until == datetime(2026, 9, 6, 23, 59, 59, tzinfo=timezone.utc)


def test_sunday_on_sunday_before_midnight_is_today() -> None:
    now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
    until = resolve_until("sunday", now=now)
    assert until == datetime(2026, 9, 6, 23, 59, 59, tzinfo=timezone.utc)


def test_sunday_after_deadline_rolls_a_week() -> None:
    now = datetime(2026, 9, 6, 23, 59, 59, tzinfo=timezone.utc)
    until = resolve_until("sunday", now=now)
    assert until == datetime(2026, 9, 13, 23, 59, 59, tzinfo=timezone.utc)


def test_until_iso_timestamp() -> None:
    until = resolve_until("2026-09-06T12:00:00Z")
    assert until == datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def test_until_rejects_junk() -> None:
    with pytest.raises(UntilError):
        resolve_until("monday")
