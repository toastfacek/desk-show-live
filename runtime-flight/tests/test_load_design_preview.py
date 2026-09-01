"""Preview loader keeps PR #26 wash off the scene contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from runtime_flight.obs_setup import REQUIRED_INPUTS, REQUIRED_SCENES, validate_contract
from conftest_obs import complete_obs_client

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "load-design-preview.py"
SPEC = importlib.util.spec_from_file_location("load_design_preview", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
load_design_preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(load_design_preview)


def test_wash_is_not_a_contract_input() -> None:
    assert load_design_preview.WASH_SOURCE == "WASH"
    assert load_design_preview.WASH_SOURCE not in REQUIRED_INPUTS


def test_on_air_url_freezes_the_wash() -> None:
    assert load_design_preview.wash_url(8766) == (
        "http://127.0.0.1:8766/dither-wash.html?static=1"
    )
    assert "static=0" in load_design_preview.wash_url(8766, static=False)


def test_browser_settings_are_full_canvas_silent() -> None:
    settings = load_design_preview.wash_browser_settings(
        "http://127.0.0.1:8766/dither-wash.html?static=1"
    )
    assert settings["width"] == 1920
    assert settings["height"] == 1080
    assert settings["reroute_audio"] is False
    assert settings["url"].endswith("static=1")


def test_apply_wash_refuses_streaming_before_any_mutation() -> None:
    class StreamingClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_stream_status(self):
            self.calls.append("get_stream_status")
            return type("StreamStatus", (), {"output_active": True})()

    client = StreamingClient()
    with pytest.raises(RuntimeError, match="already streaming"):
        load_design_preview.apply_wash(
            client, url="http://127.0.0.1:8766/dither-wash.html?static=1"
        )
    assert client.calls == ["get_stream_status"]


def test_apply_wash_sits_under_the_desk_and_leaves_the_contract() -> None:
    client = complete_obs_client()
    url = "http://127.0.0.1:8766/dither-wash.html?static=1"
    summary = load_design_preview.apply_wash(client, url=url)

    assert summary["source"] == "WASH"
    assert summary["created_input"] is True
    assert summary["z_index"] == 0
    assert summary["contract_input"] is False
    assert set(summary["created_scene_items"]) == set(REQUIRED_SCENES) - {"wide"}

    create = [
        call
        for call in client.calls
        if call[0] == "create_input" and call[2] == "WASH"
    ]
    assert create[0][3] == "browser_source"
    assert create[0][4]["url"] == url

    indexes = [
        call
        for call in client.calls
        if call[0] == "set_scene_item_index"
    ]
    assert {call[1] for call in indexes} == set(REQUIRED_SCENES)
    assert all(call[3] == 0 for call in indexes)

    assert validate_contract(client) == []
