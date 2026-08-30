import sqlite3
from concurrent.futures import ThreadPoolExecutor

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


def test_concurrent_version_allocation_is_unique_and_monotonic(pack_service):
    pack = pack_service.create_pack("character", "PHASEONE[lol]")

    with ThreadPoolExecutor(max_workers=8) as executor:
        versions = list(
            executor.map(
                lambda index: pack_service.create_version(
                    pack.id,
                    {
                        **character_manifest(),
                        "persona": f"Persona {index}",
                    },
                ),
                range(16),
            )
        )

    assert sorted(version.version for version in versions) == list(range(1, 17))
    assert [
        version.version for version in pack_service.list_versions(pack.id)
    ] == list(range(1, 17))


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE pack_versions SET manifest = '{}' WHERE pack_id = ? AND version = 1",
        "DELETE FROM pack_versions WHERE pack_id = ? AND version = 1",
    ],
)
def test_pack_versions_are_database_immutable(pack_service, statement):
    pack = pack_service.create_pack("character", "PHASEONE[lol]")
    pack_service.create_version(pack.id, character_manifest())

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with pack_service.database.connect() as connection:
            connection.execute(statement, (pack.id,))


def test_returned_manifest_mutation_cannot_change_version_truth(pack_service):
    pack = pack_service.create_pack("character", "deb")
    expected = character_manifest()
    created = pack_service.create_version(pack.id, expected)

    exposed = created.manifest
    exposed["persona"] = "Tampered"
    exposed["visual_invariants"]["locked_traits"].append("color")

    assert created.manifest == expected
    assert pack_service.get_version(pack.id, 1).manifest == expected


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


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("visual_invariants", "visual_invariants"),
        ("persona", "persona"),
        ("writer_rules", "writer_rules"),
        ("voice_direction", "voice_direction"),
        ("asset_ids", "asset_ids"),
    ],
)
def test_character_manifest_requires_every_field(pack_service, field, message):
    pack = pack_service.create_pack("character", "deb")
    manifest = character_manifest()
    del manifest[field]

    with pytest.raises(ValidationError, match=message):
        pack_service.create_version(pack.id, manifest)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("set", "set"),
        ("palette", "palette"),
        ("lighting", "lighting"),
        ("frame", "frame"),
        ("reanchor_every", "reanchor_every"),
        ("asset_ids", "asset_ids"),
    ],
)
def test_scene_manifest_requires_every_field(pack_service, field, message):
    pack = pack_service.create_pack("scene", "Light studio")
    manifest = scene_manifest()
    del manifest[field]

    with pytest.raises(ValidationError, match=message):
        pack_service.create_version(pack.id, manifest)


@pytest.mark.parametrize("field", ["w", "h", "fps"])
def test_scene_frame_requires_every_field(pack_service, field):
    pack = pack_service.create_pack("scene", "Light studio")
    manifest = scene_manifest()
    del manifest["frame"][field]

    with pytest.raises(ValidationError, match=rf"frame\.{field}"):
        pack_service.create_version(pack.id, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("persona", ""),
        ("persona", "   "),
        ("persona", 1),
        ("voice_direction", ""),
        ("voice_direction", None),
        ("writer_rules", "Prefer evidence."),
        ("writer_rules", {}),
        ("visual_invariants", []),
        ("asset_ids", ()),
    ],
)
def test_character_manifest_rejects_invalid_structures(
    pack_service, field, value
):
    pack = pack_service.create_pack("character", "deb")
    manifest = character_manifest()
    manifest[field] = value

    with pytest.raises(ValidationError, match=field):
        pack_service.create_version(pack.id, manifest)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("frame", "w"), 0, r"frame\.w"),
        (("frame", "h"), -1, r"frame\.h"),
        (("frame", "fps"), 1.5, r"frame\.fps"),
        (("frame", "fps"), True, r"frame\.fps"),
        (("reanchor_every",), 0, "reanchor_every"),
        (("reanchor_every",), False, "reanchor_every"),
        (("set",), "  ", "set"),
        (("palette",), [], "palette"),
        (("palette",), ["  "], "palette"),
        (("palette",), {}, "palette"),
        (("lighting",), None, "lighting"),
        (("frame",), [], "frame"),
        (("asset_ids",), (), "asset_ids"),
    ],
)
def test_scene_manifest_rejects_invalid_values(
    pack_service, path, value, message
):
    pack = pack_service.create_pack("scene", "Light studio")
    manifest = scene_manifest()
    target = manifest
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    with pytest.raises(ValidationError, match=message):
        pack_service.create_version(pack.id, manifest)


def test_version_requires_existing_assets(pack_service):
    pack = pack_service.create_pack("scene", "Light studio")

    with pytest.raises(ValidationError, match="asset_missing"):
        pack_service.create_version(pack.id, scene_manifest(["asset_missing"]))


def test_version_accepts_existing_asset_reference(pack_service):
    asset = pack_service.asset_store.put_bytes(
        "reference.png", b"\x89PNG\r\n\x1a\nreference", "image/png"
    )
    pack = pack_service.create_pack("character", "deb")

    version = pack_service.create_version(pack.id, character_manifest([asset.id]))

    assert version.manifest["asset_ids"] == [asset.id]


def test_list_packs_can_filter_by_kind(pack_service):
    character = pack_service.create_pack("character", "deb")
    scene = pack_service.create_pack("scene", "Light studio")

    assert pack_service.list_packs() == [character, scene]
    assert pack_service.list_packs("scene") == [scene]


def test_rejects_unknown_pack_kind(pack_service):
    with pytest.raises(ValidationError, match="kind"):
        pack_service.create_pack("prop", "Desk")
