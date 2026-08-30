import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .assets import AssetStore
from .db import Database
from .errors import ValidationError


_PACK_KINDS = {"character", "scene"}
_LOCKED_TRAITS = {"silhouette", "eye_design", "proportions"}


@dataclass(frozen=True)
class Pack:
    id: str
    kind: str
    name: str
    created_at: str


@dataclass(frozen=True)
class PackVersion:
    pack_id: str
    version: int
    manifest: dict
    created_at: str


class PackService:
    def __init__(self, database: Database, asset_store: AssetStore):
        self.database = database
        self.asset_store = asset_store

    def create_pack(self, kind: str, name: str) -> Pack:
        self._validate_kind(kind)
        pack = Pack(
            id=f"{kind}_{uuid.uuid4().hex}",
            kind=kind,
            name=name,
            created_at=self._now(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO packs (id, kind, name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (pack.id, pack.kind, pack.name, pack.created_at),
            )
        return pack

    def create_version(self, pack_id: str, manifest: dict) -> PackVersion:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            pack_row = connection.execute(
                "SELECT kind FROM packs WHERE id = ?", (pack_id,)
            ).fetchone()
            if pack_row is None:
                raise KeyError(pack_id)

            self._validate_manifest(pack_row["kind"], manifest)
            stored_manifest = self._serialize_manifest(manifest)
            next_version = connection.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                FROM pack_versions
                WHERE pack_id = ?
                """,
                (pack_id,),
            ).fetchone()[0]
            created_at = self._now()
            connection.execute(
                """
                INSERT INTO pack_versions (pack_id, version, manifest, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (pack_id, next_version, stored_manifest, created_at),
            )

        return PackVersion(
            pack_id=pack_id,
            version=next_version,
            manifest=json.loads(stored_manifest),
            created_at=created_at,
        )

    def get_version(self, pack_id: str, version: int) -> PackVersion:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT pack_id, version, manifest, created_at
                FROM pack_versions
                WHERE pack_id = ? AND version = ?
                """,
                (pack_id, version),
            ).fetchone()
        if row is None:
            raise KeyError((pack_id, version))
        return self._version_from_row(row)

    def list_packs(self, kind: str | None = None) -> list[Pack]:
        if kind is not None:
            self._validate_kind(kind)
        query = "SELECT id, kind, name, created_at FROM packs"
        parameters: tuple[str, ...] = ()
        if kind is not None:
            query += " WHERE kind = ?"
            parameters = (kind,)
        query += " ORDER BY created_at, rowid"

        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._pack_from_row(row) for row in rows]

    def _validate_manifest(self, kind: str, manifest: dict) -> None:
        if not isinstance(manifest, dict):
            raise ValidationError("manifest must be an object")
        if kind == "character":
            self._validate_character_manifest(manifest)
        else:
            self._validate_scene_manifest(manifest)
        self._validate_assets(manifest["asset_ids"])

    @staticmethod
    def _validate_character_manifest(manifest: dict) -> None:
        visual_invariants = manifest.get("visual_invariants")
        locked_traits = (
            visual_invariants.get("locked_traits")
            if isinstance(visual_invariants, dict)
            else None
        )
        if (
            not isinstance(locked_traits, list)
            or len(locked_traits) != len(_LOCKED_TRAITS)
            or not all(isinstance(trait, str) for trait in locked_traits)
            or set(locked_traits) != _LOCKED_TRAITS
        ):
            raise ValidationError(
                "visual_invariants.locked_traits must contain exactly "
                "silhouette, eye_design, and proportions"
            )
        PackService._require_fields(
            manifest, ("persona", "writer_rules", "voice_direction", "asset_ids")
        )

    @staticmethod
    def _validate_scene_manifest(manifest: dict) -> None:
        frame = manifest.get("frame")
        if not isinstance(frame, dict):
            raise ValidationError("scene manifest requires frame")
        PackService._require_fields(frame, ("w", "h", "fps"), prefix="frame.")
        PackService._require_fields(
            manifest,
            ("set", "palette", "lighting", "reanchor_every", "asset_ids"),
        )

    def _validate_assets(self, asset_ids: object) -> None:
        if not isinstance(asset_ids, list):
            raise ValidationError("asset_ids must be a list")
        for asset_id in asset_ids:
            if not isinstance(asset_id, str):
                raise ValidationError("asset_ids must contain strings")
            try:
                self.asset_store.get(asset_id)
            except KeyError as error:
                raise ValidationError(f"asset does not exist: {asset_id}") from error

    @staticmethod
    def _require_fields(
        value: dict, fields: tuple[str, ...], *, prefix: str = ""
    ) -> None:
        for field in fields:
            if field not in value:
                raise ValidationError(f"manifest requires {prefix}{field}")

    @staticmethod
    def _serialize_manifest(manifest: dict) -> str:
        try:
            return json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ValidationError("manifest must be JSON serializable") from error

    @staticmethod
    def _pack_from_row(row: sqlite3.Row) -> Pack:
        return Pack(
            id=row["id"],
            kind=row["kind"],
            name=row["name"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _version_from_row(row: sqlite3.Row) -> PackVersion:
        return PackVersion(
            pack_id=row["pack_id"],
            version=row["version"],
            manifest=json.loads(row["manifest"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _validate_kind(kind: str) -> None:
        if kind not in _PACK_KINDS:
            raise ValidationError("pack kind must be character or scene")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
