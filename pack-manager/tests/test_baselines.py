import hashlib
import json
import shutil
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from pack_manager.assets import AssetStore
from pack_manager.baselines import BaselineService
from pack_manager.candidates import CandidateService
from pack_manager.db import Database
from pack_manager.errors import IntegrityError, ValidationError
from pack_manager.packs import PackService

from conftest import character_manifest_v1, character_manifest_v2, scene_manifest_v2


def character_manifest(asset_ids):
    return character_manifest_v2(asset_ids)


def scene_manifest(asset_ids):
    return scene_manifest_v2(asset_ids)


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
        changes={
            "palette": ["red", "green"],
            "accessories": {"BOT1": ["Santa hat"]},
        },
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
        draft_variant.id,
        canonical=False,
        review_note="Theme passed",
        invariants_verified=True,
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
    assert manifest["host_map"] == {"BOT1": "host_a", "BOT2": "host_b"}
    assert manifest["display_names"] == {"BOT1": "BOT1", "BOT2": "BOT2"}
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
    assert loaded.manifest["host_map"] == {"BOT1": "host_a", "BOT2": "host_b"}
    assert loaded.manifest["display_names"] == {"BOT1": "BOT1", "BOT2": "BOT2"}


def test_variant_export_uses_alternate_scene_pack(baseline_setup):
    packs = baseline_setup["pack_service"]
    candidates = baseline_setup["candidate_service"]
    alternate = packs.create_pack("scene", "Snow")
    alternate_version = packs.create_version(alternate.id, scene_manifest([]))
    variant = candidates.create_variant(
        canonical_candidate_id=baseline_setup["approved_canonical"].id,
        hero_asset_id=baseline_setup["approved_canonical"].hero_asset_id,
        theme="Snow",
        changes={"scene": {"weather": "snow"}},
        scene_pack_id=alternate.id,
        scene_version=alternate_version.version,
    )
    variant = candidates.approve(
        variant.id,
        canonical=False,
        review_note="verified",
        invariants_verified=True,
    )

    baseline = baseline_setup["baseline_service"].lock_run(
        variant.cast_key, requested_candidate_id=variant.id
    )
    manifest = json.loads(baseline.manifest_path.read_text())

    assert manifest["packs"]["scene"]["pack_id"] == alternate.id
    assert manifest["packs"]["scene"]["version"] == 1


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


@pytest.mark.parametrize("symlink_level", ["exports", "baseline"])
def test_loader_rejects_symlinked_export_root(
    baseline_setup, locked_baseline, symlink_level
):
    baseline_dir = locked_baseline.manifest_path.parent
    exports_dir = baseline_dir.parent
    original_root = exports_dir if symlink_level == "exports" else baseline_dir
    moved_root = baseline_setup["data_dir"] / f"moved-{symlink_level}"
    original_root.rename(moved_root)
    original_root.symlink_to(moved_root, target_is_directory=True)

    with pytest.raises(IntegrityError, match="symlink"):
        baseline_setup["baseline_service"].load(locked_baseline.id)


def test_loader_allows_symlinked_configured_data_directory(
    baseline_setup, locked_baseline, tmp_path
):
    linked_data_dir = tmp_path / "linked-data"
    linked_data_dir.symlink_to(
        baseline_setup["data_dir"], target_is_directory=True
    )
    linked_asset_store = AssetStore(
        linked_data_dir, baseline_setup["database"]
    )
    linked_service = BaselineService(
        baseline_setup["database"],
        linked_asset_store,
        baseline_setup["pack_service"],
        baseline_setup["candidate_service"],
    )

    loaded = linked_service.load(locked_baseline.id)

    assert loaded.hero_path.read_bytes() == b"canonical hero"


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


def test_list_baselines_skips_one_corrupt_export(
    baseline_service, approved_canonical
):
    corrupt = baseline_service.lock_run(approved_canonical.cast_key)
    healthy = baseline_service.lock_run(approved_canonical.cast_key)
    corrupt.hero_path.write_bytes(b"corrupt")

    listed = baseline_service.list_baselines()

    assert [item.id for item in listed] == [healthy.id]


