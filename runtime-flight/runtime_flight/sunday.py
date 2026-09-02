"""Stop the orchestrator at the end of Sunday, or an explicit timestamp."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


class UntilError(Exception):
    """Raised when --until cannot be parsed."""


def resolve_until(value: str, *, now: datetime | None = None) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise UntilError("until is missing")
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    text = value.strip()
    if text.lower() == "sunday":
        return _end_of_sunday(clock)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise UntilError("until must be 'sunday' or an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _end_of_sunday(now: datetime) -> datetime:
    days = (6 - now.weekday()) % 7
    end = (now + timedelta(days=days)).replace(hour=23, minute=59, second=59, microsecond=0)
    if days == 0 and now >= end:
        end = end + timedelta(days=7)
    return end
