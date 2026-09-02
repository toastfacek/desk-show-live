"""Spend / text / pending runway. No network."""

from decimal import Decimal

import pytest

from runtime_flight.runway import UntilError, has_runway, resolve_until


def test_has_runway_when_spend_text_and_tweets_remain() -> None:
    assert has_runway(
        reserved_usd=Decimal("0.10"),
        cap_usd=Decimal("8.00"),
        take_cost_usd=Decimal("0.05"),
        text_left=4,
        pending=3,
    )


def test_out_of_runway_when_next_take_exceeds_cap() -> None:
    assert not has_runway(
        reserved_usd=Decimal("8.00"),
        cap_usd=Decimal("8.00"),
        take_cost_usd=Decimal("0.05"),
        text_left=4,
        pending=3,
    )


def test_out_of_runway_when_text_is_gone() -> None:
    assert not has_runway(
        reserved_usd=Decimal("0"),
        cap_usd=Decimal("8.00"),
        take_cost_usd=Decimal("0.05"),
        text_left=0,
        pending=3,
    )


def test_empty_list_is_not_runway() -> None:
    assert not has_runway(
        reserved_usd=Decimal("0"),
        cap_usd=Decimal("8.00"),
        take_cost_usd=Decimal("0.05"),
        text_left=4,
        pending=0,
    )


def test_until_is_optional_iso() -> None:
    assert resolve_until(None) is None
    parsed = resolve_until("2026-09-06T12:00:00Z")
    assert parsed is not None
    with pytest.raises(UntilError):
        resolve_until("sunday")
