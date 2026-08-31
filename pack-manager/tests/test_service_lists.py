from pack_manager.assets import AssetStore
from pack_manager.baselines import BaselineService
from pack_manager.candidates import CandidateService
from pack_manager.db import Database
from pack_manager.packs import PackService


from conftest import character_manifest_v2, scene_manifest_v2


PNG = b"\x89PNG\r\n\x1a\nlist-test"


def test_services_expose_public_ordered_list_interfaces(tmp_path):
    database = Database(tmp_path / "manager.sqlite3")
    database.initialize()
    assets = AssetStore(tmp_path / "data", database)
    packs = PackService(database, assets)
    candidates = CandidateService(database, assets, packs)
    baselines = BaselineService(database, assets, packs, candidates)

    asset = assets.put_bytes("reference.png", PNG, "image/png")
    character = packs.create_pack("character", "BOT1")
    character2 = packs.create_pack("character", "BOT2")
    scene = packs.create_pack("scene", "Studio")
    character_version = packs.create_version(
        character.id,
        character_manifest_v2([asset.id]),
    )
    character2_version = packs.create_version(
        character2.id,
        {
            **character_manifest_v2([asset.id]),
            "persona": "Curious.",
            "voice_direction": "Warm.",
        },
    )
    scene_version = packs.create_version(
        scene.id,
        scene_manifest_v2([asset.id]),
    )
    candidate = candidates.create(
        character_versions={
            "BOT1": (character.id, character_version.version),
            "BOT2": (character2.id, character2_version.version),
        },
        scene_pack_id=scene.id,
        scene_version=scene_version.version,
        hero_asset_id=asset.id,
    )
    candidate = candidates.approve(
        candidate.id, canonical=True, review_note="approved"
    )
    baseline = baselines.lock_run(candidate.cast_key)

    assert assets.list_assets() == [asset]
    assert packs.list_versions(character.id) == [character_version]
    assert candidates.list_candidates() == [candidate]
    assert baselines.list_baselines() == [baseline]
