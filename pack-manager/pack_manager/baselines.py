import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .assets import Asset, AssetStore
from .candidates import Candidate, CandidateService
from .db import Database
from .errors import IntegrityError
from .packs import PackService, PackVersion


@dataclass(frozen=True)
class Baseline:
    id: str
    cast_key: str
    candidate_id: str
    canonical_candidate_id: str
    fallback_reason: str | None
    manifest_path: Path
    manifest_sha256: str
    hero_path: Path
    created_at: str


@dataclass(frozen=True)
class LoadedBaseline:
    id: str
    manifest: dict
    manifest_path: Path
    hero_path: Path
    pack_paths: tuple[Path, ...]
    asset_paths: tuple[Path, ...]


class BaselineService:
    def __init__(
        self,
        database: Database,
        asset_store: AssetStore,
        pack_service: PackService,
        candidate_service: CandidateService,
    ):
        self.database = database
        self.asset_store = asset_store
        self.pack_service = pack_service
        self.candidate_service = candidate_service
        self.export_root = (asset_store.data_dir / "exports").resolve()

    def lock_run(
        self, cast_key: str, requested_candidate_id: str | None = None
    ) -> Baseline:
        resolution = self.candidate_service.resolve(
            cast_key, requested_candidate_id=requested_candidate_id
        )
        candidate = resolution.candidate
        canonical_candidate_id = (
            candidate.canonical_candidate_id or candidate.id
        )
        baseline_id = f"baseline_{uuid.uuid4().hex}"
        created_at = self._now()
        temporary_dir = self.export_root / f".tmp-{baseline_id}"
        export_dir = self.export_root / baseline_id
        renamed = False

        self.export_root.mkdir(parents=True, exist_ok=True)
        temporary_dir.mkdir()
        try:
            manifest = self._export(
                temporary_dir=temporary_dir,
                baseline_id=baseline_id,
                candidate=candidate,
                canonical_candidate_id=canonical_candidate_id,
                fallback_reason=resolution.fallback_reason,
                created_at=created_at,
            )
            manifest_bytes = self._normalized_json(manifest)
            temporary_manifest = temporary_dir / "manifest.json"
            self._write_bytes(temporary_manifest, manifest_bytes)
            manifest_sha256 = self._sha256(temporary_manifest)

            temporary_dir.rename(export_dir)
            renamed = True
            manifest_path = export_dir / "manifest.json"
            with self.database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO baselines (
                        id, cast_key, candidate_id, canonical_candidate_id,
                        fallback_reason, manifest_path, manifest_sha256,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        baseline_id,
                        cast_key,
                        candidate.id,
                        canonical_candidate_id,
                        resolution.fallback_reason,
                        str(manifest_path),
                        manifest_sha256,
                        created_at,
                    ),
                )
        except Exception:
            shutil.rmtree(export_dir if renamed else temporary_dir, ignore_errors=True)
            raise

        hero_path = export_dir / manifest["hero"]["path"]
        return Baseline(
            id=baseline_id,
            cast_key=cast_key,
            candidate_id=candidate.id,
            canonical_candidate_id=canonical_candidate_id,
            fallback_reason=resolution.fallback_reason,
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha256,
            hero_path=hero_path,
            created_at=created_at,
        )

    def verify(self, baseline_id: str) -> None:
        self.load(baseline_id)

    def load(self, baseline_id: str) -> LoadedBaseline:
        row = self._get_row(baseline_id)
        export_dir = self.export_root / baseline_id
        manifest_path = Path(row["manifest_path"])
        expected_manifest_path = export_dir / "manifest.json"
        if self._resolved(manifest_path) != self._resolved(expected_manifest_path):
            raise IntegrityError("baseline manifest path escape")

        manifest_bytes = self._read_file(manifest_path)
        if self._digest(manifest_bytes) != row["manifest_sha256"]:
            raise IntegrityError("manifest hash mismatch")
        try:
            manifest = json.loads(manifest_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise IntegrityError("invalid baseline manifest") from error
        if not isinstance(manifest, dict):
            raise IntegrityError("invalid baseline manifest")
        self._verify_identity(manifest, row)

        files = manifest.get("files")
        if not isinstance(files, list):
            raise IntegrityError("invalid baseline file list")
        verified_paths: dict[str, Path] = {}
        for record in files:
            if not isinstance(record, dict):
                raise IntegrityError("invalid baseline file record")
            relative_path = record.get("path")
            expected_hash = record.get("sha256")
            if (
                not isinstance(relative_path, str)
                or not isinstance(expected_hash, str)
                or len(expected_hash) != 64
            ):
                raise IntegrityError("invalid baseline file record")
            if relative_path in verified_paths:
                raise IntegrityError(f"duplicate baseline path: {relative_path}")
            path = self._resolve_export_path(export_dir, relative_path)
            content = self._read_file(path)
            if self._digest(content) != expected_hash:
                raise IntegrityError(f"hash mismatch: {relative_path}")
            verified_paths[relative_path] = path

        hero_relative, pack_relatives, asset_relatives = self._referenced_paths(
            manifest
        )
        referenced = {hero_relative, *pack_relatives, *asset_relatives}
        if referenced != set(verified_paths):
            raise IntegrityError("manifest file references do not match hash records")
        self._verify_export_contents(export_dir, set(verified_paths))

        return LoadedBaseline(
            id=baseline_id,
            manifest=manifest,
            manifest_path=manifest_path,
            hero_path=verified_paths[hero_relative],
            pack_paths=tuple(verified_paths[path] for path in pack_relatives),
            asset_paths=tuple(verified_paths[path] for path in asset_relatives),
        )

    def _export(
        self,
        *,
        temporary_dir: Path,
        baseline_id: str,
        candidate: Candidate,
        canonical_candidate_id: str,
        fallback_reason: str | None,
        created_at: str,
    ) -> dict:
        file_records: list[dict[str, str]] = []
        packs_dir = temporary_dir / "packs"
        assets_dir = temporary_dir / "assets"
        packs_dir.mkdir()
        assets_dir.mkdir()

        hero = self.asset_store.get(candidate.hero_asset_id)
        hero_relative = f"hero{hero.path.suffix}"
        self._copy_asset(hero, temporary_dir / hero_relative)
        file_records.append(self._file_record(temporary_dir, hero_relative))

        character_records = []
        pack_versions: list[PackVersion] = []
        for index, character in enumerate(candidate.character_versions):
            version = self.pack_service.get_version(
                character.pack_id, character.version
            )
            pack_versions.append(version)
            relative_path = f"packs/character-{index:03d}.json"
            payload = {
                "kind": "character",
                "manifest": version.manifest,
                "pack_id": version.pack_id,
                "slot": character.slot,
                "version": version.version,
            }
            self._write_bytes(
                temporary_dir / relative_path, self._normalized_json(payload)
            )
            file_records.append(self._file_record(temporary_dir, relative_path))
            character_records.append(
                {
                    "pack_id": version.pack_id,
                    "path": relative_path,
                    "slot": character.slot,
                    "version": version.version,
                }
            )

        scene_version = self.pack_service.get_version(
            candidate.scene_pack_id, candidate.scene_version
        )
        pack_versions.append(scene_version)
        scene_relative = "packs/scene.json"
        scene_payload = {
            "kind": "scene",
            "manifest": scene_version.manifest,
            "pack_id": scene_version.pack_id,
            "version": scene_version.version,
        }
        self._write_bytes(
            temporary_dir / scene_relative,
            self._normalized_json(scene_payload),
        )
        file_records.append(self._file_record(temporary_dir, scene_relative))

        exported_assets: dict[str, dict[str, str]] = {}
        for version in pack_versions:
            for asset_id in version.manifest["asset_ids"]:
                if asset_id in exported_assets:
                    continue
                asset = self.asset_store.get(asset_id)
                relative_path = f"assets/{asset.path.name}"
                self._copy_asset(asset, temporary_dir / relative_path)
                file_records.append(
                    self._file_record(temporary_dir, relative_path)
                )
                exported_assets[asset_id] = {
                    "asset_id": asset_id,
                    "path": relative_path,
                    "sha256": asset.sha256,
                }

        scene_manifest = scene_version.manifest
        return {
            "assets": sorted(
                exported_assets.values(), key=lambda item: item["asset_id"]
            ),
            "baseline_id": baseline_id,
            "candidate_id": candidate.id,
            "canonical_candidate_id": canonical_candidate_id,
            "cast_key": candidate.cast_key,
            "changes": candidate.changes,
            "created_at": created_at,
            "fallback_reason": fallback_reason,
            "files": sorted(file_records, key=lambda item: item["path"]),
            "frame": scene_manifest["frame"],
            "hero": {
                "asset_id": hero.id,
                "path": hero_relative,
                "sha256": hero.sha256,
            },
            "packs": {
                "characters": character_records,
                "scene": {
                    "pack_id": scene_version.pack_id,
                    "path": scene_relative,
                    "version": scene_version.version,
                },
            },
            "reanchor_every": scene_manifest["reanchor_every"],
            "theme": candidate.theme,
        }

    @staticmethod
    def _normalized_json(value: object) -> bytes:
        return (
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()

    @staticmethod
    def _write_bytes(path: Path, content: bytes) -> None:
        with path.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())

    def _copy_asset(self, asset: Asset, destination: Path) -> None:
        digest = hashlib.sha256()
        try:
            with asset.path.open("rb") as source, destination.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        except FileNotFoundError as error:
            raise IntegrityError(f"missing source asset: {asset.id}") from error
        if digest.hexdigest() != asset.sha256:
            raise IntegrityError(f"source asset hash mismatch: {asset.id}")

    @classmethod
    def _file_record(cls, root: Path, relative_path: str) -> dict[str, str]:
        return {
            "path": relative_path,
            "sha256": cls._sha256(root / relative_path),
        }

    def _get_row(self, baseline_id: str) -> sqlite3.Row:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM baselines WHERE id = ?", (baseline_id,)
            ).fetchone()
        if row is None:
            raise KeyError(baseline_id)
        return row

    @staticmethod
    def _verify_identity(manifest: dict, row: sqlite3.Row) -> None:
        expected = {
            "baseline_id": row["id"],
            "cast_key": row["cast_key"],
            "candidate_id": row["candidate_id"],
            "canonical_candidate_id": row["canonical_candidate_id"],
            "fallback_reason": row["fallback_reason"],
            "created_at": row["created_at"],
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            raise IntegrityError("baseline manifest metadata mismatch")

    def _referenced_paths(
        self, manifest: dict
    ) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
        try:
            hero_relative = manifest["hero"]["path"]
            character_packs = manifest["packs"]["characters"]
            scene_pack = manifest["packs"]["scene"]
            assets = manifest["assets"]
            pack_relatives = tuple(
                record["path"] for record in character_packs
            ) + (scene_pack["path"],)
            asset_relatives = tuple(record["path"] for record in assets)
        except (KeyError, TypeError) as error:
            raise IntegrityError("invalid baseline path references") from error
        all_paths = (hero_relative, *pack_relatives, *asset_relatives)
        if not all(isinstance(path, str) for path in all_paths):
            raise IntegrityError("invalid baseline path references")
        for path in all_paths:
            self._resolve_export_path(self.export_root / manifest["baseline_id"], path)
        return hero_relative, pack_relatives, asset_relatives

    def _resolve_export_path(self, export_dir: Path, relative_path: str) -> Path:
        relative = Path(relative_path)
        if (
            not relative_path
            or relative.is_absolute()
            or "\\" in relative_path
            or ".." in relative.parts
        ):
            raise IntegrityError(f"path escape: {relative_path}")
        path = self._resolved(export_dir / relative)
        try:
            path.relative_to(self._resolved(export_dir))
        except ValueError as error:
            raise IntegrityError(f"path escape: {relative_path}") from error
        return path

    def _verify_export_contents(
        self, export_dir: Path, verified_relative_paths: set[str]
    ) -> None:
        actual_paths = set()
        try:
            for path in export_dir.rglob("*"):
                if path.is_symlink():
                    raise IntegrityError(
                        f"path escape: {path.relative_to(export_dir).as_posix()}"
                    )
                if path.is_file():
                    actual_paths.add(path.relative_to(export_dir).as_posix())
        except FileNotFoundError as error:
            raise IntegrityError("missing export directory") from error
        expected_paths = {"manifest.json", *verified_relative_paths}
        if actual_paths != expected_paths:
            raise IntegrityError("export contains missing or untracked files")

    @staticmethod
    def _read_file(path: Path) -> bytes:
        try:
            return path.read_bytes()
        except (FileNotFoundError, IsADirectoryError) as error:
            raise IntegrityError(f"missing file: {path.name}") from error

    @staticmethod
    def _resolved(path: Path) -> Path:
        try:
            return path.resolve()
        except (OSError, RuntimeError) as error:
            raise IntegrityError("path escape") from error

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while chunk := file.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _digest(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
