import json
import re
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
_CHARACTER_V2_KEYS = frozenset(
    {
        "schema_version",
        "visual_invariants",
        "persona",
        "writer_rules",
        "voice_direction",
        "tts",
        "asset_ids",
    }
)
_VISUAL_INVARIANTS_V2_KEYS = frozenset(
    {"locked_traits", "silhouette", "eye_design", "proportions"}
)
_SCENE_V2_KEYS = frozenset(
    {
        "schema_version",
        "set",
        "palette",
        "lighting",
        "frame",
        "reanchor_every",
        "asset_ids",
    }
)
_FRAME_V2_KEYS = frozenset({"w", "h", "fps"})
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
_CREDENTIAL_FRAGMENTS = (
    "apikey",
    "accesskey",
    "awsaccesskeyid",
    "privatekey",
    "secretkey",
    "clientsecret",
    "secret",
    "token",
    "password",
    "authorization",
    "credential",
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
        if not has_explicit:
            if PackService._manifest_has_v2_markers(manifest):
                raise ValidationError(
                    "schema_version is required when using flight-ready fields"
                )
            return SCHEMA_VERSION_V1
        return PackService._parse_schema_version(manifest["schema_version"])

    @staticmethod
    def is_flight_ready(kind: str, manifest: dict) -> bool:
        try:
            PackService.validate_flight_ready(kind, manifest)
        except ValidationError:
            return False
        return True

    @staticmethod
    def validate_flight_ready(kind: str, manifest: dict) -> None:
        if kind not in _PACK_KINDS:
            raise ValidationError("pack kind must be character or scene")
        if not isinstance(manifest, dict):
            raise ValidationError("manifest must be an object")
        if PackService.schema_version(manifest) != SCHEMA_VERSION_V2:
            raise ValidationError(
                "flight-ready packs require schema_version 2"
            )
        PackService._reject_credentials_recursive(manifest)
        if kind == "character":
            PackService._validate_character_manifest(
                manifest, SCHEMA_VERSION_V2
            )
        else:
            PackService._validate_scene_manifest(manifest, SCHEMA_VERSION_V2)

    def _validate_manifest(self, kind: str, manifest: dict) -> None:
        if not isinstance(manifest, dict):
            raise ValidationError("manifest must be an object")
        PackService._reject_credentials_recursive(manifest)
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
            PackService._validate_closed_keys(
                manifest, _CHARACTER_V2_KEYS, "manifest"
            )
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
            if not isinstance(visual_invariants, dict):
                raise ValidationError("visual_invariants must be an object")
            PackService._validate_closed_keys(
                visual_invariants,
                _VISUAL_INVARIANTS_V2_KEYS,
                "visual_invariants",
            )
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
            PackService._validate_closed_keys(
                manifest, _SCENE_V2_KEYS, "manifest"
            )
            PackService._require_fields(manifest, ("schema_version",))
            if manifest["schema_version"] != SCHEMA_VERSION_V2:
                raise ValidationError("schema_version must be 2")
        frame = manifest.get("frame")
        if not isinstance(frame, dict):
            raise ValidationError("scene manifest requires frame")
        if schema_version == SCHEMA_VERSION_V2:
            PackService._validate_closed_keys(frame, _FRAME_V2_KEYS, "frame")
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
        PackService._reject_credentials_recursive(tts, path="tts")
        PackService._validate_closed_keys(tts, frozenset(_TTS_RESERVED_FIELDS), "tts")
        PackService._require_fields(tts, _TTS_RESERVED_FIELDS)
        if not isinstance(tts["enabled"], bool):
            raise ValidationError("tts.enabled must be a boolean")
        if tts["enabled"]:
            raise ValidationError(
                "tts.enabled must be false for the current flight"
            )
        if tts["provider"] is not None:
            raise ValidationError("tts.provider must be null while disabled")
        if tts["voice_id"] is not None:
            raise ValidationError("tts.voice_id must be null while disabled")
        if tts["speed"] is not None:
            raise ValidationError("tts.speed must be null while disabled")
        if tts["pitch"] is not None:
            raise ValidationError("tts.pitch must be null while disabled")
        if tts["max_duration_s"] is not None:
            raise ValidationError("tts.max_duration_s must be null while disabled")
        if tts["pronunciations"] != []:
            raise ValidationError("tts.pronunciations must be an empty list")
        license_block = tts.get("license")
        if not isinstance(license_block, dict):
            raise ValidationError("tts.license must be an object")
        PackService._validate_closed_keys(
            license_block, frozenset(_TTS_LICENSE_FIELDS), "tts.license"
        )
        PackService._require_fields(
            license_block, _TTS_LICENSE_FIELDS, prefix="tts.license."
        )
        if license_block["broadcast_rights_confirmed"] is not False:
            raise ValidationError(
                "tts.license.broadcast_rights_confirmed must be false while disabled"
            )
        if license_block["soundalike_or_cloned_person"] is not False:
            raise ValidationError(
                "tts.license.soundalike_or_cloned_person must be false while disabled"
            )
        if license_block["notes"] != "":
            raise ValidationError("tts.license.notes must be an empty string")

    @staticmethod
    def _parse_schema_version(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError("schema_version must be an integer")
        if value == SCHEMA_VERSION_V1:
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
    def _normalize_key(key: object) -> str:
        if not isinstance(key, str):
            return ""
        return re.sub(r"[^a-z0-9]", "", key.lower())

    @staticmethod
    def _is_credential_key(key: object) -> bool:
        normalized = PackService._normalize_key(key)
        if not normalized:
            return False
        return any(fragment in normalized for fragment in _CREDENTIAL_FRAGMENTS)

    @staticmethod
    def _reject_credentials_recursive(value: object, *, path: str = "manifest") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if PackService._is_credential_key(key):
                    raise ValidationError(
                        f"{path}.{key} must not contain credential metadata"
                    )
                PackService._reject_credentials_recursive(
                    item, path=f"{path}.{key}"
                )
        elif isinstance(value, list):
            for index, item in enumerate(value):
                PackService._reject_credentials_recursive(
                    item, path=f"{path}[{index}]"
                )

    @staticmethod
    def _validate_closed_keys(
        value: dict, allowed: frozenset[str], path: str
    ) -> None:
        extra = set(value) - allowed
        if extra:
            raise ValidationError(
                f"{path} contains unsupported fields: {', '.join(sorted(extra))}"
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
