import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from pack_manager.assets import AssetStore
from pack_manager.baselines import BaselineService
from pack_manager.candidates import CandidateService
from pack_manager.db import Database
from pack_manager.errors import IntegrityError
from pack_manager.packs import PackService


def character_manifest(asset_ids):
    return {
        "visual_invariants": {
            "locked_traits": ["silhouette", "eye_design", "proportions"]
        },
        "persona": "Calm and curious.",
        "writer_rules": ["Prefer evidence."],
        "voice_direction": "Measured and warm.",
        "asset_ids": list(asset_ids),
    }


def scene_manifest(asset_ids):
    return {
        "set": "Warm studio",
        "palette": ["orange", "cream"],
        "lighting": "Soft key light",
        "frame": {"w": 1920, "h": 1080, "fps": 30},
        "reanchor_every": 60,
        "asset_ids": list(asset_ids),
    }


@pytest.fixture
def baseline_setup(tmp_path):
    database = Database(tmp_path / "manager.sqlite3")
    database.initialize()
    data_dir = tmp_path / "data"
    asset_store = AssetStore(data_dir, database)
    pack_service = PackService(database, asset_store)
    candidate_service = CandidateService(database, asset_store, pack_service)
    baseline_service = BaselineService(
        database, asset_store, pack_service, candidate_service
    )

    bot1_asset = asset_store.put_bytes("bot1.png", b"bot1", "image/png")
    bot2_asset = asset_store.put_bytes("bot2.webp", b"bot2", "image/webp")
    scene_asset = asset_store.put_bytes("studio.jpg", b"studio", "image/jpeg")
    hero = asset_store.put_bytes("hero.png", b"canonical hero", "image/png")
    variant_hero = asset_store.put_bytes(
        "variant.png", b"variant hero", "image/png"
    )

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
    canonical = candidate_service.create(
        character_versions={
            "BOT1": (bot1_version.pack_id, bot1_version.version),
            "BOT2": (bot2_version.pack_id, bot2_version.version),
        },
        scene_pack_id=scene_version.pack_id,
        scene_version=scene_version.version,
        hero_asset_id=hero.id,
    )
    approved_canonical = candidate_service.approve(
        canonical.id, canonical=True, review_note="M0 passed"
    )
    draft_variant = candidate_service.create_variant(
        canonical_candidate_id=approved_canonical.id,
        hero_asset_id=variant_hero.id,
        theme="Christmas",
        changes={"palette": ["red", "green"], "accessories": ["Santa hat"]},
    )

    return {
        "database": database,
        "data_dir": data_dir,
        "asset_store": asset_store,
        "pack_service": pack_service,
        "candidate_service": candidate_service,
        "baseline_service": baseline_service,
        "approved_canonical": approved_canonical,
        "draft_variant": draft_variant,
        "source_assets": (bot1_asset, bot2_asset, scene_asset, hero, variant_hero),
    }


@pytest.fixture
def database(baseline_setup):
    return baseline_setup["database"]


@pytest.fixture
def baseline_service(baseline_setup):
    return baseline_setup["baseline_service"]


@pytest.fixture
def approved_canonical(baseline_setup):
    return baseline_setup["approved_canonical"]


@pytest.fixture
def draft_variant(baseline_setup):
    return baseline_setup["draft_variant"]


@pytest.fixture
def approved_variant(baseline_setup, draft_variant):
    return baseline_setup["candidate_service"].approve(
        draft_variant.id, canonical=False, review_note="Theme passed"
    )


@pytest.fixture
def locked_baseline(baseline_service, approved_canonical):
    return baseline_service.lock_run(approved_canonical.cast_key)


def test_lock_run_exports_selected_approved_variant(
    baseline_service, approved_canonical, approved_variant
):
    baseline = baseline_service.lock_run(
        approved_canonical.cast_key,
        requested_candidate_id=approved_variant.id,
    )

    manifest = json.loads(baseline.manifest_path.read_text())

    assert manifest["candidate_id"] == approved_variant.id
    assert manifest["canonical_candidate_id"] == approved_canonical.id
    assert manifest["fallback_reason"] is None
    assert baseline.hero_path.read_bytes() == b"variant hero"


def test_lock_run_records_canonical_fallback(
    baseline_service, approved_canonical, draft_variant
):
    baseline = baseline_service.lock_run(
        approved_canonical.cast_key,
        requested_candidate_id=draft_variant.id,
    )

    manifest = json.loads(baseline.manifest_path.read_text())

    assert manifest["candidate_id"] == approved_canonical.id
    assert manifest["canonical_candidate_id"] == approved_canonical.id
    assert manifest["fallback_reason"] == "requested candidate is not approved"


def test_export_is_self_contained_normalized_and_uses_relative_paths(
    baseline_setup, locked_baseline
):
    manifest_bytes = locked_baseline.manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)

    assert manifest_bytes == (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    assert manifest["frame"] == {"fps": 30, "h": 1080, "w": 1920}
    assert manifest["reanchor_every"] == 60
    assert len(manifest["packs"]["characters"]) == 2
    assert len(manifest["assets"]) == 3
    for file_record in manifest["files"]:
        path = Path(file_record["path"])
        assert not path.is_absolute()
        assert ".." not in path.parts
        exported = locked_baseline.manifest_path.parent / path
        assert hashlib.sha256(exported.read_bytes()).hexdigest() == file_record["sha256"]

    for asset in baseline_setup["source_assets"]:
        asset.path.unlink()

    loaded = baseline_setup["baseline_service"].load(locked_baseline.id)
    assert loaded.hero_path.read_bytes() == b"canonical hero"
    assert len(loaded.pack_paths) == 3
    assert len(loaded.asset_paths) == 3


def test_locked_export_rejects_tampering(baseline_service, locked_baseline):
    locked_baseline.hero_path.write_bytes(b"tampered")

    with pytest.raises(IntegrityError, match="hash mismatch"):
        baseline_service.verify(locked_baseline.id)


def test_loader_rejects_relative_path_escape(baseline_setup, locked_baseline):
    original = json.loads(locked_baseline.manifest_path.read_text())
    malicious_id = "baseline_path_escape"
    malicious_dir = baseline_setup["data_dir"] / "exports" / malicious_id
    malicious_dir.mkdir()
    malicious = dict(original)
    malicious["baseline_id"] = malicious_id
    malicious["files"] = [dict(item) for item in original["files"]]
    malicious["files"][0]["path"] = "../outside.png"
    manifest_bytes = (
        json.dumps(malicious, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    manifest_path = malicious_dir / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    with baseline_setup["database"].connect() as connection:
        connection.execute(
            """
            INSERT INTO baselines (
                id, cast_key, candidate_id, canonical_candidate_id,
                fallback_reason, manifest_path, manifest_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                malicious_id,
                locked_baseline.cast_key,
                locked_baseline.candidate_id,
                locked_baseline.canonical_candidate_id,
                None,
                str(manifest_path),
                digest,
                locked_baseline.created_at,
            ),
        )

    with pytest.raises(IntegrityError, match="path escape"):
        baseline_setup["baseline_service"].load(malicious_id)


def test_locked_baseline_cannot_be_updated(database, locked_baseline):
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with database.connect() as connection:
            connection.execute(
                "UPDATE baselines SET fallback_reason = ? WHERE id = ?",
                ("changed", locked_baseline.id),
            )


def test_locked_baseline_cannot_be_deleted(database, locked_baseline):
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with database.connect() as connection:
            connection.execute(
                "DELETE FROM baselines WHERE id = ?", (locked_baseline.id,)
            )
