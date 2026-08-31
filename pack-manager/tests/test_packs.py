import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from pack_manager.assets import AssetStore
from pack_manager.db import Database
from pack_manager.errors import ValidationError
from pack_manager.packs import PackService

from conftest import (
    character_manifest_v1,
    character_manifest_v2,
    disabled_tts_block,
    scene_manifest_v1,
    scene_manifest_v2,
)


@pytest.fixture
def pack_service(tmp_path):
    database = Database(tmp_path / "manager.sqlite3")
    database.initialize()
    asset_store = AssetStore(tmp_path / "data", database)
    return PackService(database, asset_store)


def character_manifest(asset_ids=()):
    return character_manifest_v1(asset_ids)


def scene_manifest(asset_ids=()):
    return scene_manifest_v1(asset_ids)


def test_versions_are_monotonic_and_immutable(pack_service):
    pack = pack_service.create_pack("character", "PHASEONE[lol]")
    v1 = pack_service.create_version(pack.id, character_manifest())
    changed = character_manifest()
    changed["persona"] = "More curious."
    v2 = pack_service.create_version(pack.id, changed)

    assert (v1.version, v2.version) == (1, 2)
    assert pack_service.get_version(pack.id, 1).manifest["persona"] != "More curious."


@pytest.mark.parametrize("name", ["", " ", "\t\n"])
def test_pack_name_rejects_blank_before_persistence(pack_service, name):
    with pytest.raises(ValidationError, match="name"):
        pack_service.create_pack("character", name)

    assert pack_service.list_packs() == []


def test_pack_name_strips_surrounding_whitespace(pack_service):
    pack = pack_service.create_pack("character", "  PHASEONE[lol] Host  ")

    assert pack.name == "PHASEONE[lol] Host"
    assert pack_service.list_packs() == [pack]


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


def test_v1_character_manifest_remains_readable(pack_service):
    pack = pack_service.create_pack("character", "legacy")
    created = pack_service.create_version(pack.id, character_manifest_v1())

    assert created.manifest == character_manifest_v1()
    assert PackService.schema_version(created.manifest) == 1


def test_v2_character_manifest_requires_schema_version(pack_service):
    pack = pack_service.create_pack("character", "flight")
    manifest = character_manifest_v2()
    del manifest["schema_version"]

    with pytest.raises(ValidationError, match="schema_version"):
        pack_service.create_version(pack.id, manifest)


@pytest.mark.parametrize(
    "descriptor",
    ["silhouette", "eye_design", "proportions"],
)
def test_v2_character_requires_visual_descriptors(pack_service, descriptor):
    pack = pack_service.create_pack("character", "flight")
    manifest = character_manifest_v2()
    del manifest["visual_invariants"][descriptor]

    with pytest.raises(ValidationError, match=descriptor):
        pack_service.create_version(pack.id, manifest)


def test_v2_character_requires_nonempty_voice_direction(pack_service):
    pack = pack_service.create_pack("character", "flight")
    manifest = character_manifest_v2()
    manifest["voice_direction"] = "   "

    with pytest.raises(ValidationError, match="voice_direction"):
        pack_service.create_version(pack.id, manifest)


def test_v2_character_accepts_disabled_tts_with_null_provider_fields(pack_service):
    pack = pack_service.create_pack("character", "flight")

    version = pack_service.create_version(pack.id, character_manifest_v2())

    assert version.manifest["schema_version"] == 2
    assert version.manifest["tts"]["enabled"] is False
    assert version.manifest["tts"]["provider"] is None
    assert version.manifest["tts"]["voice_id"] is None


def test_v2_character_rejects_tts_provider_credentials(pack_service):
    pack = pack_service.create_pack("character", "flight")
    manifest = character_manifest_v2()
    manifest["tts"]["api_key"] = "secret-token"

    with pytest.raises(ValidationError, match="credential|api_key|secret"):
        pack_service.create_version(pack.id, manifest)


def test_manifest_rejects_nested_credentials_in_writer_rules(pack_service):
    pack = pack_service.create_pack("character", "flight")
    manifest = character_manifest_v2()
    manifest["writer_rules"].append({"apiKey": "nested"})

    with pytest.raises(ValidationError, match="credential|apikey|token"):
        pack_service.create_version(pack.id, manifest)


def test_scene_manifest_rejects_nested_credentials(pack_service):
    pack = pack_service.create_pack("scene", "flight")
    manifest = scene_manifest_v2()
    manifest["frame"]["access_token"] = "secret"

    with pytest.raises(ValidationError, match="credential|token"):
        pack_service.create_version(pack.id, manifest)


