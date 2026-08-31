"""Task 9: reservation-based spend ledger. Decimal only; no live fal."""

from __future__ import annotations

import ast
import os
from decimal import Decimal
from pathlib import Path

import pytest

from runtime_flight.spend import (
    AttemptReservation,
    DuplicateReservationError,
    SmokeLimitExceeded,
    SpendCapExceeded,
    SpendLedger,
    SpendMeter,
    arguments_sha256,
)

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}

RATE = Decimal("0.08")
DURATION_S = 5
NEXT_COST = RATE * Decimal(DURATION_S)  # 0.40
HASH_A = "a" * 64
HASH_B = "b" * 64


def _ledger(tmp_path: Path) -> SpendLedger:
    return SpendLedger(tmp_path / "reservations.jsonl")


def _meter(
    tmp_path: Path,
    *,
    cap: Decimal = Decimal("12.00"),
    mode: str = "live",
    ledger: SpendLedger | None = None,
) -> SpendMeter:
    return SpendMeter(
        cap_usd=cap,
        rate_768p_usd_per_s=RATE,
        duration_s=DURATION_S,
        mode=mode,  # type: ignore[arg-type]
        ledger=ledger or _ledger(tmp_path),
    )


def test_next_cost_is_rate_times_five_seconds_decimal() -> None:
    cost = SpendMeter.next_cost_usd(RATE, DURATION_S)
    assert cost == Decimal("0.40")
    assert isinstance(cost, Decimal)


def test_exact_cap_allows_when_total_plus_next_cost_equals_cap(tmp_path: Path) -> None:
    meter = _meter(tmp_path, cap=Decimal("0.80"))
    first = meter.reserve_attempt(1, 1, HASH_A)
    second = meter.reserve_attempt(2, 1, HASH_B)
    assert first.reserved_cost_usd == NEXT_COST
    assert second.reserved_cost_usd == NEXT_COST
    assert meter.total == Decimal("0.80")
    with pytest.raises(SpendCapExceeded):
        meter.reserve_attempt(3, 1, "c" * 64)


def test_exact_cap_uses_inclusive_less_or_equal(tmp_path: Path) -> None:
    meter = _meter(tmp_path, cap=NEXT_COST)
    reservation = meter.reserve_attempt(1, 1, HASH_A)
    assert reservation.reserved_cost_usd == NEXT_COST
    assert meter.total + NEXT_COST > meter.cap_usd
    with pytest.raises(SpendCapExceeded):
        meter.reserve_attempt(2, 1, HASH_B)


