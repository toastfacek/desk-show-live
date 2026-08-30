from player_obs import LAYOUTS, ObsPlayer


class _Bag:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeReq:
    def __init__(self):
        self.calls = []
        self.scenes = [{"sceneName": name} for name in LAYOUTS]

    def get_scene_list(self):
        return _Bag(scenes=self.scenes)

    def set_current_program_scene(self, name):
        self.calls.append(("layout", name))

    def set_input_settings(self, name, settings, overlay=True):
        self.calls.append(("settings", name, settings))

    def trigger_media_input_action(self, name, action):
        self.calls.append(("restart", name, action))

    def get_scene_item_list(self, name):
        return _Bag(scene_items=[])

    def set_scene_item_enabled(self, scene_name, item_id, enabled):
        self.calls.append(("enabled", scene_name, item_id, enabled))

    def set_input_volume(self, name, vol_mul):
        self.calls.append(("vol", name, vol_mul))


def test_set_layout_switches_program_scene():
    player = ObsPlayer()
    player._client = FakeReq()
    player.set_layout("split")
    assert player.layout == "split"
    assert ("layout", "split") in player._client.calls


def test_play_clip_sets_host_wide_and_restarts():
    player = ObsPlayer()
    player._client = FakeReq()
    player.play_clip("/tmp/002.mp4")
    kinds = [row[0] for row in player._client.calls]
    assert "settings" in kinds
    assert "restart" in kinds
    settings = next(row for row in player._client.calls if row[0] == "settings")
    assert settings[1] == "HOST_WIDE"
    assert settings[2]["local_file"].endswith("002.mp4")


def test_missing_layouts_empty_when_all_present():
    player = ObsPlayer()
    player._client = FakeReq()
    assert player.missing_layouts() == []


def test_missing_layouts_lists_absent():
    player = ObsPlayer()
    req = FakeReq()
    req.scenes = [{"sceneName": "wide"}]
    player._client = req
    assert player.missing_layouts() == ["split", "solo_l", "solo_r", "card_full", "hold"]
