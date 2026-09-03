"""Whether the orchestrator can still fund the next tweet."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal


class UntilError(Exception):
    """Raised when --until cannot be parsed."""


def has_runway(
    *,
    reserved_usd: Decimal,
    cap_usd: Decimal,
    take_cost_usd: Decimal,
    text_left: int,
    pending: int,
) -> bool:
    if pending < 1:
        return False
    if text_left < 1:
        return False
    if reserved_usd + take_cost_usd > cap_usd:
        return False
    return True


def resolve_until(value: str | None, *, now: datetime | None = None) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise UntilError("until must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    del now
    return parsed