def test_cap_and_totals_reject_float_inputs(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    with pytest.raises(TypeError, match="Decimal"):
        SpendMeter(
            cap_usd=0.80,  # type: ignore[arg-type]
            rate_768p_usd_per_s=RATE,
            duration_s=DURATION_S,
            mode="live",
            ledger=ledger,
        )
    with pytest.raises(TypeError, match="Decimal"):
        SpendMeter(
            cap_usd=Decimal("0.80"),
            rate_768p_usd_per_s=0.08,  # type: ignore[arg-type]
            duration_s=DURATION_S,
            mode="live",
            ledger=ledger,
        )


def test_smoke_permits_at_most_two_attempts_regardless_of_success(
    tmp_path: Path,
) -> None:
    meter = _meter(tmp_path, cap=Decimal("2.00"), mode="smoke")
    first = meter.reserve_attempt(1, 1, HASH_A)
    second = meter.reserve_attempt(1, 2, HASH_B)
    assert first.attempt == 1
    assert second.attempt == 2
    with pytest.raises(SmokeLimitExceeded):
        meter.reserve_attempt(2, 1, "c" * 64)
    assert meter.total == Decimal("0.80")
    assert len(meter.ledger.records()) == 2


def test_smoke_third_attempt_refused_after_unknown_submissions(tmp_path: Path) -> None:
    meter = _meter(tmp_path, cap=Decimal("2.00"), mode="smoke")
    first = meter.reserve_attempt(1, 1, HASH_A)
    second = meter.reserve_attempt(2, 1, HASH_B)
    meter.ledger.mark_unknown_submission(first.id)
    meter.ledger.mark_unknown_submission(second.id)
    with pytest.raises(SmokeLimitExceeded):
        meter.reserve_attempt(3, 1, "c" * 64)


def test_duplicate_take_attempt_ids_are_refused(tmp_path: Path) -> None:
    meter = _meter(tmp_path)
    meter.reserve_attempt(4, 1, HASH_A)
    with pytest.raises(DuplicateReservationError):
        meter.reserve_attempt(4, 1, HASH_B)
    meter.reserve_attempt(4, 2, HASH_B)
    meter.reserve_attempt(5, 1, HASH_A)


def test_reservation_is_fsynced_before_reserve_attempt_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fsynced: list[int] = []
    original = os.fsync

    def _spy(fd: int) -> None:
        fsynced.append(fd)
        original(fd)

    monkeypatch.setattr(os, "fsync", _spy)
    ledger_path = tmp_path / "reservations.jsonl"
    meter = _meter(tmp_path, ledger=SpendLedger(ledger_path))
    reservation = meter.reserve_attempt(1, 1, HASH_A)
    assert fsynced, "reservation must be fsynced before reserve_attempt returns"
    reloaded = SpendLedger(ledger_path)
    persisted = reloaded.get(reservation.id)
    assert persisted is not None
    assert persisted.take == 1
    assert persisted.attempt == 1
    assert persisted.arguments_sha256 == HASH_A
    assert Decimal(str(persisted.reserved_cost_usd)) == NEXT_COST


def test_each_reservation_is_a_separate_durable_row(tmp_path: Path) -> None:
    meter = _meter(tmp_path)
    first = meter.reserve_attempt(1, 1, HASH_A)
    second = meter.reserve_attempt(2, 1, HASH_B)
    assert first.id != second.id
    reloaded = SpendLedger(meter.ledger.path)
    assert {row.id for row in reloaded.records()} == {first.id, second.id}


def test_attach_request_id_persists_and_fsyncs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fsynced: list[int] = []
    original = os.fsync

    def _spy(fd: int) -> None:
        fsynced.append(fd)
        original(fd)

    monkeypatch.setattr(os, "fsync", _spy)
    meter = _meter(tmp_path)
    reservation = meter.reserve_attempt(1, 1, HASH_A)
    fsynced.clear()
    import asyncio

    asyncio.run(meter.ledger.attach_request_id(reservation.id, "req-abc"))
    assert fsynced
    reloaded = SpendLedger(meter.ledger.path)
    row = reloaded.get(reservation.id)
    assert row is not None
    assert row.request_id == "req-abc"


def test_unknown_submission_counts_reservation_and_sets_state(tmp_path: Path) -> None:
    meter = _meter(tmp_path)
    reservation = meter.reserve_attempt(1, 1, HASH_A)
    meter.ledger.mark_unknown_submission(reservation.id)
    assert meter.total == NEXT_COST
    row = meter.ledger.get(reservation.id)
    assert row is not None
    assert row.final_remote_state == "unknown_submission"
    assert row.request_id is None
    evidence = meter.ledger.evidence(reservation.id)
    assert evidence["final_remote_state"] == "unknown_submission"
    assert evidence["reserved_cost_usd"] == str(NEXT_COST)


def test_evidence_fields_include_required_keys(tmp_path: Path) -> None:
    meter = _meter(tmp_path)
    reservation = meter.reserve_attempt(7, 2, HASH_A)
    import asyncio

    asyncio.run(meter.ledger.attach_request_id(reservation.id, "req-xyz"))
    meter.ledger.mark_finished(reservation.id, "COMPLETED")
    evidence = meter.ledger.evidence(reservation.id)
    assert evidence["reservation_id"] == reservation.id
    assert evidence["take"] == 7
    assert evidence["attempt"] == 2
    assert evidence["request_id"] == "req-xyz"
    assert evidence["arguments_sha256"] == HASH_A
    assert evidence["submitted_at"]
    assert evidence["finished_at"]
    assert evidence["final_remote_state"] == "COMPLETED"
    assert evidence["reserved_cost_usd"] == str(NEXT_COST)
    assert isinstance(reservation, AttemptReservation)


def test_arguments_sha256_is_canonical_json() -> None:
    digest = arguments_sha256({"b": 2, "a": 1})
    assert digest == arguments_sha256({"a": 1, "b": 2})
    assert len(digest) == 64


def test_spend_module_does_not_import_root_scaffold_or_fal_client() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "spend.py"
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
    assert "from spend" not in source
    assert "import spend" not in source
    assert "float(" not in source
    assert "round(" not in source
