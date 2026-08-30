import pytest

from pack_manager.assets import AssetStore
from pack_manager.db import Database
from pack_manager.errors import ValidationError
from pack_manager.packs import PackService


@pytest.fixture
def pack_service(tmp_path):
    database = Database(tmp_path / "manager.sqlite3")
    database.initialize()
    asset_store = AssetStore(tmp_path / "data", database)
    return PackService(database, asset_store)


def character_manifest(asset_ids=()):
    return {
        "visual_invariants": {
            "locked_traits": ["silhouette", "eye_design", "proportions"]
        },
        "persona": "Calm and curious.",
        "writer_rules": ["Prefer evidence."],
        "voice_direction": "Measured and warm.",
        "asset_ids": list(asset_ids),
    }


def scene_manifest(asset_ids=()):
    return {
        "set": "Warm studio",
        "palette": ["orange", "cream"],
        "lighting": "Soft key light",
        "frame": {"w": 1920, "h": 1080, "fps": 30},
        "reanchor_every": 60,
        "asset_ids": list(asset_ids),
    }


def test_versions_are_monotonic_and_immutable(pack_service):
    pack = pack_service.create_pack("character", "PHASEONE[lol]")
    v1 = pack_service.create_version(pack.id, character_manifest())
    changed = character_manifest()
    changed["persona"] = "More curious."
    v2 = pack_service.create_version(pack.id, changed)

    assert (v1.version, v2.version) == (1, 2)
    assert pack_service.get_version(pack.id, 1).manifest["persona"] != "More curious."


def test_character_manifest_requires_locked_traits(pack_service):
    pack = pack_service.create_pack("character", "deb")

    with pytest.raises(ValidationError, match="locked_traits"):
        pack_service.create_version(pack.id, {"persona": "Curious"})


def test_scene_manifest_requires_frame(pack_service):
    pack = pack_service.create_pack("scene", "Light studio")

    with pytest.raises(ValidationError, match="frame"):
        pack_service.create_version(pack.id, {"set": "Warm studio"})


def test_character_locked_traits_are_exact(pack_service):
    pack = pack_service.create_pack("character", "deb")
    manifest = character_manifest()
    manifest["visual_invariants"]["locked_traits"].append("color")

    with pytest.raises(ValidationError, match="locked_traits"):
        pack_service.create_version(pack.id, manifest)


def test_version_requires_existing_assets(pack_service):
    pack = pack_service.create_pack("scene", "Light studio")

    with pytest.raises(ValidationError, match="asset_missing"):
        pack_service.create_version(pack.id, scene_manifest(["asset_missing"]))


def test_list_packs_can_filter_by_kind(pack_service):
    character = pack_service.create_pack("character", "deb")
    scene = pack_service.create_pack("scene", "Light studio")

    assert pack_service.list_packs() == [character, scene]
    assert pack_service.list_packs("scene") == [scene]


def test_rejects_unknown_pack_kind(pack_service):
    with pytest.raises(ValidationError, match="kind"):
        pack_service.create_pack("prop", "Desk")
