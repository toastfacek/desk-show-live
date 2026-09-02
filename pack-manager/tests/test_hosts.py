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
    is_show_loadout,
    loadout_hero_sha256,
    lock_canonical_hosts,
    require_show_loadout,
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


def test_show_loadout_matches_canonical_copy_and_fixture_hero():
    assert is_show_loadout(
        hero_sha256=loadout_hero_sha256(),
        display_names={"BOT1": BOT1_NAME, "BOT2": BOT2_NAME},
        bot1_visual=BOT1_MANIFEST["visual_invariants"],
        bot2_visual=BOT2_MANIFEST["visual_invariants"],
        scene=SCENE_MANIFEST,
    )
    with pytest.raises(ValidationError, match="single Light Media Club loadout"):
        require_show_loadout(
            hero_sha256=loadout_hero_sha256(),
            display_names={"BOT1": BOT1_NAME, "BOT2": BOT2_NAME},
            bot1_visual={
                **BOT1_MANIFEST["visual_invariants"],
                "silhouette": (
                    "Low wide rounded-box head, broad sloping shoulders, "
                    "bottom-heavy charcoal torso."
                ),
            },
            bot2_visual=BOT2_MANIFEST["visual_invariants"],
            scene=SCENE_MANIFEST,
        )


def test_lock_canonical_hosts_ignores_non_loadout_latest(tmp_path: Path):
    from pack_manager.assets import AssetStore
    from pack_manager.baselines import BaselineService
    from pack_manager.candidates import CandidateService
    from pack_manager.db import Database
    from pack_manager.packs import PackService

    from conftest import character_manifest_v2, scene_manifest_v2

    data_dir = tmp_path / "data"
    database = Database(data_dir / "manager.sqlite3")
    database.initialize()
    assets = AssetStore(data_dir, database)
    packs = PackService(database, assets)
    candidates = CandidateService(database, assets, packs)
    baselines = BaselineService(database, assets, packs, candidates)
    decoy = assets.put_bytes("decoy.png", FIXTURE_HERO.read_bytes(), "image/png")
    bot1 = packs.create_pack("character", "BOT1")
    bot2 = packs.create_pack("character", "BOT2")
    scene = packs.create_pack("scene", "Studio")
    bot1_version = packs.create_version(
        bot1.id, character_manifest_v2([decoy.id])
    )
    bot2_version = packs.create_version(
        bot2.id, character_manifest_v2([decoy.id])
    )
    scene_version = packs.create_version(scene.id, scene_manifest_v2([decoy.id]))
    candidate = candidates.create(
        character_versions={
            "BOT1": (bot1_version.pack_id, bot1_version.version),
            "BOT2": (bot2_version.pack_id, bot2_version.version),
        },
        scene_pack_id=scene_version.pack_id,
        scene_version=scene_version.version,
        hero_asset_id=decoy.id,
    )
    approved = candidates.approve(candidate.id, canonical=True, review_note="decoy")
    other = baselines.lock_run(approved.cast_key)

    locked = lock_canonical_hosts(data_dir, FIXTURE_HERO)
    assert locked.id != other.id
    loaded = load_locked_baseline(data_dir, locked.id)
    assert loaded.manifest["display_names"] == {"BOT1": BOT1_NAME, "BOT2": BOT2_NAME}


def test_lock_canonical_hosts_rejects_non_fixture_hero(tmp_path: Path):
    from PIL import Image
    import io

    other = tmp_path / "other.png"
    image = Image.new("RGB", (HERO_WIDTH, HERO_HEIGHT), (10, 20, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    other.write_bytes(buffer.getvalue())

    with pytest.raises(ValidationError, match="fixture"):
        lock_canonical_hosts(tmp_path / "data", other)
