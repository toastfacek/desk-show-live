"""Reservation-based spend meter and durable request ledger. Decimal only."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

VIDEO_DURATION_S = 5
SMOKE_MAX_ATTEMPTS = 2


class SpendError(Exception):
    """Raised when a reservation cannot be created or updated."""


class SpendCapExceeded(SpendError):
    """Raised when total + next_cost would exceed the confirmed cap."""


class DuplicateReservationError(SpendError):
    """Raised when a take/attempt pair is reserved twice."""


class SmokeLimitExceeded(SpendError):
    """Raised when smoke mode already has two submission attempts."""


@dataclass(frozen=True)
class AttemptReservation:
    id: str
    take: int
    attempt: int
    arguments_sha256: str
    reserved_cost_usd: Decimal


@dataclass(frozen=True)
class LedgerRow:
    id: str
    take: int
    attempt: int
    arguments_sha256: str
    reserved_cost_usd: Decimal
    request_id: str | None
    status_url: str | None
    response_url: str | None
    cancel_url: str | None
    submitted_at: str | None
    finished_at: str | None
    final_remote_state: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "take": self.take,
            "attempt": self.attempt,
            "arguments_sha256": self.arguments_sha256,
            "reserved_cost_usd": str(self.reserved_cost_usd),
            "request_id": self.request_id,
            "status_url": self.status_url,
            "response_url": self.response_url,
            "cancel_url": self.cancel_url,
            "submitted_at": self.submitted_at,
            "finished_at": self.finished_at,
            "final_remote_state": self.final_remote_state,
        }

    def evolve(self, **changes: Any) -> LedgerRow:
        payload = self.as_dict()
        payload.update(changes)
        payload["reserved_cost_usd"] = (
            changes["reserved_cost_usd"]
            if "reserved_cost_usd" in changes
            else self.reserved_cost_usd
        )
        return LedgerRow(**payload)


def arguments_sha256(arguments: dict[str, Any]) -> str:
    payload = json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    return value


class SpendLedger:
    """JSONL reservation ledger. Every mutation is rewritten and fsynced."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._rows: dict[str, LedgerRow] = {}
        if path.exists():
            self._load()

    def records(self) -> list[LedgerRow]:
        return list(self._rows.values())

    def get(self, reservation_id: str) -> LedgerRow | None:
        return self._rows.get(reservation_id)

    def persist_reservation(self, reservation: AttemptReservation) -> None:
        self._rows[reservation.id] = LedgerRow(
            id=reservation.id,
            take=reservation.take,
            attempt=reservation.attempt,
            arguments_sha256=reservation.arguments_sha256,
            reserved_cost_usd=reservation.reserved_cost_usd,
            request_id=None,
            status_url=None,
            response_url=None,
            cancel_url=None,
            submitted_at=None,
            finished_at=None,
            final_remote_state=None,
        )
        self._fsync_write()

    async def attach_request_id(self, reservation_id: str, request_id: str) -> None:
        row = self._require(reservation_id)
        self._rows[reservation_id] = row.evolve(
            request_id=request_id,
            submitted_at=row.submitted_at or _utc_now(),
        )
        self._fsync_write()

    def persist_handle(self, reservation_id: str, handle: Any) -> None:
        row = self._require(reservation_id)
        self._rows[reservation_id] = row.evolve(
            request_id=handle.request_id,
            status_url=handle.status_url,
            response_url=handle.response_url,
            cancel_url=handle.cancel_url,
            submitted_at=row.submitted_at or _utc_now(),
        )
        self._fsync_write()

    def mark_unknown_submission(self, reservation_id: str) -> None:
        row = self._require(reservation_id)
        self._rows[reservation_id] = row.evolve(
            finished_at=_utc_now(),
            final_remote_state="unknown_submission",
        )
        self._fsync_write()

    def mark_finished(self, reservation_id: str, remote_state: str) -> None:
        row = self._require(reservation_id)
        self._rows[reservation_id] = row.evolve(
            finished_at=_utc_now(),
            final_remote_state=remote_state,
        )
        self._fsync_write()

    def evidence(self, reservation_id: str) -> dict[str, Any]:
        row = self._require(reservation_id)
        return {
            "reservation_id": row.id,
            "take": row.take,
            "attempt": row.attempt,
            "request_id": row.request_id,
            "arguments_sha256": row.arguments_sha256,
            "submitted_at": row.submitted_at,
            "finished_at": row.finished_at,
            "final_remote_state": row.final_remote_state,
            "reserved_cost_usd": str(row.reserved_cost_usd),
        }

    def _require(self, reservation_id: str) -> LedgerRow:
        row = self._rows.get(reservation_id)
        if row is None:
            raise SpendError(f"unknown reservation: {reservation_id}")
        return row

    def _load(self) -> None:
        text = self.path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if not line:
                continue
            raw = json.loads(line)
            row = LedgerRow(
                id=raw["id"],
                take=raw["take"],
                attempt=raw["attempt"],
                arguments_sha256=raw["arguments_sha256"],
                reserved_cost_usd=Decimal(str(raw["reserved_cost_usd"])),
                request_id=raw.get("request_id"),
                status_url=raw.get("status_url"),
                response_url=raw.get("response_url"),
                cancel_url=raw.get("cancel_url"),
                submitted_at=raw.get("submitted_at"),
                finished_at=raw.get("finished_at"),
                final_remote_state=raw.get("final_remote_state"),
            )
            self._rows[row.id] = row

    def _fsync_write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        payload = "".join(json.dumps(row.as_dict(), separators=(",", ":")) + "\n" for row in self._rows.values())
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        dir_fd = os.open(str(self.path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


class SpendMeter:
    def __init__(
        self,
        *,
        cap_usd: Decimal,
        rate_768p_usd_per_s: Decimal,
        duration_s: int = VIDEO_DURATION_S,
        mode: Literal["live", "smoke"] = "live",
        ledger: SpendLedger,
    ) -> None:
        self.cap_usd = _require_decimal(cap_usd, "cap_usd")
        self.rate_768p_usd_per_s = _require_decimal(rate_768p_usd_per_s, "rate_768p_usd_per_s")
        self.duration_s = duration_s
        self.mode = mode
        self.ledger = ledger

    @staticmethod
    def next_cost_usd(rate_768p_usd_per_s: Decimal, duration_s: int = VIDEO_DURATION_S) -> Decimal:
        _require_decimal(rate_768p_usd_per_s, "rate_768p_usd_per_s")
        return rate_768p_usd_per_s * Decimal(duration_s)

    @property
    def next_cost(self) -> Decimal:
        return self.next_cost_usd(self.rate_768p_usd_per_s, self.duration_s)

    @property
    def total(self) -> Decimal:
        acc = Decimal("0")
        for row in self.ledger.records():
            acc += row.reserved_cost_usd
        return acc

    def reserve_attempt(self, take: int, attempt: int, arguments_hash: str) -> AttemptReservation:
        for row in self.ledger.records():
            if row.take == take and row.attempt == attempt:
                raise DuplicateReservationError(
                    f"duplicate take/attempt reservation: {take}/{attempt}"
                )
        if self.mode == "smoke" and len(self.ledger.records()) >= SMOKE_MAX_ATTEMPTS:
            raise SmokeLimitExceeded("smoke permits at most two submission attempts")
        next_cost = self.next_cost
        if self.total + next_cost > self.cap_usd:
            raise SpendCapExceeded(
                f"reservation would bring reserved spend to {self.total + next_cost}, "
                f"cap is {self.cap_usd}"
            )
        reservation = AttemptReservation(
            id=f"take-{take}-attempt-{attempt}",
            take=take,
            attempt=attempt,
            arguments_sha256=arguments_hash,
            reserved_cost_usd=next_cost,
        )
        self.ledger.persist_reservation(reservation)
        return reservation
