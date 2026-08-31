import hashlib
import inspect
import io
import json
import shutil
import tomllib
from pathlib import Path

import pytest
from PIL import Image

from pack_manager.assets import AssetStore
from pack_manager.baselines import BaselineService
from pack_manager.candidates import CandidateService
from pack_manager.db import Database
from pack_manager.errors import IntegrityError, ValidationError
from pack_manager.packs import PackService
from pack_manager.runtime import load_locked_baseline
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


def make_truncated_png_bytes() -> bytes:
    return make_png_bytes()[:200]


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


def test_baseline_context_load_accepts_only_data_dir_and_baseline_id():
    signature = inspect.signature(BaselineContext.load)
    assert tuple(signature.parameters) == ("data_dir", "baseline_id")


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


def test_baseline_context_rejects_truncated_png_idat(flight_setup):
    service = flight_setup["baseline_service"]
    locked = flight_setup["locked"]
    baseline_id = tamper_hero_manifest(
        service,
        locked,
        make_truncated_png_bytes(),
        baseline_id="baseline_runtime_truncated_png",
    )

    with pytest.raises(ValidationError, match="PNG|hero"):
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


def test_baseline_context_rejects_manifest_path_escape(flight_setup):
    service = flight_setup["baseline_service"]
    locked = flight_setup["locked"]
    malicious_id = "baseline_runtime_path_escape"
    export_dir = locked.manifest_path.parent
    manifest = json.loads(locked.manifest_path.read_text())
    manifest["baseline_id"] = malicious_id
    manifest["files"] = [dict(item) for item in manifest["files"]]
    manifest["files"][0]["path"] = "../outside.png"
    malicious_dir = service.export_root / malicious_id
    shutil.copytree(export_dir, malicious_dir)
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

    with pytest.raises(IntegrityError, match="path escape"):
        BaselineContext.load(flight_setup["data_dir"], malicious_id)


def test_baseline_context_nested_mappings_are_immutable(flight_setup):
    context = BaselineContext.load(flight_setup["data_dir"], flight_setup["locked"].id)

    with pytest.raises(TypeError):
        context.host_map["BOT1"] = "host_wrong"
    with pytest.raises(TypeError):
        context.display_names["BOT1"] = "Renamed"
    with pytest.raises(TypeError):
        context.frame["fps"] = 24
    with pytest.raises(TypeError):
        context.characters[0].manifest["schema_version"] = 1
    with pytest.raises(TypeError):
        context.scene.manifest["schema_version"] = 1


def test_baseline_context_does_not_reopen_verified_export_bytes(flight_setup, monkeypatch):
    loaded = load_locked_baseline(flight_setup["data_dir"], flight_setup["locked"].id)
    hero_relative = loaded.manifest["hero"]["path"]
    hero_bytes = loaded.verified_bytes[hero_relative]
    original_read_bytes = Path.read_bytes
    export_root = str(flight_setup["baseline_service"].export_root)

    def counting_read_bytes(self, *args, **kwargs):
        if str(self).startswith(export_root):
            raise AssertionError(f"unexpected export reopen during context build: {self}")
        return original_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    BaselineContext._from_loaded(loaded, hero_bytes)


def test_runtime_flight_bootstrap_installs_local_distributions():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    bootstrap = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap-local.sh"
    metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    dependencies = metadata["project"]["dependencies"]
    bootstrap_text = bootstrap.read_text(encoding="utf-8")

    assert "pyyaml>=6.0.3" in dependencies
    assert "httpx2>=2.12.0" in dependencies
    assert "fal-client>=1.0.1,<2" in dependencies
    assert "pack-manager>=" not in " ".join(dependencies)
    assert "../pack-manager" in bootstrap_text
    assert "../obs-harness" in bootstrap_text

    from pack_manager.runtime import load_locked_baseline

    assert callable(load_locked_baseline)
