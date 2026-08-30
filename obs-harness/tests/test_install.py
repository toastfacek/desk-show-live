from scenes.install import pick_kind, scene_names


class _Bag:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_pick_kind_prefers_available():
    assert pick_kind({"text_ft2_source", "other"}, ("text_gdiplus_v2", "text_ft2_source")) == "text_ft2_source"
    assert pick_kind(set(), ("color_source_v3", "color_source")) == "color_source_v3"


def test_scene_names_reads_dicts():
    client = _Bag(get_scene_list=lambda: _Bag(scenes=[{"sceneName": "wide"}, {"sceneName": "hold"}]))
    assert scene_names(client) == {"wide", "hold"}
