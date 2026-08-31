import json
from pathlib import Path

from .assets import AssetStore
from .baselines import BaselineService, LoadedBaseline
from .candidates import CandidateService
from .db import Database
from .errors import IntegrityError, ValidationError
from .packs import PackService

_REQUIRED_CHARACTER_SLOTS = ("BOT1", "BOT2")


def _baseline_service(data_dir: Path, *, maintenance: bool = False) -> BaselineService:
    data_dir = Path(data_dir)
    database_path = data_dir / "manager.sqlite3"
    if not database_path.is_file():
        raise IntegrityError(f"missing manager database: {database_path}")

    database = Database(database_path)
    assets = AssetStore(data_dir, database)
    packs = PackService(database, assets)
    candidates = CandidateService(database, assets, packs)
    return BaselineService(
        database, assets, packs, candidates, maintenance=maintenance
    )


def load_locked_baseline(data_dir: Path, baseline_id: str) -> LoadedBaseline:
    service = _baseline_service(data_dir, maintenance=False)
    loaded = service.load(baseline_id)
    _validate_flight_ready_export(loaded)
    return loaded


def _parse_export_payload(content: bytes) -> dict:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntegrityError("invalid exported pack payload") from error
    if not isinstance(payload, dict):
        raise IntegrityError("invalid exported pack payload")
    return payload


def _validate_flight_ready_export(loaded: LoadedBaseline) -> None:
    manifest = loaded.manifest
    characters = manifest.get("packs", {}).get("characters")
    if not isinstance(characters, list):
        raise IntegrityError("invalid character pack list")
    if len(characters) != 2:
        raise ValidationError("baseline requires exactly two character packs")

    slots: list[str] = []
    for record in characters:
        if not isinstance(record, dict):
            raise IntegrityError("invalid character pack record")
        slot = record.get("slot")
        if not isinstance(slot, str):
            raise ValidationError("baseline requires exact character slots BOT1 and BOT2")
        slots.append(slot)
        relative_path = record.get("path")
        if not isinstance(relative_path, str):
            raise IntegrityError("invalid character pack path")
        try:
            content = loaded.verified_bytes[relative_path]
        except KeyError as error:
            raise IntegrityError("missing verified character export bytes") from error
        payload = _parse_export_payload(content)
        if payload.get("kind") != "character":
            raise IntegrityError("character export kind mismatch")
        inner = payload.get("manifest")
        if not isinstance(inner, dict):
            raise IntegrityError("invalid exported character manifest")
        PackService.validate_flight_ready("character", inner)

    if sorted(slots) != list(_REQUIRED_CHARACTER_SLOTS):
        raise ValidationError("baseline requires exact character slots BOT1 and BOT2")

    scene_record = manifest.get("packs", {}).get("scene")
    if not isinstance(scene_record, dict):
        raise IntegrityError("invalid scene pack metadata")
    scene_path = scene_record.get("path")
    if not isinstance(scene_path, str):
        raise IntegrityError("invalid scene pack path")
    try:
        scene_content = loaded.verified_bytes[scene_path]
    except KeyError as error:
        raise IntegrityError("missing verified scene export bytes") from error
    scene_payload = _parse_export_payload(scene_content)
    if scene_payload.get("kind") != "scene":
        raise IntegrityError("scene export kind mismatch")
    scene_manifest = scene_payload.get("manifest")
    if not isinstance(scene_manifest, dict):
        raise IntegrityError("invalid exported scene manifest")
    PackService.validate_flight_ready("scene", scene_manifest)
