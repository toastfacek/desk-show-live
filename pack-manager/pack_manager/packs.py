import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .assets import AssetStore
from .db import Database
from .errors import ValidationError


SCHEMA_VERSION_V1 = 1
SCHEMA_VERSION_V2 = 2
_PACK_KINDS = {"character", "scene"}
_LOCKED_TRAITS = {"silhouette", "eye_design", "proportions"}
_VISUAL_DESCRIPTORS = ("silhouette", "eye_design", "proportions")
_TTS_RESERVED_FIELDS = (
    "enabled",
    "provider",
    "voice_id",
    "speed",
    "pitch",
    "pronunciations",
    "max_duration_s",
    "license",
)
_TTS_LICENSE_FIELDS = (
    "broadcast_rights_confirmed",
    "soundalike_or_cloned_person",
    "notes",
)
_FORBIDDEN_TTS_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "token",
        "credential",
        "credentials",
        "access_key",
        "access_token",
    }
)


@dataclass(frozen=True)
class Pack:
    id: str
    kind: str
    name: str
    created_at: str


@dataclass(frozen=True, init=False)
class PackVersion:
    pack_id: str
    version: int
    created_at: str
    _manifest_json: str = field(repr=False)

    def __init__(
        self, pack_id: str, version: int, manifest: dict, created_at: str
    ):
        object.__setattr__(self, "pack_id", pack_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(
            self,
            "_manifest_json",
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        )

    @property
    def manifest(self) -> dict:
        """Return an independent copy of this version's manifest."""
        return json.loads(self._manifest_json)


class PackService:
    def __init__(self, database: Database, asset_store: AssetStore):
        self.database = database
        self.asset_store = asset_store

    def create_pack(self, kind: str, name: str) -> Pack:
        self._validate_kind(kind)
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("pack name must be a non-empty string")
        name = name.strip()
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

    def list_versions(self, pack_id: str) -> list[PackVersion]:
        with self.database.connect() as connection:
            pack = connection.execute(
                "SELECT 1 FROM packs WHERE id = ?", (pack_id,)
            ).fetchone()
            if pack is None:
                raise KeyError(pack_id)
            rows = connection.execute(
                """
                SELECT pack_id, version, manifest, created_at
                FROM pack_versions
                WHERE pack_id = ?
                ORDER BY version
                """,
                (pack_id,),
            ).fetchall()
        return [self._version_from_row(row) for row in rows]

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

    @staticmethod
    def schema_version(manifest: dict) -> int:
        has_explicit = "schema_version" in manifest
        value = manifest.get("schema_version", SCHEMA_VERSION_V1)
        if value == SCHEMA_VERSION_V1:
            if has_explicit:
                return SCHEMA_VERSION_V1
            if PackService._manifest_has_v2_markers(manifest):
                raise ValidationError(
                    "schema_version is required when using flight-ready fields"
                )
            return SCHEMA_VERSION_V1
        if value == SCHEMA_VERSION_V2:
            return SCHEMA_VERSION_V2
        raise ValidationError("schema_version must be 1 or 2")

    @staticmethod
    def _manifest_has_v2_markers(manifest: dict) -> bool:
        if "tts" in manifest:
            return True
        visual_invariants = manifest.get("visual_invariants")
        if not isinstance(visual_invariants, dict):
            return False
        return any(
            descriptor in visual_invariants for descriptor in _VISUAL_DESCRIPTORS
        )

    @staticmethod
    def validate_flight_ready(kind: str, manifest: dict) -> None:
        if kind not in _PACK_KINDS:
            raise ValidationError("pack kind must be character or scene")
        if PackService.schema_version(manifest) != SCHEMA_VERSION_V2:
            raise ValidationError(
                "flight-ready packs require schema_version 2"
            )
        if kind == "character":
            PackService._validate_character_manifest(manifest)
        else:
            PackService._validate_scene_manifest(manifest)

    def _validate_manifest(self, kind: str, manifest: dict) -> None:
        if not isinstance(manifest, dict):
            raise ValidationError("manifest must be an object")
        schema_version = PackService.schema_version(manifest)
        if kind == "character":
            self._validate_character_manifest(manifest, schema_version)
        else:
            self._validate_scene_manifest(manifest, schema_version)
        self._validate_assets(manifest["asset_ids"])

    @staticmethod
    def _validate_character_manifest(
        manifest: dict, schema_version: int = SCHEMA_VERSION_V1
    ) -> None:
        if schema_version == SCHEMA_VERSION_V2:
            PackService._require_fields(manifest, ("schema_version", "tts"))
            if manifest["schema_version"] != SCHEMA_VERSION_V2:
                raise ValidationError("schema_version must be 2")
            PackService._validate_tts_block(manifest["tts"])
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
        if schema_version == SCHEMA_VERSION_V2:
            for descriptor in _VISUAL_DESCRIPTORS:
                PackService._require_non_empty_string(
                    visual_invariants.get(descriptor),
                    f"visual_invariants.{descriptor}",
                )
        PackService._require_fields(
            manifest, ("persona", "writer_rules", "voice_direction", "asset_ids")
        )
        PackService._require_non_empty_string(manifest["persona"], "persona")
        if not isinstance(manifest["writer_rules"], list):
            raise ValidationError("writer_rules must be a list")
        PackService._require_non_empty_string(
            manifest["voice_direction"], "voice_direction"
        )

    @staticmethod
    def _validate_scene_manifest(
        manifest: dict, schema_version: int = SCHEMA_VERSION_V1
    ) -> None:
        if schema_version == SCHEMA_VERSION_V2:
            PackService._require_fields(manifest, ("schema_version",))
            if manifest["schema_version"] != SCHEMA_VERSION_V2:
                raise ValidationError("schema_version must be 2")
        frame = manifest.get("frame")
        if not isinstance(frame, dict):
            raise ValidationError("scene manifest requires frame")
        PackService._require_fields(frame, ("w", "h", "fps"), prefix="frame.")
        PackService._require_fields(
            manifest,
            ("set", "palette", "lighting", "reanchor_every", "asset_ids"),
        )
        for field in ("w", "h", "fps"):
            PackService._require_positive_integer(frame[field], f"frame.{field}")
        PackService._require_positive_integer(
            manifest["reanchor_every"], "reanchor_every"
        )
        PackService._require_non_empty_string(manifest["set"], "set")
        PackService._require_meaningful_palette(manifest["palette"])
        PackService._require_non_empty_string(manifest["lighting"], "lighting")

    @staticmethod
    def _validate_tts_block(tts: object) -> None:
        if not isinstance(tts, dict):
            raise ValidationError("tts must be an object")
        forbidden = _FORBIDDEN_TTS_KEYS.intersection(tts)
        if forbidden:
            raise ValidationError(
                "tts must not contain provider credentials: "
                + ", ".join(sorted(forbidden))
            )
        PackService._require_fields(tts, _TTS_RESERVED_FIELDS)
        if not isinstance(tts["enabled"], bool):
            raise ValidationError("tts.enabled must be a boolean")
        if not isinstance(tts["pronunciations"], list):
            raise ValidationError("tts.pronunciations must be a list")
        license_block = tts.get("license")
        if not isinstance(license_block, dict):
            raise ValidationError("tts.license must be an object")
        PackService._require_fields(
            license_block, _TTS_LICENSE_FIELDS, prefix="tts.license."
        )
        if not isinstance(license_block["broadcast_rights_confirmed"], bool):
            raise ValidationError(
                "tts.license.broadcast_rights_confirmed must be a boolean"
            )
        if not isinstance(license_block["soundalike_or_cloned_person"], bool):
            raise ValidationError(
                "tts.license.soundalike_or_cloned_person must be a boolean"
            )
        if not isinstance(license_block["notes"], str):
            raise ValidationError("tts.license.notes must be a string")

        if not tts["enabled"]:
            return

        PackService._require_non_empty_string(tts["provider"], "tts.provider")
        PackService._require_non_empty_string(tts["voice_id"], "tts.voice_id")
        if not license_block["broadcast_rights_confirmed"]:
            raise ValidationError(
                "tts.license.broadcast_rights_confirmed must be true when "
                "tts is enabled"
            )
        if license_block["soundalike_or_cloned_person"]:
            raise ValidationError(
                "tts.license.soundalike_or_cloned_person must be false"
            )
        for field in ("speed", "pitch", "max_duration_s"):
            value = tts[field]
            if value is not None and not isinstance(value, (int, float)):
                raise ValidationError(f"tts.{field} must be a number or null")

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
    def _require_non_empty_string(value: object, field: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{field} must be a non-empty string")

    @staticmethod
    def _require_positive_integer(value: object, field: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValidationError(f"{field} must be a positive integer")

    @staticmethod
    def _require_meaningful_palette(value: object) -> None:
        if not PackService._is_meaningful_descriptor(value):
            raise ValidationError("palette must be a meaningful value")

    @staticmethod
    def _is_meaningful_descriptor(value: object) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return bool(value) and all(
                PackService._is_meaningful_descriptor(item) for item in value
            )
        if isinstance(value, dict):
            return bool(value) and all(
                isinstance(key, str)
                and bool(key.strip())
                and PackService._is_meaningful_descriptor(item)
                for key, item in value.items()
            )
        return False

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
