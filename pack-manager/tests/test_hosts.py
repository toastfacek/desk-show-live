from pathlib import Path

import pytest

from pack_manager.hosts import (
    BOT1_MANIFEST,
    BOT1_NAME,
    HERO_HEIGHT,
    HERO_WIDTH,
    SCENE_MANIFEST,
    SCENE_NAME,
    lock_canonical_hosts,
)
from pack_manager.runtime import load_locked_baseline
from pack_manager.errors import ValidationError

FIXTURE_HERO = Path(__file__).resolve().parents[1] / "fixtures" / "hero_solo.png"


def test_canonical_copy_is_solo_stream_desk():
    assert SCENE_NAME == "Solo Stream Desk"
    assert "solo livestream desk" in SCENE_MANIFEST["set"]
    assert "No second host" in SCENE_MANIFEST["set"]
    assert SCENE_MANIFEST["palette"] == [
        "charcoal",
        "walnut",
        "signal orange",
        "acid lemon",
    ]
    assert BOT1_MANIFEST["visual_invariants"]["silhouette"] == (
        "Broad rounded orange software sprite."
    )
    assert BOT1_MANIFEST["voice_direction"] == (
        "Low chest voice, dry and even, then a lift when something is "
        "actually interesting. No lift at the end of a shrug."
    )
    assert "conversation teaches" in BOT1_MANIFEST["soul"]
    assert "point of view" in BOT1_MANIFEST["persona"]
    assert "voice of the audience" in BOT1_MANIFEST["persona"]
    assert "load-bearing" in BOT1_MANIFEST["persona"]
    assert "selected chat" in BOT1_MANIFEST["writer_rules"][2]
    assert "AI analyst" in BOT1_MANIFEST["persona"]
    assert "not a driver" in BOT1_MANIFEST["persona"]
    assert BOT1_MANIFEST["opinions"]
    assert "deb" not in BOT1_MANIFEST["persona"]
    assert "deb" not in SCENE_MANIFEST["set"]


def test_fixture_hero_is_flight_png():
    assert FIXTURE_HERO.is_file()
    content = FIXTURE_HERO.read_bytes()
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    import struct

    width, height = struct.unpack(">II", content[16:24])
    assert (width, height) == (HERO_WIDTH, HERO_HEIGHT)


def test_lock_canonical_hosts_exports_phaseone_only(tmp_path: Path):
    data_dir = tmp_path / "data"
    locked = lock_canonical_hosts(data_dir, FIXTURE_HERO)
    loaded = load_locked_baseline(data_dir, locked.id)
    manifest = loaded.manifest

    assert manifest["display_names"] == {"BOT1": BOT1_NAME}
    assert manifest["host_map"] == {"BOT1": "host_a"}
    assert manifest["frame"] == {"w": HERO_WIDTH, "h": HERO_HEIGHT, "fps": 24}
    assert manifest["reanchor_every"] == 5
    assert locked.hero_path.read_bytes() == FIXTURE_HERO.read_bytes()
    assert loaded.hero_path == locked.hero_path
    slots = [row["slot"] for row in manifest["packs"]["characters"]]
    assert slots == ["BOT1"]

    again = lock_canonical_hosts(data_dir, FIXTURE_HERO)
    assert again.id == locked.id


def test_lock_canonical_hosts_cli(tmp_path: Path):
    from pack_manager.hosts import main

    data_dir = tmp_path / "data"
    code = main(["--data-dir", str(data_dir), "--hero", str(FIXTURE_HERO)])
    assert code == 0
    assert any(data_dir.joinpath("exports").glob("baseline_*"))


def test_lock_canonical_hosts_rejects_missing_hero(tmp_path: Path):
    with pytest.raises(ValidationError, match="not found"):
        lock_canonical_hosts(tmp_path / "data", tmp_path / "missing.png")
