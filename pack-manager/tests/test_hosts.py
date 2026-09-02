from pathlib import Path

import pytest

from pack_manager.hosts import (
    BOT1_MANIFEST,
    BOT1_NAME,
    BOT2_MANIFEST,
    BOT2_NAME,
    HERO_HEIGHT,
    HERO_WIDTH,
    SCENE_MANIFEST,
    SCENE_NAME,
    lock_canonical_hosts,
)
from pack_manager.runtime import load_locked_baseline
from pack_manager.errors import ValidationError

FIXTURE_HERO = Path(__file__).resolve().parents[1] / "fixtures" / "hero_wide.png"


def test_canonical_copy_is_light_broadcast_sprites():
    assert SCENE_NAME == "Light Media Club"
    assert "live media clubhouse" in SCENE_MANIFEST["set"]
    assert "pill-shaped desk" in SCENE_MANIFEST["set"]
    assert SCENE_MANIFEST["palette"] == [
        "warm white",
        "forest green",
        "cobalt",
        "signal orange",
    ]
    assert BOT1_MANIFEST["visual_invariants"]["silhouette"] == (
        "Broad rounded orange software sprite."
    )
    assert BOT2_MANIFEST["visual_invariants"]["silhouette"] == (
        "Tall cobalt software sprite."
    )
    assert BOT1_MANIFEST["voice_direction"] == (
        "Low chest voice, dry and even, then a lift when something is "
        "actually interesting. No lift at the end of a shrug."
    )
    assert BOT2_MANIFEST["voice_direction"] == (
        "Higher thinner voice, quick and clipped, bright, slightly nasal, "
        "restless upward energy. Gets into it when something is good."
    )
    assert "conversation teaches" in BOT1_MANIFEST["soul"]
    assert "learn in public" in BOT2_MANIFEST["soul"]
    assert "point of view" in BOT1_MANIFEST["persona"]
    assert "voice of the audience" in BOT1_MANIFEST["persona"]
    assert "have a take" in BOT2_MANIFEST["persona"]
    assert "does to people" in BOT1_MANIFEST["persona"]
    assert "AI analyst" in BOT1_MANIFEST["persona"]
    assert "not a driver" in BOT1_MANIFEST["persona"]
    assert "Yes-and" in BOT2_MANIFEST["persona"]
    assert "missing screenshot is a caveat" in BOT2_MANIFEST["opinions"][1]
    assert BOT1_MANIFEST["opinions"]
    assert BOT2_MANIFEST["opinions"]


def test_fixture_hero_is_flight_png():
    assert FIXTURE_HERO.is_file()
    content = FIXTURE_HERO.read_bytes()
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    import struct

    width, height = struct.unpack(">II", content[16:24])
    assert (width, height) == (HERO_WIDTH, HERO_HEIGHT)


def test_lock_canonical_hosts_exports_phaseone_and_deb(tmp_path: Path):
    data_dir = tmp_path / "data"
    locked = lock_canonical_hosts(data_dir, FIXTURE_HERO)
    loaded = load_locked_baseline(data_dir, locked.id)
    manifest = loaded.manifest

    assert manifest["display_names"] == {"BOT1": BOT1_NAME, "BOT2": BOT2_NAME}
    assert manifest["host_map"] == {"BOT1": "host_a", "BOT2": "host_b"}
    assert manifest["frame"] == {"w": HERO_WIDTH, "h": HERO_HEIGHT, "fps": 24}
    assert manifest["reanchor_every"] == 5
    assert locked.hero_path.read_bytes() == FIXTURE_HERO.read_bytes()
    assert loaded.hero_path == locked.hero_path

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
