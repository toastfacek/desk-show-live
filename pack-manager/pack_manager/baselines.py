import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .assets import Asset, AssetStore
from .candidates import Candidate, CandidateService
from .db import Database
from .errors import IntegrityError, ValidationError
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
    verified_bytes: dict[str, bytes]


class BaselineService:
    def __init__(
        self,
        database: Database,
        asset_store: AssetStore,
        pack_service: PackService,
        candidate_service: CandidateService,
        *,
        maintenance: bool = True,
    ):
        self.database = database
        self.asset_store = asset_store
        self.pack_service = pack_service
        self.candidate_service = candidate_service
        self.export_root = (asset_store.data_dir / "exports").absolute()
        if maintenance:
            self._cleanup_orphan_exports()

    def lock_run(
        self, cast_key: str, requested_candidate_id: str | None = None
    ) -> Baseline:
        with self._manager_lock():
            return self._lock_run_locked(cast_key, requested_candidate_id)

    def _lock_run_locked(
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

    def get(self, baseline_id: str) -> Baseline:
        row = self._get_row(baseline_id)
        loaded = self.load(baseline_id)
        return self._baseline_from_row(row, loaded)

    def list_baselines(self) -> list[Baseline]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM baselines ORDER BY created_at, rowid"
            ).fetchall()
        baselines = []
        for row in rows:
            try:
                loaded = self.load(row["id"])
            except IntegrityError:
                continue
            baselines.append(self._baseline_from_row(row, loaded))
        return baselines

    def read_manifest_verified(self, baseline_id: str) -> bytes:
        loaded = self.load(baseline_id)
        content = self._read_file(loaded.manifest_path)
        row = self._get_row(baseline_id)
        if self._digest(content) != row["manifest_sha256"]:
            raise IntegrityError("manifest hash mismatch after verification")
        return content

    def load(self, baseline_id: str) -> LoadedBaseline:
        row = self._get_row(baseline_id)
        export_dir = self.export_root / baseline_id
        self._reject_symlinked_export_ancestors(export_dir)
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
        verified_bytes: dict[str, bytes] = {}
        verified_bytes["manifest.json"] = manifest_bytes
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
            verified_bytes[relative_path] = content

        hero_relative, pack_relatives, asset_relatives = self._referenced_paths(
            manifest
        )
        referenced = {hero_relative, *pack_relatives, *asset_relatives}
        if referenced != set(verified_paths):
            raise IntegrityError("manifest file references do not match hash records")
        self._verify_export_contents(export_dir, set(verified_paths))
        self._verify_runtime_metadata(manifest, verified_bytes)

        return LoadedBaseline(
            id=baseline_id,
            manifest=manifest,
            manifest_path=manifest_path,
            hero_path=verified_paths[hero_relative],
            pack_paths=tuple(verified_paths[path] for path in pack_relatives),
            asset_paths=tuple(verified_paths[path] for path in asset_relatives),
            verified_bytes=verified_bytes,
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
            PackService.validate_flight_ready("character", version.manifest)
            pack_versions.append(version)
            relative_path = f"packs/character-{index:03d}.json"
            payload = {
                "kind": "character",
                "manifest": version.manifest,
                "name": self._pack_name(version.pack_id),
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
        PackService.validate_flight_ready("scene", scene_version.manifest)
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
        display_names = {
            character.slot: self._pack_name(character.pack_id)
            for character in candidate.character_versions
        }
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
            "host_map": {"BOT1": "host_a", "BOT2": "host_b"},
            "display_names": display_names,
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

    def _pack_name(self, pack_id: str) -> str:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT name FROM packs WHERE id = ?", (pack_id,)
            ).fetchone()
        if row is None or not row["name"].strip():
            raise IntegrityError(f"missing pack: {pack_id}")
        return row["name"]

    def _verify_runtime_metadata(
        self, manifest: dict, verified_bytes: dict[str, bytes]
    ) -> None:
        if manifest.get("host_map") != {
            "BOT1": "host_a",
            "BOT2": "host_b",
        }:
            raise IntegrityError("invalid host mapping")
        characters = manifest.get("packs", {}).get("characters")
        display_names = manifest.get("display_names")
        if not isinstance(characters, list) or not isinstance(display_names, dict):
            raise IntegrityError("invalid display names")
        if set(display_names) != {"BOT1", "BOT2"}:
            raise IntegrityError("invalid display names")
        expected = {}
        try:
            for record in characters:
                relative_path = record["path"]
                payload = json.loads(verified_bytes[relative_path])
                if any(
                    payload.get(field) != record.get(field)
                    for field in ("slot", "pack_id", "version")
                ):
                    raise IntegrityError(
                        "character pack metadata mismatch"
                    )
                expected[record["slot"]] = payload["name"]
            scene_record = manifest["packs"]["scene"]
            scene_payload = json.loads(
                verified_bytes[scene_record["path"]]
            )
            if any(
                scene_payload.get(field) != scene_record.get(field)
                for field in ("pack_id", "version")
            ):
                raise IntegrityError("scene pack metadata mismatch")
        except (
            KeyError,
            TypeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise IntegrityError("invalid character pack metadata") from error
        if display_names != expected or not all(
            isinstance(name, str) and name.strip()
            for name in display_names.values()
        ):
            raise IntegrityError("invalid display names")

    def _cleanup_orphan_exports(self) -> None:
        if self.export_root.is_symlink():
            return
        self.export_root.mkdir(parents=True, exist_ok=True)
        with self._manager_lock():
            self._cleanup_orphan_exports_locked()

    def _cleanup_orphan_exports_locked(self) -> None:
        with self.database.connect() as connection:
            referenced = {
                row["id"]
                for row in connection.execute("SELECT id FROM baselines")
            }
        for path in self.export_root.iterdir():
            name = path.name
            remove = name.startswith(".tmp-baseline_") or (
                name.startswith("baseline_") and name not in referenced
            )
            if not remove:
                continue
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path)

    @contextmanager
    def _manager_lock(self):
        self.export_root.mkdir(parents=True, exist_ok=True)
        lock_path = self.export_root / ".manager.lock"
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

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
    def _baseline_from_row(
        row: sqlite3.Row, loaded: LoadedBaseline
    ) -> Baseline:
        return Baseline(
            id=row["id"],
            cast_key=row["cast_key"],
            candidate_id=row["candidate_id"],
            canonical_candidate_id=row["canonical_candidate_id"],
            fallback_reason=row["fallback_reason"],
            manifest_path=loaded.manifest_path,
            manifest_sha256=row["manifest_sha256"],
            hero_path=loaded.hero_path,
            created_at=row["created_at"],
        )

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

    def _reject_symlinked_export_ancestors(self, export_dir: Path) -> None:
        try:
            relative_parts = export_dir.relative_to(self.export_root).parts
        except ValueError as error:
            raise IntegrityError("baseline root path escape") from error

        paths = [self.export_root]
        for part in relative_parts:
            paths.append(paths[-1] / part)
        for path in paths:
            if path.is_symlink():
                raise IntegrityError(f"symlinked export root: {path.name}")

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
