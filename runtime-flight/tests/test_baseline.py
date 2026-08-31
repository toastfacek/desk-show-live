import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from pack_manager.assets import AssetStore
from pack_manager.baselines import BaselineService
from pack_manager.candidates import CandidateService
from pack_manager.db import Database
from pack_manager.errors import IntegrityError, ValidationError
from pack_manager.packs import PackService
from runtime_flight.baseline import BaselineContext

from conftest import character_manifest_v2, scene_manifest_v2


def make_png_bytes(width: int = 1344, height: int = 768, color: tuple[int, int, int] = (255, 128, 0)) -> bytes:
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_jpeg_bytes(width: int = 1344, height: int = 768) -> bytes:
    image = Image.new("RGB", (width, height), (10, 20, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def register_tampered_baseline(service, locked, *, baseline_id: str, manifest: dict) -> str:
    malicious_dir = service.export_root / baseline_id
    shutil.copytree(locked.manifest_path.parent, malicious_dir)
    manifest_path = malicious_dir / "manifest.json"
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
                baseline_id,
                locked.cast_key,
                locked.candidate_id,
                locked.canonical_candidate_id,
                None,
                str(manifest_path),
                hashlib.sha256(manifest_bytes).hexdigest(),
                locked.created_at,
            ),
        )
    return baseline_id


def tamper_hero_manifest(service, locked, hero_bytes: bytes, *, baseline_id: str) -> str:
    export_dir = locked.manifest_path.parent
    manifest = json.loads(locked.manifest_path.read_text())
    manifest["baseline_id"] = baseline_id
    hero_relative = locked.hero_path.relative_to(export_dir).as_posix()
    digest = hashlib.sha256(hero_bytes).hexdigest()
    for file_record in manifest["files"]:
        if file_record["path"] == hero_relative:
            file_record["sha256"] = digest
    manifest["hero"]["sha256"] = digest
    baseline_id = register_tampered_baseline(service, locked, baseline_id=baseline_id, manifest=manifest)
    hero_path = service.export_root / baseline_id / hero_relative
    hero_path.write_bytes(hero_bytes)
    return baseline_id


@pytest.fixture
def flight_setup(tmp_path):
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
    bot2_asset = asset_store.put_bytes("bot2.png", make_png_bytes(64, 64), "image/png")
    scene_asset = asset_store.put_bytes("studio.png", make_png_bytes(64, 64), "image/png")
    hero = asset_store.put_bytes("hero.png", make_png_bytes(), "image/png")

    bot1 = pack_service.create_pack("character", "BOT1")
    bot2 = pack_service.create_pack("character", "BOT2")
    scene = pack_service.create_pack("scene", "Studio")
    bot1_version = pack_service.create_version(
        bot1.id, character_manifest_v2([bot1_asset.id])
    )
    bot2_version = pack_service.create_version(
        bot2.id, character_manifest_v2([bot2_asset.id])
    )
    scene_version = pack_service.create_version(
        scene.id, scene_manifest_v2([scene_asset.id])
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
        "workspace_root": tmp_path,
    }


def test_baseline_context_loads_verified_export(flight_setup):
    context = BaselineContext.load(flight_setup["data_dir"], flight_setup["locked"].id)

    assert context.baseline_id == flight_setup["locked"].id
    assert context.hero_path == flight_setup["locked"].hero_path
    assert context.hero_sha256 == hashlib.sha256(make_png_bytes()).hexdigest()
    assert context.host_map == {"BOT1": "host_a", "BOT2": "host_b"}
    assert context.display_names == {"BOT1": "BOT1", "BOT2": "BOT2"}
    assert context.reanchor_every == 60
    assert context.frame == {"fps": 30, "h": 1080, "w": 1920}
    assert {character.slot for character in context.characters} == {"BOT1", "BOT2"}
    assert context.scene.manifest["schema_version"] == 2
    for character in context.characters:
        assert character.manifest["schema_version"] == 2
        assert character.manifest["voice_direction"]


def test_baseline_context_rejects_non_png_hero_bytes(flight_setup):
    service = flight_setup["baseline_service"]
    locked = flight_setup["locked"]
    baseline_id = tamper_hero_manifest(
        service,
        locked,
        make_jpeg_bytes(),
        baseline_id="baseline_runtime_jpeg_hero",
    )

    with pytest.raises(ValidationError, match="PNG|hero"):
        BaselineContext.load(flight_setup["data_dir"], baseline_id)


def test_baseline_context_rejects_invalid_png(flight_setup):
    service = flight_setup["baseline_service"]
    locked = flight_setup["locked"]
    baseline_id = tamper_hero_manifest(
        service,
        locked,
        b"not-a-png",
        baseline_id="baseline_runtime_invalid_png",
    )

    with pytest.raises(ValidationError, match="PNG|decode|hero"):
        BaselineContext.load(flight_setup["data_dir"], baseline_id)


@pytest.mark.parametrize("width,height", [(100, 768), (1344, 100), (1920, 1080)])
def test_baseline_context_rejects_non_flight_hero_dimensions(flight_setup, width, height):
    service = flight_setup["baseline_service"]
    locked = flight_setup["locked"]
    baseline_id = tamper_hero_manifest(
        service,
        locked,
        make_png_bytes(width, height),
        baseline_id=f"baseline_runtime_dims_{width}x{height}",
    )

    with pytest.raises(ValidationError, match="1344|768|dimension"):
        BaselineContext.load(flight_setup["data_dir"], baseline_id)


def test_baseline_context_rejects_root_scaffold_hero_path(flight_setup, monkeypatch):
    workspace = flight_setup["workspace_root"]
    scaffold_hero = workspace / "assets" / "hero.png"
    scaffold_hero.parent.mkdir(parents=True, exist_ok=True)
    scaffold_hero.write_bytes(make_png_bytes())

    service = flight_setup["baseline_service"]
    locked = flight_setup["locked"]
    manifest = json.loads(locked.manifest_path.read_text())
    manifest["hero"]["path"] = "../../assets/hero.png"
    manifest_bytes = service._normalized_json(manifest)
    locked.manifest_path.write_bytes(manifest_bytes)

    monkeypatch.chdir(workspace)

    with pytest.raises((ValidationError, Exception), match="scaffold|hero|path escape|hash mismatch"):
        BaselineContext.load(flight_setup["data_dir"], locked.id)


def test_baseline_context_rejects_config_yaml_hero_still_path(flight_setup, monkeypatch):
    workspace = flight_setup["workspace_root"]
    scaffold_hero = workspace / "assets" / "hero.png"
    scaffold_hero.parent.mkdir(parents=True, exist_ok=True)
    scaffold_bytes = make_png_bytes()
    scaffold_hero.write_bytes(scaffold_bytes)
    (workspace / "config.yaml").write_text(
        'identity:\n  hero_still: "assets/hero.png"\n',
        encoding="utf-8",
    )

    service = flight_setup["baseline_service"]
    locked = flight_setup["locked"]
    baseline_id = tamper_hero_manifest(
        service,
        locked,
        scaffold_bytes,
        baseline_id="baseline_runtime_config_hero",
    )

    monkeypatch.chdir(workspace)

    with pytest.raises(ValidationError, match="scaffold|hero_still|root|config"):
        BaselineContext.load(flight_setup["data_dir"], baseline_id)
