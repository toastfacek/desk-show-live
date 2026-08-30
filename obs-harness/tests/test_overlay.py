from overlay import build_state, load_posts

from loop import Harness
from tests.test_loop import _pack


def test_card_pulls_post_text():
    state = build_state(
        layout="split",
        headline="A MOVE WITHOUT A THESIS",
        speaking="host_a",
        package={"item_id": "demo-1", "center": {"kind": "card"}},
        posts={"demo-1": {"id": "demo-1", "author": "example", "text": "hello tape"}},
    )
    assert state["center"]["text"] == "hello tape"
    assert state["names"]["host_b"]["name"] == "deb"
    assert state["names"]["host_a"]["name"] == "PHASEONE[lol]"


def test_loop_writes_overlay_state(tmp_path):
    h = Harness.from_rundown(
        _pack(tmp_path),
        stub={"delay_s": 0.0, "delay_jitter_s": 0.0, "forced_late_takes": []},
        clip_duration_s=5.0,
    )
    h.step()
    path = tmp_path / "out" / "overlay_state.json"
    assert path.exists()
    text = path.read_text()
    assert "HEAD" in text
    assert "PHASEONE[lol]" in text
    assert "card_full" in text or "wide" in text or "split" in text or "hold" in text


def test_load_posts(tmp_path):
    p = tmp_path / "posts.json"
    p.write_text('{"posts": [{"id": "demo-1", "author": "x", "text": "hi"}]}')
    assert load_posts(p)["demo-1"]["text"] == "hi"