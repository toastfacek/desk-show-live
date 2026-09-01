"""Task 4: ObsPlayer speaking highlights and scene-item cache."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from obs_harness.player_obs import HOST_LAYOUTS, LAYOUTS, ObsPlayer, prepare_obs_clip


@dataclass
class FakeSceneItem:
    source_name: str
    scene_item_id: int
    scene_item_enabled: bool = True


@dataclass
class FakeObsClient:
    calls: list[tuple] = field(default_factory=list)
    scene_items: dict[str, list[FakeSceneItem]] = field(default_factory=dict)
    program_scene: str = "split"
    media_duration: int | None = 5000
    media_cursor: int | None = 0
    media_state: str = "OBS_MEDIA_STATE_PLAYING"
    media_error: Exception | None = None

    def get_scene_item_list(self, name: str):
        self.calls.append(("get_scene_item_list", name))
        items = self.scene_items.get(name, [])
        return type("SceneItemList", (), {"scene_items": items})()

    def set_scene_item_enabled(self, scene_name: str, item_id: int, enabled: bool):
        self.calls.append(("set_scene_item_enabled", scene_name, item_id, enabled))

    def set_input_settings(self, name: str, settings: dict, overlay: bool):
        self.calls.append(("set_input_settings", name, settings, overlay))

    def set_input_mute(self, name: str, muted: bool):
        self.calls.append(("set_input_mute", name, muted))

    def trigger_media_input_action(self, name: str, action: str):
        self.calls.append(("trigger_media_input_action", name, action))

    def get_current_program_scene(self):
        self.calls.append(("get_current_program_scene",))
        return type(
            "ProgramScene",
            (),
            {"current_program_scene_name": self.program_scene},
        )()

    def get_media_input_status(self, name: str):
        self.calls.append(("get_media_input_status", name))
        if self.media_error is not None:
            raise self.media_error
        return type(
            "MediaStatus",
            (),
            {
                "media_duration": self.media_duration,
                "media_cursor": self.media_cursor,
                "media_state": self.media_state,
            },
        )()


class ReconnectObsPlayer(ObsPlayer):
    def __init__(self, clients: list[FakeObsClient]) -> None:
        super().__init__()
        self._clients = list(clients)

    def connect(self) -> None:
        if not self._clients:
            raise RuntimeError("no clients left to connect")
        self._client = self._clients.pop(0)
        self._refresh_scene_item_cache()


def _player_with_client(client: FakeObsClient) -> ObsPlayer:
    player = ObsPlayer()
    player._client = client
    return player


def _scene_items_for_layouts() -> dict[str, list[FakeSceneItem]]:
    items: dict[str, list[FakeSceneItem]] = {}
    item_id = 1
    for scene in LAYOUTS:
        items[scene] = [
            FakeSceneItem("HL_A", item_id),
            FakeSceneItem("HL_B", item_id + 1),
        ]
        item_id += 2
    return items


@pytest.mark.parametrize("scene", HOST_LAYOUTS)
def test_set_speaking_enables_highlight_by_scene_item_id_host_a(scene):
    client = FakeObsClient(scene_items=_scene_items_for_layouts())
    player = _player_with_client(client)
    player._refresh_scene_item_cache()

    player.set_speaking("host_a")

    hl_a_id = client.scene_items[scene][0].scene_item_id
    hl_b_id = client.scene_items[scene][1].scene_item_id
    assert ("set_scene_item_enabled", scene, hl_a_id, True) in client.calls
    assert ("set_scene_item_enabled", scene, hl_b_id, False) in client.calls


@pytest.mark.parametrize("scene", HOST_LAYOUTS)
def test_set_speaking_enables_highlight_by_scene_item_id_host_b(scene):
    client = FakeObsClient(scene_items=_scene_items_for_layouts())
    player = _player_with_client(client)
    player._refresh_scene_item_cache()

    player.set_speaking("host_b")

    hl_a_id = client.scene_items[scene][0].scene_item_id
    hl_b_id = client.scene_items[scene][1].scene_item_id
    assert ("set_scene_item_enabled", scene, hl_a_id, False) in client.calls
    assert ("set_scene_item_enabled", scene, hl_b_id, True) in client.calls


@pytest.mark.parametrize("scene", HOST_LAYOUTS)
def test_set_speaking_null_disables_both_highlights(scene):
    client = FakeObsClient(scene_items=_scene_items_for_layouts())
    player = _player_with_client(client)
    player._refresh_scene_item_cache()
    client.calls.clear()

    player.set_speaking(None)

    hl_a_id = client.scene_items[scene][0].scene_item_id
    hl_b_id = client.scene_items[scene][1].scene_item_id
    assert ("set_scene_item_enabled", scene, hl_a_id, False) in client.calls
    assert ("set_scene_item_enabled", scene, hl_b_id, False) in client.calls


def test_set_speaking_does_not_mute_audio_inputs():
    client = FakeObsClient(scene_items=_scene_items_for_layouts())
    player = _player_with_client(client)
    player._refresh_scene_item_cache()

    player.set_speaking("host_a")

    mute_calls = [call for call in client.calls if call[0] == "set_input_mute"]
    assert mute_calls == []


def test_reconnect_refreshes_scene_item_cache_with_replacement_client():
    client1 = FakeObsClient(scene_items=_scene_items_for_layouts())
    client2 = FakeObsClient(scene_items=_scene_items_for_layouts())
    client2.scene_items["wide"][0].scene_item_id = 99

    player = ReconnectObsPlayer([client1, client2])
    player.connect()
    assert player._scene_item_ids["wide"]["HL_A"] == client1.scene_items["wide"][0].scene_item_id

    player.reconnect(deadline_s=1.0)

    assert player._client is client2
    assert player._scene_item_ids["wide"]["HL_A"] == 99


def test_get_program_state_idle_media_is_still_connected():
    client = FakeObsClient(
        program_scene="card_full",
        media_duration=None,
        media_cursor=None,
        media_state="OBS_MEDIA_STATE_ENDED",
    )
    player = _player_with_client(client)
    player.t = 12.0

    state = player.get_program_state()

    assert state["connected"] is True
    assert state["media_ok"] is True
    assert state["layout"] == "card_full"
    assert state["on_air"]["kind"] == "card"
    assert state["on_air"]["ends_at"] == 12.0
    assert state["on_air"]["media_ok"] is True


def test_get_program_state_missing_source_is_not_ok():
    client = FakeObsClient(media_error=RuntimeError("no such input"))
    player = _player_with_client(client)

    state = player.get_program_state()

    assert state["connected"] is True
    assert state["media_ok"] is False
    assert state["on_air"]["media_ok"] is False


def _tiny_clip(path: Path) -> Path:
    import subprocess

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=64x48:d=0.2:r=24",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=32000:cl=stereo",
            "-shortest",
            "-c:v",
            "libx264",
            "-profile:v",
            "baseline",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def test_prepare_obs_clip_writes_high_profile_sibling(tmp_path: Path):
    src = _tiny_clip(tmp_path / "001.mp4")
    dest = prepare_obs_clip(src)
    assert dest != src
    assert dest.name == "001.obs.mp4"
    assert dest.is_file()
    again = prepare_obs_clip(src)
    assert again == dest


def test_play_clip_points_host_wide_at_obs_playable(tmp_path: Path):
    src = _tiny_clip(tmp_path / "003.mp4")
    client = FakeObsClient()
    player = _player_with_client(client)
    player.play_clip(str(src))
    settings = [
        call for call in client.calls if call[0] == "set_input_settings"
    ]
    assert settings[-1][1] == "HOST_WIDE"
    assert settings[-1][2]["local_file"].endswith("003.obs.mp4")
    assert settings[-1][2]["looping"] is False
    assert settings[-1][2]["clear_on_media_end"] is False
    mute = [call for call in client.calls if call[0] == "set_input_mute"]
    assert mute[-1][1] == "HOST_WIDE"
    assert mute[-1][2] is False
