"""T1–T6: director is a pure function. No OBS."""

from obs_harness.director import decide

SEGMENT = {
    "layout_plan": ["wide", "split", "split", "wide", "split"],
    "center": {"kind": "card", "id": "demo-1"},
    "chyron": "A MOVE WITHOUT A THESIS",
    "spend_policy": "normal",
}

NEXT_LINE = {
    "speaker": "host_a",
    "text": "Fear has a ticker now, and it shrugs.",
}


def base_snapshot(**overrides):
    snap = {
        "t": 12.4,
        "on_air": {
            "layout": "split",
            "take": 2,
            "duration_s": 5,
            "ends_at": 15.0,
            "speaker": "host_b",
        },
        "ready": [],
        "cooking": None,
        "chain_ready": False,
        "next_line": dict(NEXT_LINE),
        "spend_usd": 0.0,
        "spend_cap_usd": 20.0,
        "holds_recent": 0,
        "flags": {"hold": False, "panic": False},
        "next_take": 4,
        "layout_i": 1,
        "segment": dict(SEGMENT),
    }
    snap.update(overrides)
    return snap


def test_t1_cooking_holds_last_host_layout():
    beat = decide(
        base_snapshot(cooking={"take": 3, "submitted_at": 10.1}, ready=[])
    )
    assert beat["layout"] == "split"
    assert beat["submit"] is None
    assert beat["host_source"] is None
    assert beat["speaking"] is None
    assert beat["center"] == SEGMENT["center"]
    assert beat["chyron"] == SEGMENT["chyron"]


def test_t1_cooking_without_a_host_picture_goes_to_card_full():
    beat = decide(
        base_snapshot(
            cooking={"take": 3, "submitted_at": 10.1},
            ready=[],
            on_air=None,
            layout=None,
        )
    )
    assert beat["layout"] == "card_full"
    assert beat["host_source"] is None


def test_t2_ready_clip_plays_and_submits_next():
    ready = [
        {
            "take": 3,
            "path": "/tmp/003.mp4",
            "speaker": "host_a",
            "line": "Then give me the timestamp.",
            "duration_s": 5.0,
        }
    ]
    beat = decide(base_snapshot(ready=ready, cooking=None, next_take=4))
    assert beat["host_source"] == "ready:3"
    assert beat["layout"] == "split"
    assert beat["speaking"] == "host_a"
    assert beat["submit"] is not None
    assert beat["submit"]["take"] == 4
    assert beat["submit"]["line"] == NEXT_LINE["text"]
    assert beat["submit"]["speaker"] == "host_a"
    assert set(beat["submit"]) == {"take", "line", "speaker"}


def test_t3_panic_hold_no_submit():
    beat = decide(
        base_snapshot(
            flags={"hold": False, "panic": True},
            ready=[{"take": 3, "path": "/tmp/003.mp4", "speaker": "host_a"}],
        )
    )
    assert beat["layout"] == "hold"
    assert beat["submit"] is None
    assert beat["host_source"] is None
    assert beat["why"] == "panic"


def test_t4_director_copies_next_line_does_not_write():
    beat = decide(
        base_snapshot(
            ready=[
                {
                    "take": 3,
                    "path": "/tmp/003.mp4",
                    "speaker": "host_b",
                    "line": "ignored",
                }
            ],
            cooking=None,
            next_line={"speaker": "host_a", "text": "EXACT COPY PLEASE"},
        )
    )
    assert beat["submit"]["line"] == "EXACT COPY PLEASE"


def test_t5_cold_start_submits_take_1():
    beat = decide(
        base_snapshot(
            t=0.0,
            on_air=None,
            ready=[],
            cooking=None,
            chain_ready=True,
            next_take=1,
            layout_i=0,
        )
    )
    assert beat["host_source"] is None
    assert beat["layout"] in ("card_full", "hold")
    assert beat["layout"] == "card_full"
    assert beat["submit"] is not None
    assert beat["submit"]["take"] == 1
    assert beat["submit"]["line"] == NEXT_LINE["text"]


def test_t6_script_ended_hold_no_submit():
    beat = decide(
        base_snapshot(
            on_air=None,
            ready=[],
            cooking=None,
            next_line=None,
            next_take=9,
        )
    )
    assert beat["layout"] == "hold"
    assert beat["submit"] is None
    assert beat["host_source"] is None