def test_initialization_cleans_crash_orphans_safely(baseline_setup):
    export_root = baseline_setup["data_dir"] / "exports"
    temporary = export_root / ".tmp-baseline_crash"
    orphan = export_root / "baseline_orphan"
    unrelated = export_root / "operator-notes"
    temporary.mkdir(parents=True)
    orphan.mkdir()
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("keep")

    BaselineService(
        baseline_setup["database"],
        baseline_setup["asset_store"],
        baseline_setup["pack_service"],
        baseline_setup["candidate_service"],
    )

    assert not temporary.exists()
    assert not orphan.exists()
    assert (unrelated / "keep.txt").read_text() == "keep"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host_map", {"BOT1": "host_a"}),
        (
            "host_map",
            {"BOT1": "host_a", "BOT2": "host_b", "BOT3": "host_c"},
        ),
        ("display_names", {"BOT1": "BOT1"}),
        ("display_names", {"BOT1": "BOT1", "BOT2": ""}),
        (
            "display_names",
            {"BOT1": "BOT1", "BOT2": "BOT2", "BOT3": "BOT3"},
        ),
    ],
)
def test_loader_rejects_corrupt_runtime_slot_metadata(
    baseline_setup, locked_baseline, field, value
):
    service = baseline_setup["baseline_service"]
    original_dir = locked_baseline.manifest_path.parent
    malicious_id = f"baseline_corrupt_{field}_{len(value)}"
    malicious_dir = service.export_root / malicious_id
    shutil.copytree(original_dir, malicious_dir)
    manifest_path = malicious_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["baseline_id"] = malicious_id
    manifest[field] = value
    manifest_bytes = service._normalized_json(manifest)
    manifest_path.write_bytes(manifest_bytes)
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
                hashlib.sha256(manifest_bytes).hexdigest(),
                locked_baseline.created_at,
            ),
        )

    with pytest.raises(IntegrityError, match="host mapping|display names"):
        service.load(malicious_id)


@pytest.mark.parametrize(
    ("payload_kind", "field", "value"),
    [
        ("character", "slot", "BOT2"),
        ("character", "pack_id", "character_wrong"),
        ("character", "version", 999),
        ("scene", "pack_id", "scene_wrong"),
        ("scene", "version", 999),
    ],
)
def test_loader_rejects_rehashed_pack_payload_metadata_tampering(
    baseline_setup,
    locked_baseline,
    payload_kind,
    field,
    value,
):
    service = baseline_setup["baseline_service"]
    malicious_id = f"baseline_payload_{payload_kind}_{field}"
    malicious_dir = service.export_root / malicious_id
    shutil.copytree(locked_baseline.manifest_path.parent, malicious_dir)
    manifest_path = malicious_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["baseline_id"] = malicious_id
    record = (
        manifest["packs"]["characters"][0]
        if payload_kind == "character"
        else manifest["packs"]["scene"]
    )
    payload_path = malicious_dir / record["path"]
    payload = json.loads(payload_path.read_text())
    payload[field] = value
    payload_bytes = service._normalized_json(payload)
    payload_path.write_bytes(payload_bytes)
    for file_record in manifest["files"]:
        if file_record["path"] == record["path"]:
            file_record["sha256"] = hashlib.sha256(payload_bytes).hexdigest()
            break
    manifest_bytes = service._normalized_json(manifest)
    manifest_path.write_bytes(manifest_bytes)
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
                hashlib.sha256(manifest_bytes).hexdigest(),
                locked_baseline.created_at,
            ),
        )

    with pytest.raises(IntegrityError, match="pack metadata"):
        service.load(malicious_id)


def test_blank_pack_name_cannot_reach_baseline_export(baseline_setup):
    candidate = baseline_setup["approved_canonical"]
    with baseline_setup["database"].connect() as connection:
        connection.execute(
            "UPDATE packs SET name = '   ' WHERE id = ?",
            (candidate.character_versions[0].pack_id,),
        )

    with pytest.raises(IntegrityError, match="missing pack"):
        baseline_setup["baseline_service"].lock_run(candidate.cast_key)


def test_concurrent_same_cast_locks_are_separate_and_valid(
    baseline_service, approved_canonical
):
    with ThreadPoolExecutor(max_workers=4) as executor:
        baselines = list(
            executor.map(
                lambda _: baseline_service.lock_run(
                    approved_canonical.cast_key
                ),
                range(4),
            )
        )

    assert len({baseline.id for baseline in baselines}) == 4
    for baseline in baselines:
        baseline_service.verify(baseline.id)


