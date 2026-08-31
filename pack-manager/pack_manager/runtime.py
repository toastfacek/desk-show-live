import json
from pathlib import Path

from .assets import AssetStore
from .baselines import BaselineService, LoadedBaseline
from .candidates import CandidateService
from .db import Database
from .errors import IntegrityError, ValidationError
from .packs import PackService

_REQUIRED_CHARACTER_SLOTS = frozenset({"BOT1", "BOT2"})


def _baseline_service(data_dir: Path) -> BaselineService:
    data_dir = Path(data_dir)
    database = Database(data_dir / "manager.sqlite3")
    database.initialize()
    assets = AssetStore(data_dir, database)
    packs = PackService(database, assets)
    candidates = CandidateService(database, assets, packs)
    return BaselineService(database, assets, packs, candidates)


def load_locked_baseline(data_dir: Path, baseline_id: str) -> LoadedBaseline:
    service = _baseline_service(data_dir)
    loaded = service.load(baseline_id)
    _validate_flight_ready_export(loaded)
    return loaded


def _validate_flight_ready_export(loaded: LoadedBaseline) -> None:
    manifest = loaded.manifest
    characters = manifest.get("packs", {}).get("characters")
    if not isinstance(characters, list):
        raise IntegrityError("invalid character pack list")

    slots = {record.get("slot") for record in characters}
    if slots != _REQUIRED_CHARACTER_SLOTS:
        raise ValidationError(
            "baseline requires exact character slots BOT1 and BOT2"
        )

    export_dir = loaded.manifest_path.parent
    for pack_path in loaded.pack_paths:
        payload = json.loads(pack_path.read_text(encoding="utf-8"))
        inner = payload.get("manifest")
        if not isinstance(inner, dict):
            raise IntegrityError("invalid exported pack manifest")
        kind = payload.get("kind")
        if kind not in {"character", "scene"}:
            raise IntegrityError("invalid exported pack kind")
        PackService.validate_flight_ready(kind, inner)
