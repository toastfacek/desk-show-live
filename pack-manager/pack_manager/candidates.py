import hashlib
import json
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .assets import AssetStore
from .db import Database
from .errors import ConflictError, ValidationError
from .packs import PackService


_ALLOWED_VARIANT_CHANGES = {"scene", "palette", "accessories"}
_REQUIRED_CHARACTER_SLOTS = {"BOT1", "BOT2"}


@dataclass(frozen=True)
class CharacterVersion:
    slot: str
    pack_id: str
    version: int


@dataclass(frozen=True, init=False)
class Candidate:
    id: str
    cast_key: str
    scene_pack_id: str
    scene_version: int
    hero_asset_id: str
    canonical_candidate_id: str | None
    theme: str | None
    status: str
    review_note: str | None
    created_at: str
    reviewed_at: str | None
    _character_versions_json: str = field(repr=False)
    _changes_json: str | None = field(repr=False)

    def __init__(
        self,
        *,
        id: str,
        cast_key: str,
        character_versions: tuple[CharacterVersion, ...],
        scene_pack_id: str,
        scene_version: int,
        hero_asset_id: str,
        canonical_candidate_id: str | None,
        theme: str | None,
        changes: dict | None,
        status: str,
        review_note: str | None,
        created_at: str,
        reviewed_at: str | None,
    ):
        for name, value in (
            ("id", id),
            ("cast_key", cast_key),
            ("scene_pack_id", scene_pack_id),
            ("scene_version", scene_version),
            ("hero_asset_id", hero_asset_id),
            ("canonical_candidate_id", canonical_candidate_id),
            ("theme", theme),
            ("status", status),
            ("review_note", review_note),
            ("created_at", created_at),
            ("reviewed_at", reviewed_at),
        ):
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "_character_versions_json",
            _serialize_character_versions(character_versions),
        )
        object.__setattr__(
            self,
            "_changes_json",
            _serialize_json(changes, "changes") if changes is not None else None,
        )

    @property
    def character_versions(self) -> tuple[CharacterVersion, ...]:
        return _deserialize_character_versions(self._character_versions_json)

    @property
    def changes(self) -> dict | None:
        return json.loads(self._changes_json) if self._changes_json is not None else None


@dataclass(frozen=True)
class CandidateResolution:
    candidate: Candidate
    fallback_reason: str | None