def test_cleanup_cannot_remove_an_active_export(baseline_setup):
    service = baseline_setup["baseline_service"]
    export_started = threading.Event()
    allow_export = threading.Event()
    init_started = threading.Event()
    original_export = service._export

    def paused_export(**kwargs):
        export_started.set()
        assert allow_export.wait(timeout=5)
        return original_export(**kwargs)

    service._export = paused_export

    def initialize_second_service():
        init_started.set()
        return BaselineService(
            baseline_setup["database"],
            baseline_setup["asset_store"],
            baseline_setup["pack_service"],
            baseline_setup["candidate_service"],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        lock_future = executor.submit(
            service.lock_run,
            baseline_setup["approved_canonical"].cast_key,
        )
        assert export_started.wait(timeout=5)
        init_future = executor.submit(initialize_second_service)
        assert init_started.wait(timeout=5)
        time.sleep(0.1)
        try:
            assert not init_future.done()
        finally:
            allow_export.set()
        baseline = lock_future.result(timeout=5)
        init_future.result(timeout=5)

    service.verify(baseline.id)


def test_lock_run_rejects_v1_packs(baseline_setup):
    packs = baseline_setup["pack_service"]
    candidates = baseline_setup["candidate_service"]
    baselines = baseline_setup["baseline_service"]
    asset = baseline_setup["source_assets"][0]

    bot1 = packs.create_pack("character", "Legacy BOT1")
    bot2 = packs.create_pack("character", "Legacy BOT2")
    scene = packs.create_pack("scene", "Legacy Studio")
    bot1_version = packs.create_version(bot1.id, character_manifest_v1([asset.id]))
    bot2_version = packs.create_version(bot2.id, character_manifest_v1([asset.id]))
    scene_version = packs.create_version(scene.id, scene_manifest_v2([asset.id]))
    hero = baseline_setup["source_assets"][3]
    candidate = candidates.create(
        character_versions={
            "BOT1": (bot1_version.pack_id, bot1_version.version),
            "BOT2": (bot2_version.pack_id, bot2_version.version),
        },
        scene_pack_id=scene_version.pack_id,
        scene_version=scene_version.version,
        hero_asset_id=hero.id,
    )
    candidate = candidates.approve(
        candidate.id, canonical=True, review_note="legacy packs"
    )

    with pytest.raises(ValidationError, match="schema_version|flight"):
        baselines.lock_run(candidate.cast_key)


def test_export_preserves_schema_version_and_visual_descriptors(
    baseline_setup, locked_baseline
):
    manifest = json.loads(locked_baseline.manifest_path.read_text())
    character_path = locked_baseline.manifest_path.parent / manifest["packs"]["characters"][0]["path"]
    character_payload = json.loads(character_path.read_text())
    stored = character_payload["manifest"]

    assert stored["schema_version"] == 2
    assert stored["visual_invariants"]["silhouette"].startswith("Broad rounded")
    assert stored["voice_direction"]
    assert stored["tts"]["enabled"] is False


def test_lock_run_leaves_no_baseline_or_export_after_v1_rejection(baseline_setup):
    packs = baseline_setup["pack_service"]
    candidates = baseline_setup["candidate_service"]
    baselines = baseline_setup["baseline_service"]
    database = baseline_setup["database"]
    export_root = baselines.export_root
    asset = baseline_setup["source_assets"][0]
    hero = baseline_setup["source_assets"][3]

    bot1 = packs.create_pack("character", "Legacy BOT1")
    bot2 = packs.create_pack("character", "Legacy BOT2")
    scene = packs.create_pack("scene", "Legacy Studio")
    bot1_version = packs.create_version(bot1.id, character_manifest_v1([asset.id]))
    bot2_version = packs.create_version(bot2.id, character_manifest_v1([asset.id]))
    scene_version = packs.create_version(scene.id, scene_manifest_v2([asset.id]))
    candidate = candidates.create(
        character_versions={
            "BOT1": (bot1_version.pack_id, bot1_version.version),
            "BOT2": (bot2_version.pack_id, bot2_version.version),
        },
        scene_pack_id=scene_version.pack_id,
        scene_version=scene_version.version,
        hero_asset_id=hero.id,
    )
    candidate = candidates.approve(
        candidate.id, canonical=True, review_note="legacy packs"
    )

    with database.connect() as connection:
        baseline_count_before = connection.execute(
            "SELECT COUNT(*) FROM baselines"
        ).fetchone()[0]
    export_entries_before = set(export_root.iterdir()) if export_root.exists() else set()

    with pytest.raises(ValidationError, match="schema_version|flight"):
        baselines.lock_run(candidate.cast_key)

    with database.connect() as connection:
        baseline_count_after = connection.execute(
            "SELECT COUNT(*) FROM baselines"
        ).fetchone()[0]
    export_entries_after = set(export_root.iterdir()) if export_root.exists() else set()

    assert baseline_count_after == baseline_count_before
    assert export_entries_after == export_entries_before
    assert not any(path.name.startswith(".tmp-baseline_") for path in export_entries_after)
    assert not any(path.name.startswith("baseline_") for path in export_entries_after - export_entries_before)
