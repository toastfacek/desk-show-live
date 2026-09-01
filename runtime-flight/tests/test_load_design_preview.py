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


def test_wash_url_drifts_by_default_and_can_freeze() -> None:
    assert load_design_preview.wash_url(8766) == (
        "http://127.0.0.1:8766/dither-wash.html?static=0&speed=1"
    )
    assert load_design_preview.wash_url(8766, speed=2.5).endswith(
        "static=0&speed=2.5"
    )
    frozen = load_design_preview.wash_url(8766, static=True)
    assert frozen.endswith("static=1")
    assert "speed=" not in frozen


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


def test_overlay_live_is_transparent_1080_cg_not_the_review_page() -> None:
    html = Path(__file__).resolve().parents[2] / "scripts" / "design-preview" / "overlay-live.html"
    text = html.read_text(encoding="utf-8")
    assert "1920px" in text
    assert "1080px" in text
    assert "background:transparent" in text
    assert "PHASEONE[lol]" in text
    assert ">deb<" in text
    assert "RUNTIME" in text
    assert "Runtime mark" in text
    assert "thesis" not in text.lower()
    assert "the number" not in text.lower()
    assert "overlay-live.js" in text
    assert 'class="set"' not in text
    assert "The overlay stops performing" not in text


def test_overlay_live_url_selects_speaker() -> None:
    assert load_design_preview.overlay_live_url(8766) == (
        "http://127.0.0.1:8766/overlay-live.html?speaker=a"
    )
    assert "speaker=b" in load_design_preview.overlay_live_url(8766, speaker="b")
    live = load_design_preview.overlay_live_url(
        8766, card_origin="http://127.0.0.1:8765"
    )
    assert "card_origin=http://127.0.0.1:8765" in live


def test_overlay_live_polls_card_without_html_injection() -> None:
    html = Path(__file__).resolve().parents[2] / "scripts" / "design-preview" / "overlay-live.html"
    js = Path(__file__).resolve().parents[2] / "scripts" / "design-preview" / "overlay-live.js"
    text = html.read_text(encoding="utf-8")
    script = js.read_text(encoding="utf-8")
    assert 'id="card-author"' in text
    assert 'id="card-body"' in text
    assert 'id="card-image"' in text
    assert 'id="tweet-embed"' in text
    assert 'id="chyron"' in text
    assert "overlay-live.js" in text
    assert "innerHTML" not in text
    assert "innerHTML" not in script
    assert "textContent" in script
    assert "tweet-embed.html?id=" in script
    embed = (
        Path(__file__).resolve().parents[2] / "scripts" / "design-preview" / "tweet-embed.html"
    ).read_text(encoding="utf-8")
    assert "platform.twitter.com/embed/Tweet.html" in embed
    assert "innerHTML" not in embed


def test_apply_preview_points_watchdog_at_identity_and_hides_obs_type() -> None:
    client = complete_obs_client()
    summary = load_design_preview.apply_preview(
        client,
        wash="http://127.0.0.1:8766/dither-wash.html?static=1",
        overlay="http://127.0.0.1:8766/overlay-live.html?speaker=a",
    )
    watchdog = [
        call
        for call in client.calls
        if call[0] == "set_input_settings" and call[1] == "WATCHDOG"
    ]
    assert watchdog[-1][2]["url"].endswith("overlay-live.html?speaker=a")
    hidden = set(summary["hidden_furniture"])
    assert "split:NAME_A" in hidden
    assert "split:HEADLINE" in hidden
    assert "split:CENTER" in hidden
    assert summary["wells"]["wells"]["left"]["x"] == 64
    assert summary["transition"] == "Cut"
    crops = summary["wells"]["crops"]
    assert crops["left"]["crop_right"] > load_design_preview.HALF_W
    assert crops["right"]["crop_left"] > load_design_preview.HALF_W
    assert crops["left"]["crop_top"] == load_design_preview.CROP_TOP
    host_settings = [
        call
        for call in client.calls
        if call[0] == "set_input_settings" and call[1] == "HOST_WIDE"
    ]
    assert host_settings[-1][2]["looping"] is False
    assert host_settings[-1][2]["restart_on_activate"] is False
    assert any(
        call[0] == "set_current_scene_transition" and call[1] == "Cut"
        for call in client.calls
    )
    assert validate_contract(client) == []


def test_host_crops_center_sprites_inside_each_well() -> None:
    left = load_design_preview.host_crop(load_design_preview.HOST_L_X)
    right = load_design_preview.host_crop(load_design_preview.HOST_R_X)
    left_w = (
        load_design_preview.SOURCE_W - left["crop_left"] - left["crop_right"]
    )
    right_w = (
        load_design_preview.SOURCE_W - right["crop_left"] - right["crop_right"]
    )
    assert left_w == load_design_preview.CROP_W
    assert right_w == load_design_preview.CROP_W
    assert left["crop_left"] == 0
    assert 230 < load_design_preview.HOST_L_X < left_w
    visible_right = load_design_preview.HOST_R_X - right["crop_left"]
    assert abs(visible_right - load_design_preview.CROP_W / 2) <= 2
    transform = load_design_preview._bounds(
        64, 140, 580, 660, **left
    )
    assert transform["boundsAlignment"] == load_design_preview.ALIGN_CENTER
    assert transform["cropLeft"] == left["crop_left"]
    assert transform["cropRight"] == left["crop_right"]