def test_v2_character_rejects_enabled_tts_even_with_license(pack_service):
    pack = pack_service.create_pack("character", "flight")
    manifest = character_manifest_v2()
    manifest["tts"]["enabled"] = True
    manifest["tts"]["provider"] = "example"
    manifest["tts"]["voice_id"] = "voice-1"
    manifest["tts"]["license"]["broadcast_rights_confirmed"] = True

    with pytest.raises(ValidationError, match="tts.enabled|not supported|disabled"):
        pack_service.create_version(pack.id, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider", "vendor"),
        ("voice_id", "voice-1"),
        ("speed", 1.0),
        ("pitch", 0.0),
        ("max_duration_s", 5),
        ("pronunciations", [{"word": "bot", "alias": "bought"}]),
    ],
)
def test_v2_character_rejects_malformed_disabled_tts_fields(
    pack_service, field, value
):
    pack = pack_service.create_pack("character", "flight")
    manifest = character_manifest_v2()
    manifest["tts"][field] = value

    with pytest.raises(ValidationError, match=f"tts\\.{field}|tts"):
        pack_service.create_version(pack.id, manifest)


@pytest.mark.parametrize("value", [True, 2.0, "2"])
def test_schema_version_rejects_non_integer(pack_service, value):
    pack = pack_service.create_pack("character", "flight")
    manifest = character_manifest_v2()
    manifest["schema_version"] = value

    with pytest.raises(ValidationError, match="schema_version"):
        pack_service.create_version(pack.id, manifest)


def test_v2_character_rejects_unknown_tts_fields(pack_service):
    pack = pack_service.create_pack("character", "flight")
    manifest = character_manifest_v2()
    manifest["tts"]["model"] = "future"

    with pytest.raises(ValidationError, match="tts"):
        pack_service.create_version(pack.id, manifest)


def test_validate_flight_ready_rejects_malformed_v2_character_missing_descriptor():
    manifest = character_manifest_v2()
    del manifest["visual_invariants"]["silhouette"]

    with pytest.raises(ValidationError, match="silhouette|visual_invariants"):
        PackService.validate_flight_ready("character", manifest)


def test_validate_flight_ready_rejects_malformed_v2_character_enabled_tts():
    manifest = character_manifest_v2()
    manifest["tts"]["enabled"] = True
    manifest["tts"]["provider"] = "example"
    manifest["tts"]["voice_id"] = "voice-1"

    with pytest.raises(ValidationError, match="tts.enabled|not supported|disabled"):
        PackService.validate_flight_ready("character", manifest)


def test_validate_flight_ready_rejects_malformed_v2_scene_missing_schema():
    manifest = scene_manifest_v2()
    manifest["schema_version"] = 1

    with pytest.raises(ValidationError, match="schema_version|flight"):
        PackService.validate_flight_ready("scene", manifest)


def test_validate_flight_ready_enforces_v2_character_validator_path(pack_service):
    pack = pack_service.create_pack("character", "flight")
    version = pack_service.create_version(pack.id, character_manifest_v2())
    manifest = version.manifest
    manifest["voice_direction"] = "   "

    with pytest.raises(ValidationError, match="voice_direction"):
        PackService.validate_flight_ready("character", manifest)


def test_flight_ready_rejects_v1_character_manifest(pack_service):
    pack = pack_service.create_pack("character", "legacy")
    version = pack_service.create_version(pack.id, character_manifest_v1())

    with pytest.raises(ValidationError, match="schema_version|flight"):
        PackService.validate_flight_ready("character", version.manifest)


def test_flight_ready_accepts_v2_character_manifest(pack_service):
    pack = pack_service.create_pack("character", "flight")
    version = pack_service.create_version(pack.id, character_manifest_v2())

    PackService.validate_flight_ready("character", version.manifest)


def test_v2_scene_manifest_rejects_invalid_schema_version(pack_service):
    pack = pack_service.create_pack("scene", "flight")
    manifest = scene_manifest_v2()
    manifest["schema_version"] = 3

    with pytest.raises(ValidationError, match="schema_version"):
        pack_service.create_version(pack.id, manifest)


def test_flight_ready_rejects_v1_scene_manifest(pack_service):
    pack = pack_service.create_pack("scene", "legacy")
    version = pack_service.create_version(pack.id, scene_manifest_v1())

    with pytest.raises(ValidationError, match="schema_version|flight"):
        PackService.validate_flight_ready("scene", version.manifest)


def test_v2_scene_manifest_is_flight_ready(pack_service):
    pack = pack_service.create_pack("scene", "flight")
    version = pack_service.create_version(pack.id, scene_manifest_v2())

    PackService.validate_flight_ready("scene", version.manifest)
    assert version.manifest["schema_version"] == 2
