import hashlib
import json
import shutil
import struct
import zlib
from pathlib import Path

import pytest

from pack_manager.assets import AssetStore
from pack_manager.baselines import BaselineService
from pack_manager.candidates import CandidateService
from pack_manager.db import Database
from pack_manager.errors import IntegrityError, ValidationError
from pack_manager.packs import PackService
from pack_manager.runtime import load_locked_baseline

from conftest import character_manifest_v1, character_manifest_v2, scene_manifest_v2


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", checksum)


def make_png_bytes(
    width: int = 1344,
    height: int = 768,
    color: tuple[int, int, int] = (255, 128, 0),
) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(color) * width
    compressed = zlib.compress(row * height, 9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


def character_manifest(asset_ids):
    return character_manifest_v2(asset_ids)


def scene_manifest(asset_ids):
    return scene_manifest_v2(asset_ids)


@pytest.fixture
def flight_data_dir(tmp_path):
    data_dir = tmp_path / "pack-data"
    database = Database(data_dir / "manager.sqlite3")
    database.initialize()
    asset_store = AssetStore(data_dir, database)
    pack_service = PackService(database, asset_store)
    candidate_service = CandidateService(database, asset_store, pack_service)
    baseline_service = BaselineService(
        database, asset_store, pack_service, candidate_service
    )

    bot1_asset = asset_store.put_bytes("bot1.png", make_png_bytes(64, 64), "image/png")
    bot2_asset = asset_store.put_bytes("bot2.png", make_png_bytes(64, 64, (0, 128, 255)), "image/png")
    scene_asset = asset_store.put_bytes("studio.png", make_png_bytes(64, 64, (200, 200, 200)), "image/png")
    hero = asset_store.put_bytes("hero.png", make_png_bytes(), "image/png")

    bot1 = pack_service.create_pack("character", "BOT1")
    bot2 = pack_service.create_pack("character", "BOT2")
    scene = pack_service.create_pack("scene", "Studio")
    bot1_version = pack_service.create_version(
        bot1.id, character_manifest([bot1_asset.id])
    )
    bot2_version = pack_service.create_version(
        bot2.id, character_manifest([bot2_asset.id])
    )
    scene_version = pack_service.create_version(
        scene.id, scene_manifest([scene_asset.id])
    )
    candidate = candidate_service.create(
        character_versions={
            "BOT1": (bot1_version.pack_id, bot1_version.version),
            "BOT2": (bot2_version.pack_id, bot2_version.version),
        },
        scene_pack_id=scene_version.pack_id,
        scene_version=scene_version.version,
        hero_asset_id=hero.id,
    )
    approved = candidate_service.approve(
        candidate.id, canonical=True, review_note="flight-ready"
    )
    locked = baseline_service.lock_run(approved.cast_key)

    return {
        "data_dir": data_dir,
        "baseline_service": baseline_service,
        "locked": locked,
        "hero_bytes": make_png_bytes(),
    }


def test_load_locked_baseline_verifies_manifest_and_export_hashes(flight_data_dir):
    loaded = load_locked_baseline(flight_data_dir["data_dir"], flight_data_dir["locked"].id)

    manifest_bytes = loaded.manifest_path.read_bytes()
    row = flight_data_dir["baseline_service"]._get_row(flight_data_dir["locked"].id)
    assert hashlib.sha256(manifest_bytes).hexdigest() == row["manifest_sha256"]
    for file_record in loaded.manifest["files"]:
        path = loaded.manifest_path.parent / file_record["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == file_record["sha256"]


def test_load_locked_baseline_rejects_tampered_manifest_hash(flight_data_dir):
    locked = flight_data_dir["locked"]
    locked.manifest_path.write_bytes(b"tampered manifest\n")

    with pytest.raises(IntegrityError, match="manifest hash mismatch"):
        load_locked_baseline(flight_data_dir["data_dir"], locked.id)


def test_load_locked_baseline_rejects_tampered_export_file_hash(flight_data_dir):
    locked = flight_data_dir["locked"]
    locked.hero_path.write_bytes(b"tampered hero")

    with pytest.raises(IntegrityError, match="hash mismatch"):
        load_locked_baseline(flight_data_dir["data_dir"], locked.id)


def test_load_locked_baseline_rejects_v1_character_pack_export(flight_data_dir):
    service = flight_data_dir["baseline_service"]
    locked = flight_data_dir["locked"]
    export_dir = locked.manifest_path.parent
    manifest = json.loads(locked.manifest_path.read_text())
    malicious_id = "baseline_runtime_v1_character"
    manifest["baseline_id"] = malicious_id
    character_path = export_dir / manifest["packs"]["characters"][0]["path"]
    payload = json.loads(character_path.read_text())
    payload["manifest"] = character_manifest_v1(payload["manifest"]["asset_ids"])
    payload_bytes = service._normalized_json(payload)
    malicious_dir = service.export_root / malicious_id
    shutil.copytree(export_dir, malicious_dir)
    (malicious_dir / character_path.relative_to(export_dir)).write_bytes(payload_bytes)
    for file_record in manifest["files"]:
        if file_record["path"] == character_path.relative_to(export_dir).as_posix():
            file_record["sha256"] = hashlib.sha256(payload_bytes).hexdigest()
    manifest_bytes = service._normalized_json(manifest)
    manifest_path = malicious_dir / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    with service.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO baselines (
                id, cast_key, candidate_id, canonical_candidate_id,
                fallback_reason, manifest_path, manifest_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                malicious_id,
                locked.cast_key,
                locked.candidate_id,
                locked.canonical_candidate_id,
                None,
                str(manifest_path),
                hashlib.sha256(manifest_bytes).hexdigest(),
                locked.created_at,
            ),
        )

    with pytest.raises(ValidationError, match="schema_version|flight"):
        load_locked_baseline(flight_data_dir["data_dir"], malicious_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host_map", {"BOT1": "host_a"}),
        ("host_map", {"BOT1": "host_a", "BOT2": "host_wrong"}),
        ("display_names", {"BOT1": "BOT1"}),
        ("display_names", {"BOT1": "BOT1", "BOT2": ""}),
    ],
)
def test_load_locked_baseline_rejects_invalid_host_mapping_or_display_names(
    flight_data_dir, field, value
):
    service = flight_data_dir["baseline_service"]
    locked = flight_data_dir["locked"]
    malicious_id = f"baseline_runtime_{field}"
    malicious_dir = service.export_root / malicious_id
    shutil.copytree(locked.manifest_path.parent, malicious_dir)
    manifest_path = malicious_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["baseline_id"] = malicious_id
    manifest[field] = value
    manifest_bytes = service._normalized_json(manifest)
    manifest_path.write_bytes(manifest_bytes)
    with service.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO baselines (
                id, cast_key, candidate_id, canonical_candidate_id,
                fallback_reason, manifest_path, manifest_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                malicious_id,
                locked.cast_key,
                locked.candidate_id,
                locked.canonical_candidate_id,
                None,
                str(manifest_path),
                hashlib.sha256(manifest_bytes).hexdigest(),
                locked.created_at,
            ),
        )

    with pytest.raises(IntegrityError, match="host mapping|display names"):
        load_locked_baseline(flight_data_dir["data_dir"], malicious_id)


