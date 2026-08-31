"""Task 4: ObsPlayer speaking highlights and scene-item cache."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from obs_harness.player_obs import HOST_LAYOUTS, LAYOUTS, ObsPlayer


@dataclass
class FakeSceneItem:
    source_name: str
    scene_item_id: int
    scene_item_enabled: bool = True


@dataclass
class FakeObsClient:
  calls: list[tuple] = field(default_factory=list)
  scene_items: dict[str, list[FakeSceneItem]] = field(default_factory=dict)

  def get_scene_item_list(self, name: str):
      self.calls.append(("get_scene_item_list", name))
      items = self.scene_items.get(name, [])
      return type("SceneItemList", (), {"scene_items": items})()

  def set_scene_item_enabled(self, scene_name: str, item_id: int, enabled: bool):
      self.calls.append(("set_scene_item_enabled", scene_name, item_id, enabled))

  def set_input_mute(self, name: str, muted: bool):
      self.calls.append(("set_input_mute", name, muted))


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


def test_reconnect_refreshes_scene_item_cache():
    client = FakeObsClient(scene_items=_scene_items_for_layouts())
    player = ObsPlayer()
    player._client = client
    player._refresh_scene_item_cache()
    assert player._scene_item_ids["wide"]["HL_A"] == client.scene_items["wide"][0].scene_item_id

    client.scene_items["wide"][0].scene_item_id = 99
    player.connect = lambda: player._refresh_scene_item_cache()
    player.reconnect()

    assert player._scene_item_ids["wide"]["HL_A"] == 99
