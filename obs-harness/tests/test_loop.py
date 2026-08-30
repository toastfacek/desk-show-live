"""T7–T10: short loop against FakePlayer + stub. No OBS."""

from pathlib import Path

from loop import Harness


def _pack(tmp_path: Path, n_lines: int = 8) -> Path:
    clips = tmp_path / "clips"
    clips.mkdir()
    for i in range(3):
        (clips / f"c{i}.mp4").write_bytes(b"fake")
    script = tmp_path / "script.jsonl"
    lines = [
        '{"speaker": "host_a", "text": "Line %d.", "thought_open": false}\n' % i
        for i in range(1, n_lines + 1)
    ]
    script.write_text("".join(lines))
    posts = tmp_path / "posts.json"
    posts.write_text('{"posts": [{"id": "demo-1", "author": "x", "text": "hi"}]}')
    rundown = tmp_path / "rundown.yaml"
    rundown.write_text(
        "\n".join(
            [
                "show: {name: demo, target_len_s: 90, mode: rehearse}",
                f"script_file: {script}",
                f"posts_file: {posts}",
                f"clip_pool: {clips}",
                "segments:",
                "  - id: demo_1",
                "    kind: talk",
                "    target_len_s: 90",
                "    layout_plan: [wide, split, split, wide, split]",
                "    package:",
                "      item_id: demo-1",
                "      chyron: HEAD",
                "      center: {kind: card, id: demo-1}",
                "      spend_policy: normal",
            ]
        )
    )
    return rundown


def test_t7_three_takes_no_hold(tmp_path):
    h = Harness.from_rundown(
        _pack(tmp_path),
        stub={"delay_s": 4.0, "delay_jitter_s": 0.0, "forced_late_takes": []},
        clip_duration_s=5.0,
    )
    h.run_simulated(until_takes_on_air=3)
    statuses = [row["status"] for row in h.log]
    assert "held" not in statuses
    aired = [row for row in h.log if row.get("t_on_air") is not None]
    assert len(aired) >= 3


def test_t8_forced_late_take_3_then_airs(tmp_path):
    h = Harness.from_rundown(
        _pack(tmp_path),
        stub={
            "delay_s": 4.0,
            "delay_jitter_s": 0.0,
            "forced_late_takes": [3],
            "forced_late_delay_s": 8.0,
        },
        clip_duration_s=5.0,
    )
    h.run_simulated(until_takes_on_air=3)
    layouts = [b["layout"] for b in h.beats]
    assert any(layout in ("card_full", "hold") for layout in layouts)
    take3 = next(row for row in h.log if row["take"] == 3)
    assert take3.get("t_on_air") is not None
    assert take3.get("forced_late") is True


def test_t9_script_slot_stays_at_two(tmp_path):
    h = Harness.from_rundown(
        _pack(tmp_path, n_lines=10),
        stub={"delay_s": 4.0, "delay_jitter_s": 0.0, "forced_late_takes": []},
        clip_duration_s=5.0,
    )
    depths = []

    def after_step():
        depths.append(len(h.written_ahead))

    h.after_step = after_step
    h.run_simulated(until_takes_on_air=3)
    # Until the file is nearly empty, depth is 2 after every refill.
    assert all(d <= 2 for d in depths)
    assert 2 in depths


def test_t10_director_does_not_import_player_obs():
    text = Path(__file__).resolve().parents[1].joinpath("director.py").read_text()
    assert "player_obs" not in text