@pytest.mark.parametrize(
    "slots",
    [
        ["BOT1"],
        ["BOT1", "BOT2", "BOT3"],
        ["BOT1", "HOST_B"],
    ],
)
def test_load_locked_baseline_rejects_invalid_character_slots(flight_data_dir, slots):
    service = flight_data_dir["baseline_service"]
    locked = flight_data_dir["locked"]
    malicious_id = f"baseline_slots_{'-'.join(slots)}"
    malicious_dir = service.export_root / malicious_id
    shutil.copytree(locked.manifest_path.parent, malicious_dir)
    manifest_path = malicious_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["baseline_id"] = malicious_id
    characters = manifest["packs"]["characters"]
    for index, slot in enumerate(slots):
        if index < len(characters):
            characters[index]["slot"] = slot
        else:
            characters.append({**characters[0], "slot": slot, "path": f"packs/extra-{index}.json"})
    manifest["packs"]["characters"] = characters[: len(slots)]
    manifest_bytes = service._normalized_json(manifest)
    manifest_path.write_bytes(manifest_bytes)
    with service.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO baselines (
                id, cast_key, candidate_id, canonical_candidate_id,
                fallback_reason, manifest_path, manifest_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                malicious_id,
                locked.cast_key,
                locked.candidate_id,
                locked.canonical_candidate_id,
                None,
                str(manifest_path),
                hashlib.sha256(manifest_bytes).hexdigest(),
                locked.created_at,
            ),
        )

    with pytest.raises(
        (IntegrityError, ValidationError),
        match="slot|BOT1|BOT2|manifest file references|character pack metadata|display names",
    ):
        load_locked_baseline(flight_data_dir["data_dir"], malicious_id)


def test_load_locked_baseline_returns_pack_truth_scene_and_reset_interval(flight_data_dir):
    loaded = load_locked_baseline(flight_data_dir["data_dir"], flight_data_dir["locked"].id)
    manifest = loaded.manifest

    assert manifest["host_map"] == {"BOT1": "host_a", "BOT2": "host_b"}
    assert manifest["display_names"] == {"BOT1": "BOT1", "BOT2": "BOT2"}
    assert manifest["reanchor_every"] == 60
    assert manifest["frame"] == {"fps": 30, "h": 1080, "w": 1920}
    assert manifest["hero"]["sha256"] == hashlib.sha256(flight_data_dir["hero_bytes"]).hexdigest()
    assert loaded.hero_path == flight_data_dir["locked"].hero_path
