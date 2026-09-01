"""Pure checks for the OBS layout script's safety and geometry constants."""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "apply-obs-layout.py"
SPEC = importlib.util.spec_from_file_location("apply_obs_layout", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
apply_obs_layout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apply_obs_layout)


def test_layout_uses_fixed_solo_aperture_and_distinct_host_colors() -> None:
    assert apply_obs_layout.WELLS["solo"] == {
        "x": 80,
        "y": 80,
        "w": 620,
        "h": 700,
    }
    assert (
        apply_obs_layout.HIGHLIGHT_COLORS["HL_A"]
        != apply_obs_layout.HIGHLIGHT_COLORS["HL_B"]
    )
    assert apply_obs_layout.DEFAULT_CLIP == (
        apply_obs_layout.REPO_ROOT / "assets" / "clips" / "sync_check.mp4"
    )


def test_host_wide_playback_does_not_loop() -> None:
    source = inspect.getsource(apply_obs_layout.apply_layout)
    assert '"looping": False' in source
    assert '"restart_on_activate": False' in source
    assert 'set_current_scene_transition("Cut")' in source
    assert "set_current_scene_transition_duration" not in source


def test_apply_layout_refuses_streaming_before_any_mutation() -> None:
    class StreamingClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_stream_status(self):
            self.calls.append("get_stream_status")
            return type("StreamStatus", (), {"output_active": True})()

    client = StreamingClient()
    with pytest.raises(RuntimeError, match="already streaming"):
        apply_obs_layout.apply_layout(
            client,
            clip=Path("clip.mp4"),
            watchdog_url="http://127.0.0.1:8765/",
        )

    assert client.calls == ["get_stream_status"]