class CandidateService:
    def __init__(
        self,
        database: Database,
        asset_store: AssetStore,
        pack_service: PackService,
    ):
        self.database = database
        self.asset_store = asset_store
        self.pack_service = pack_service

    def create(
        self,
        *,
        character_versions: Mapping[str, tuple[str, int]],
        scene_pack_id: str,
        scene_version: int,
        hero_asset_id: str,
    ) -> Candidate:
        versions = self._validate_character_versions(character_versions)
        self._validate_pack_version(scene_pack_id, scene_version, "scene")
        self._validate_hero(hero_asset_id)
        cast_key = self._cast_key(
            versions,
            scene_pack_id=scene_pack_id,
            scene_version=scene_version,
        )
        candidate = Candidate(
            id=f"candidate_{uuid.uuid4().hex}",
            cast_key=cast_key,
            character_versions=versions,
            scene_pack_id=scene_pack_id,
            scene_version=scene_version,
            hero_asset_id=hero_asset_id,
            canonical_candidate_id=None,
            theme=None,
            changes=None,
            status="draft",
            review_note=None,
            created_at=self._now(),
            reviewed_at=None,
        )
        self._insert(candidate)
        return candidate

    def create_variant(
        self,
        *,
        canonical_candidate_id: str,
        hero_asset_id: str,
        theme: str,
        changes: dict,
        scene_pack_id: str | None = None,
        scene_version: int | None = None,
    ) -> Candidate:
        self._validate_hero(hero_asset_id)
        self._validate_theme(theme)
        stored_changes = self._validate_variant_changes(changes)
        if (scene_pack_id is None) != (scene_version is None):
            raise ValidationError(
                "scene_pack_id and scene_version must be provided together"
            )
        if scene_pack_id is not None:
            self._validate_pack_version(scene_pack_id, scene_version, "scene")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            canonical = self._from_row(
                self._require_row(connection, canonical_candidate_id)
            )
            if (
                canonical.status != "approved"
                or canonical.canonical_candidate_id is not None
            ):
                raise ValidationError(
                    "variant requires an approved canonical candidate"
                )
            current = connection.execute(
                """
                SELECT candidate_id
                FROM canonical_candidates
                WHERE cast_key = ?
                """,
                (canonical.cast_key,),
            ).fetchone()
            if current is None or current["candidate_id"] != canonical.id:
                raise ValidationError(
                    "variant requires the current canonical candidate"
                )
            candidate = Candidate(
                id=f"candidate_{uuid.uuid4().hex}",
                cast_key=canonical.cast_key,
                character_versions=canonical.character_versions,
                scene_pack_id=scene_pack_id or canonical.scene_pack_id,
                scene_version=(
                    scene_version
                    if scene_version is not None
                    else canonical.scene_version
                ),
                hero_asset_id=hero_asset_id,
                canonical_candidate_id=canonical.id,
                theme=theme,
                changes=stored_changes,
                status="draft",
                review_note=None,
                created_at=self._now(),
                reviewed_at=None,
            )
            self._insert_with_connection(connection, candidate)
        return candidate

    def approve(
        self,
        candidate_id: str,
        *,
        canonical: bool,
        review_note: str,
        invariants_verified: bool = False,
    ) -> Candidate:
        self._validate_review_note(review_note)
        reviewed_at = self._now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._require_row(connection, candidate_id)
            candidate = self._from_row(row)
            if candidate.status != "draft":
                raise ConflictError("candidate is not draft")
            if canonical and candidate.canonical_candidate_id is not None:
                raise ConflictError("a variant cannot become canonical")
            if candidate.canonical_candidate_id is not None:
                self._validate_variant_changes(candidate.changes)
                if invariants_verified is not True:
                    raise ValidationError(
                        "invariants_verified must be true for a variant"
                    )
                current = connection.execute(
                    """
                    SELECT candidate_id
                    FROM canonical_candidates
                    WHERE cast_key = ?
                    """,
                    (candidate.cast_key,),
                ).fetchone()
                if (
                    current is None
                    or current["candidate_id"]
                    != candidate.canonical_candidate_id
                ):
                    raise ConflictError(
                        "variant has stale canonical lineage"
                    )
            connection.execute(
                """
                UPDATE candidates
                SET status = 'approved', review_note = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (review_note, reviewed_at, candidate_id),
            )
            if canonical:
                connection.execute(
                    """
                    INSERT INTO canonical_candidates
                        (cast_key, candidate_id, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cast_key) DO UPDATE SET
                        candidate_id = excluded.candidate_id,
                        updated_at = excluded.updated_at
                    """,
                    (candidate.cast_key, candidate_id, reviewed_at),
                )
            row = self._require_row(connection, candidate_id)
        return self._from_row(row)

    def set_canonical(self, candidate_id: str) -> Candidate:
        updated_at = self._now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            candidate = self._from_row(
                self._require_row(connection, candidate_id)
            )
            if (
                candidate.status != "approved"
                or candidate.canonical_candidate_id is not None
            ):
                raise ConflictError(
                    "canonical candidate must be an approved root"
                )
            connection.execute(
                """
                INSERT INTO canonical_candidates
                    (cast_key, candidate_id, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cast_key) DO UPDATE SET
                    candidate_id = excluded.candidate_id,
                    updated_at = excluded.updated_at
                """,
                (candidate.cast_key, candidate.id, updated_at),
            )
        return candidate

    def reject(self, candidate_id: str, *, review_note: str) -> Candidate:
        self._validate_review_note(review_note)
        reviewed_at = self._now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._require_row(connection, candidate_id)
            if row["status"] != "draft":
                raise ConflictError("candidate is not draft")
            connection.execute(
                """
                UPDATE candidates
                SET status = 'rejected', review_note = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (review_note, reviewed_at, candidate_id),
            )
            row = self._require_row(connection, candidate_id)
        return self._from_row(row)

    def resolve(
        self, cast_key: str, requested_candidate_id: str | None = None
    ) -> CandidateResolution:
        with self.database.connect() as connection:
            canonical_row = connection.execute(
                """
                SELECT candidates.*
                FROM canonical_candidates
                JOIN candidates
                    ON candidates.id = canonical_candidates.candidate_id
                WHERE canonical_candidates.cast_key = ?
                """,
                (cast_key,),
            ).fetchone()
            if canonical_row is None:
                raise KeyError(cast_key)
            canonical = self._from_row(canonical_row)
            if requested_candidate_id is None or requested_candidate_id == canonical.id:
                return CandidateResolution(canonical, None)

            requested_row = connection.execute(
                "SELECT * FROM candidates WHERE id = ?",
                (requested_candidate_id,),
            ).fetchone()

        if requested_row is None:
            return CandidateResolution(
                canonical, "requested candidate does not exist"
            )
        requested = self._from_row(requested_row)
        if requested.status != "approved":
            return CandidateResolution(
                canonical, "requested candidate is not approved"
            )
        if requested.cast_key != cast_key:
            return CandidateResolution(
                canonical, "requested candidate has different cast key"
            )
        if requested.canonical_candidate_id != canonical.id:
            return CandidateResolution(
                canonical, "requested candidate is not a variant of canonical"
            )
        return CandidateResolution(requested, None)

    def get(self, candidate_id: str) -> Candidate:
        return self._get(candidate_id)

    def list_candidates(self) -> list[Candidate]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM candidates ORDER BY created_at, rowid"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def current_canonical_ids(self) -> set[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT candidate_id FROM canonical_candidates"
            ).fetchall()
        return {row["candidate_id"] for row in rows}

    def is_current_canonical(self, candidate_id: str) -> bool:
        # Missing candidates remain a not-found error rather than silently false.
        self.get(candidate_id)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM canonical_candidates
                WHERE candidate_id = ?
                """,
                (candidate_id,),
            ).fetchone()
        return row is not None

    def _validate_character_versions(
        self, character_versions: Mapping[str, tuple[str, int]]
    ) -> tuple[CharacterVersion, ...]:
        if not isinstance(character_versions, Mapping) or not character_versions:
            raise ValidationError("character_versions must be a non-empty mapping")
        if set(character_versions) != _REQUIRED_CHARACTER_SLOTS:
            raise ValidationError(
                "character_versions must contain exactly BOT1 and BOT2"
            )
        versions = []
        for slot in ("BOT1", "BOT2"):
            reference = character_versions[slot]
            if not isinstance(slot, str) or not slot.strip():
                raise ValidationError("character slot must be a non-empty string")
            if (
                not isinstance(reference, (tuple, list))
                or len(reference) != 2
                or not isinstance(reference[0], str)
            ):
                raise ValidationError(
                    f"character version for {slot} must be (pack_id, version)"
                )
            pack_id, version = reference
            self._validate_pack_version(pack_id, version, "character")
            versions.append(CharacterVersion(slot, pack_id, version))
        return tuple(versions)

    def _validate_pack_version(
        self, pack_id: str, version: int, expected_kind: str
    ) -> None:
        if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
            raise ValidationError(f"{expected_kind} version must be a positive integer")
        try:
            self.pack_service.get_version(pack_id, version)
        except KeyError as error:
            raise ValidationError(
                f"{expected_kind} version does not exist: {pack_id}@{version}"
            ) from error
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT kind FROM packs WHERE id = ?", (pack_id,)
            ).fetchone()
        if row is None or row["kind"] != expected_kind:
            raise ValidationError(
                f"{pack_id}@{version} is not a {expected_kind} version"
            )

    def _validate_hero(self, hero_asset_id: str) -> None:
        try:
            self.asset_store.get(hero_asset_id)
        except KeyError as error:
            raise ValidationError(
                f"hero asset does not exist: {hero_asset_id}"
            ) from error

    @staticmethod
    def _validate_theme(theme: str) -> None:
        if not isinstance(theme, str) or not theme.strip():
            raise ValidationError("theme must be a non-empty string")

    @staticmethod
    def _validate_review_note(review_note: str) -> None:
        if not isinstance(review_note, str) or not review_note.strip():
            raise ValidationError("review_note must be a non-empty string")

    @staticmethod
    def _validate_variant_changes(changes: dict) -> dict:
        if not isinstance(changes, dict) or not changes:
            raise ValidationError("variant changes must be a non-empty object")
        unsupported = set(changes) - _ALLOWED_VARIANT_CHANGES
        if unsupported:
            raise ValidationError(
                "variant changes may contain only scene, palette, and accessories"
            )
        if "scene" in changes and not isinstance(changes["scene"], dict):
            raise ValidationError("variant scene changes must be an object")
        if "palette" in changes and not PackService._is_meaningful_descriptor(
            changes["palette"]
        ):
            raise ValidationError(
                "variant palette must be a meaningful color descriptor"
            )
        if "accessories" in changes:
            accessories = changes["accessories"]
            if (
                not isinstance(accessories, dict)
                or not accessories
                or not set(accessories).issubset(_REQUIRED_CHARACTER_SLOTS)
                or any(
                    not isinstance(items, list)
                    or any(
                        not isinstance(item, str) or not item.strip()
                        for item in items
                    )
                    for items in accessories.values()
                )
            ):
                raise ValidationError(
                    "variant accessories must be an object keyed only by "
                    "BOT1/BOT2 with lists of non-empty strings"
                )
        serialized = _serialize_json(changes, "changes")
        return json.loads(serialized)

    @staticmethod
    def _cast_key(
        character_versions: tuple[CharacterVersion, ...],
        *,
        scene_pack_id: str,
        scene_version: int,
    ) -> str:
        identity = {
            "characters": [
                [item.slot, item.pack_id, item.version]
                for item in character_versions
            ],
            "scene": [scene_pack_id, scene_version],
        }
        encoded = json.dumps(
            identity, sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _insert(self, candidate: Candidate) -> None:
        with self.database.connect() as connection:
            self._insert_with_connection(connection, candidate)

    @staticmethod
    def _insert_with_connection(
        connection: sqlite3.Connection, candidate: Candidate
    ) -> None:
        connection.execute(
            """
            INSERT INTO candidates (
                id, cast_key, character_versions, scene_pack_id,
                scene_version, hero_asset_id, canonical_candidate_id,
                theme, changes, status, review_note, created_at, reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.id,
                candidate.cast_key,
                candidate._character_versions_json,
                candidate.scene_pack_id,
                candidate.scene_version,
                candidate.hero_asset_id,
                candidate.canonical_candidate_id,
                candidate.theme,
                candidate._changes_json,
                candidate.status,
                candidate.review_note,
                candidate.created_at,
                candidate.reviewed_at,
            ),
        )

    def _get(self, candidate_id: str) -> Candidate:
        with self.database.connect() as connection:
            row = self._require_row(connection, candidate_id)
        return self._from_row(row)

    @staticmethod
    def _require_row(
        connection: sqlite3.Connection, candidate_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        return row

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Candidate:
        return Candidate(
            id=row["id"],
            cast_key=row["cast_key"],
            character_versions=_deserialize_character_versions(
                row["character_versions"]
            ),
            scene_pack_id=row["scene_pack_id"],
            scene_version=row["scene_version"],
            hero_asset_id=row["hero_asset_id"],
            canonical_candidate_id=row["canonical_candidate_id"],
            theme=row["theme"],
            changes=json.loads(row["changes"]) if row["changes"] else None,
            status=row["status"],
            review_note=row["review_note"],
            created_at=row["created_at"],
            reviewed_at=row["reviewed_at"],
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _serialize_character_versions(
    character_versions: tuple[CharacterVersion, ...],
) -> str:
    return json.dumps(
        [
            {
                "slot": item.slot,
                "pack_id": item.pack_id,
                "version": item.version,
            }
            for item in character_versions
        ],
        sort_keys=True,
        separators=(",", ":"),
    )


def _deserialize_character_versions(value: str) -> tuple[CharacterVersion, ...]:
    return tuple(CharacterVersion(**item) for item in json.loads(value))


def _serialize_json(value: object, field_name: str) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{field_name} must be JSON serializable") from error
