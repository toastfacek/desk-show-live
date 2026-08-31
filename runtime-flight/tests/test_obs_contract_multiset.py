"""Multiset scene-item contract tests independent of production constants."""

from __future__ import annotations

from runtime_flight.obs_setup import SceneItemRequirement, scene_item_multiset_errors


ALPHA_REQUIREMENTS = (
    SceneItemRequirement("HOST_WIDE", minimum=2, maximum=2, distinct_ids=True),
    SceneItemRequirement("LOGO", minimum=1),
)


def test_multiset_rejects_missing_host_wide():
    errors = scene_item_multiset_errors(
        "alpha",
        [("LOGO", 10)],
        ALPHA_REQUIREMENTS,
    )
    assert any("HOST_WIDE" in error and "alpha" in error for error in errors)


def test_multiset_rejects_one_host_wide():
    errors = scene_item_multiset_errors(
        "alpha",
        [("HOST_WIDE", 1), ("LOGO", 2)],
        ALPHA_REQUIREMENTS,
    )
    assert any("HOST_WIDE" in error and "2" in error for error in errors)


def test_multiset_rejects_duplicate_host_wide_ids():
    errors = scene_item_multiset_errors(
        "alpha",
        [("HOST_WIDE", 7), ("HOST_WIDE", 7), ("LOGO", 2)],
        ALPHA_REQUIREMENTS,
    )
    assert any("distinct" in error.lower() for error in errors)


def test_multiset_accepts_two_distinct_host_wide():
    errors = scene_item_multiset_errors(
        "alpha",
        [("HOST_WIDE", 1), ("HOST_WIDE", 2), ("LOGO", 3)],
        ALPHA_REQUIREMENTS,
    )
    assert errors == []
