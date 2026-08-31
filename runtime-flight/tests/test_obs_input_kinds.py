"""Input kind normalization and setup rejection tests."""

from __future__ import annotations

import pytest

from runtime_flight.obs_setup import (
    normalize_input_kind,
    resolve_role_kinds,
    role_kind_compatible,
    setup_obs,
    validate_contract,
)
from conftest_obs import FakeObsClient, complete_obs_client


def test_normalize_input_kind_strips_trailing_version_suffix():
    assert normalize_input_kind("text_gdiplus_v2") == "text_gdiplus"
    assert normalize_input_kind("color_source_v3") == "color_source"
    assert normalize_input_kind("ffmpeg_source") == "ffmpeg_source"


def test_role_kind_compatible_accepts_normalized_versioned_kind():
    assert role_kind_compatible("text", "text_gdiplus_v2")
    assert role_kind_compatible("color", "color_source_v3")


def test_validate_contract_accepts_versioned_existing_kinds():
    client = complete_obs_client()
    client.inputs["HEADLINE"] = "text_gdiplus_v2"
    client.inputs["HL_A"] = "color_source_v3"
    assert validate_contract(client) == []


def test_resolve_role_kinds_uses_exact_unversioned_candidates():
    kinds = resolve_role_kinds(
        {
            "ffmpeg_source",
            "text_gdiplus",
            "color_source",
            "image_source",
            "browser_source",
        }
    )
    assert kinds == {
        "media": "ffmpeg_source",
        "text": "text_gdiplus",
        "color": "color_source",
        "image": "image_source",
        "browser": "browser_source",
    }


def test_resolve_role_kinds_prefers_versioned_create_kind():
    kinds = resolve_role_kinds(
        {
            "ffmpeg_source",
            "text_ft2_source",
            "text_ft2_source_v2",
            "color_source",
            "color_source_v3",
            "image_source",
            "browser_source",
        }
    )
    assert kinds["text"] == "text_ft2_source_v2"
    assert kinds["color"] == "color_source_v3"
    assert kinds["media"] == "ffmpeg_source"


def test_setup_obs_queries_versioned_and_unversioned_input_kind_lists():
    client = FakeObsClient()
    setup_obs(client)
    assert ("get_input_kind_list", False) in client.calls
    assert ("get_input_kind_list", True) in client.calls


def test_setup_obs_rejects_incompatible_existing_kind_before_creating():
    client = complete_obs_client()
    client.inputs["HEADLINE"] = "browser_source"
    with pytest.raises(RuntimeError, match="incompatible"):
        setup_obs(client)
    assert not any(call[0] == "create_scene" for call in client.calls)
    assert not any(call[0] == "create_input" for call in client.calls)
