from __future__ import annotations

import argparse
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Literal

import uvicorn
import yaml
from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .assets import Asset, AssetStore
from .baselines import Baseline, BaselineService
from .candidates import Candidate, CandidateService
from .db import Database
from .errors import ConflictError, IntegrityError, ValidationError
from .packs import Pack, PackService, PackVersion
from .providers import ReferenceCopyProvider


DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
WEB_ROOT = Path(__file__).with_name("web")


class UploadTooLargeError(ValidationError):
    pass


class PackCreate(BaseModel):
    kind: Literal["character", "scene"]
    name: str = Field(min_length=1)


class VersionCreate(BaseModel):
    manifest: dict


class CandidateCreate(BaseModel):
    character_versions: dict[str, tuple[str, int]]
    scene_pack_id: str
    scene_version: int
    hero_asset_id: str


class GeneratedCandidateCreate(BaseModel):
    character_versions: dict[str, tuple[str, int]]
    scene_pack_id: str
    scene_version: int
    prompt: str = ""
    reference_asset_ids: list[str] = Field(min_length=1)
    seed: int | None = None


class CandidateApprove(BaseModel):
    canonical: bool = False
    review_note: str


class CandidateReject(BaseModel):
    review_note: str


class VariantCreate(BaseModel):
    canonical_candidate_id: str
    hero_asset_id: str
    theme: str
    changes: dict


class BaselineCreate(BaseModel):
    cast_key: str
    requested_candidate_id: str | None = None


@dataclass(frozen=True)
class Services:
    database: Database
    assets: AssetStore
    packs: PackService
    candidates: CandidateService
    baselines: BaselineService


def create_app(
    data_dir: Path,
    *,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> FastAPI:
    data_dir = Path(data_dir)
    database = Database(data_dir / "manager.sqlite3")
    database.initialize()
    assets = AssetStore(data_dir, database, max_bytes=max_upload_bytes)
    packs = PackService(database, assets)
    candidates = CandidateService(database, assets, packs)
    baselines = BaselineService(database, assets, packs, candidates)
    services = Services(database, assets, packs, candidates, baselines)

    app = FastAPI(title="Character Pack Manager")
    app.state.services = services
    app.state.max_upload_bytes = max_upload_bytes

    async def domain_error_handler(
        request: Request, error: Exception
    ) -> JSONResponse:
        del request
        if isinstance(error, UploadTooLargeError):
            status, code = 413, "upload_too_large"
        elif isinstance(error, ValidationError):
            status, code = 422, "validation_error"
        elif isinstance(error, ConflictError):
            status, code = 409, "conflict"
        else:
            status, code = 409, "integrity_error"
        return JSONResponse(
            status_code=status,
            content={"error": {"code": code, "message": str(error)}},
        )

    for error_type in (
        ValidationError,
        UploadTooLargeError,
        ConflictError,
        IntegrityError,
    ):
        app.add_exception_handler(error_type, domain_error_handler)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del request
        errors = error.errors()
        malformed = any(item.get("type") == "json_invalid" for item in errors)
        if malformed:
            status, code, message = 400, "malformed_request", "malformed JSON body"
        else:
            first = errors[0] if errors else {}
            location = ".".join(str(part) for part in first.get("loc", ()))
            detail = first.get("msg", "invalid request")
            message = f"{location}: {detail}" if location else detail
            status, code = 422, "request_validation"
        return _error_response(status, code, message)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        del request
        codes = {
            400: "malformed_request",
            404: "not_found",
            405: "method_not_allowed",
        }
        return _error_response(
            error.status_code,
            codes.get(error.status_code, "http_error"),
            str(error.detail),
        )

    @app.exception_handler(KeyError)
    async def missing_error_handler(
        request: Request, error: KeyError
    ) -> JSONResponse:
        del request
        missing = error.args[0] if error.args else "record"
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "not_found",
                    "message": f"record not found: {missing}",
                }
            },
        )

    @app.exception_handler(sqlite3.IntegrityError)
    async def database_conflict_handler(
        request: Request, error: sqlite3.IntegrityError
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "conflict", "message": str(error)}},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request, error: Exception
    ) -> JSONResponse:
        del request, error
        return _error_response(500, "internal_error", "internal server error")

    @app.get("/api/packs")
    def list_packs(kind: Literal["character", "scene"] | None = Query(None)):
        return [_pack_json(pack) for pack in services.packs.list_packs(kind)]

    @app.post("/api/packs", status_code=201)
    def create_pack(body: PackCreate):
        return _pack_json(services.packs.create_pack(body.kind, body.name))

    @app.get("/api/packs/{pack_id}/versions")
    def list_versions(pack_id: str):
        return [
            _version_json(version)
            for version in services.packs.list_versions(pack_id)
        ]

    @app.get("/api/packs/{pack_id}/versions/{version}")
    def get_version(pack_id: str, version: int):
        return _version_json(services.packs.get_version(pack_id, version))

    @app.post("/api/packs/{pack_id}/versions", status_code=201)
    def create_version(pack_id: str, body: VersionCreate):
        return _version_json(
            services.packs.create_version(pack_id, body.manifest)
        )

    @app.get("/api/assets")
    def list_assets():
        return [_asset_json(asset) for asset in services.assets.list_assets()]

    @app.get("/api/assets/{asset_id}/content")
    def get_asset_content(asset_id: str):
        asset, content = services.assets.read_verified(asset_id)
        return Response(
            content=content,
            media_type=asset.mime_type,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/api/assets/{asset_id}")
    def get_asset(asset_id: str):
        return _asset_json(services.assets.get(asset_id))

    @app.post("/api/assets", status_code=201)
    async def upload_asset(
        file: Annotated[UploadFile, File(description="PNG, JPEG, or WebP image")],
    ):
        mime_type = file.content_type or "application/octet-stream"
        if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValidationError(f"unsupported image type: {mime_type}")
        content = await file.read(max_upload_bytes + 1)
        if len(content) > max_upload_bytes:
            raise UploadTooLargeError(
                f"upload size exceeds limit {max_upload_bytes}"
            )
        if not _matches_image_signature(content, mime_type):
            raise ValidationError(
                f"file signature does not match {mime_type}"
            )
        # The original filename is metadata only; AssetStore never uses it as a path.
        return _asset_json(
            services.assets.put_bytes(file.filename or "upload", content, mime_type)
        )

    @app.get("/api/candidates")
    def list_candidates():
        return [
            _candidate_json(candidate)
            for candidate in services.candidates.list_candidates()
        ]

    @app.post("/api/candidates/generate", status_code=201)
    def generate_candidate(body: GeneratedCandidateCreate):
        references = tuple(
            services.assets.get(asset_id) for asset_id in body.reference_asset_ids
        )
        source = references[0]
        generated_dir = data_dir / ".generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.path.suffix
        output_path = generated_dir / f"{uuid.uuid4().hex}{suffix}"
        provider = ReferenceCopyProvider()
        try:
            provider.generate_still(
                prompt=body.prompt,
                reference_paths=tuple(asset.path for asset in references),
                seed=body.seed,
                output_path=output_path,
            )
            generated = services.assets.put_bytes(
                "generated" + suffix,
                output_path.read_bytes(),
                source.mime_type,
            )
        finally:
            output_path.unlink(missing_ok=True)
        return _candidate_json(
            services.candidates.create(
                character_versions=body.character_versions,
                scene_pack_id=body.scene_pack_id,
                scene_version=body.scene_version,
                hero_asset_id=generated.id,
            )
        )

    @app.post("/api/candidates/variants", status_code=201)
    def create_variant(body: VariantCreate):
        return _candidate_json(
            services.candidates.create_variant(
                canonical_candidate_id=body.canonical_candidate_id,
                hero_asset_id=body.hero_asset_id,
                theme=body.theme,
                changes=body.changes,
            )
        )

    @app.post("/api/candidates", status_code=201)
    def create_candidate(body: CandidateCreate):
        return _candidate_json(
            services.candidates.create(
                character_versions=body.character_versions,
                scene_pack_id=body.scene_pack_id,
                scene_version=body.scene_version,
                hero_asset_id=body.hero_asset_id,
            )
        )

    @app.get("/api/candidates/{candidate_id}")
    def get_candidate(candidate_id: str):
        return _candidate_json(services.candidates.get(candidate_id))

    @app.post("/api/candidates/{candidate_id}/approve")
    def approve_candidate(candidate_id: str, body: CandidateApprove):
        return _candidate_json(
            services.candidates.approve(
                candidate_id,
                canonical=body.canonical,
                review_note=body.review_note,
            )
        )

    @app.post("/api/candidates/{candidate_id}/reject")
    def reject_candidate(candidate_id: str, body: CandidateReject):
        return _candidate_json(
            services.candidates.reject(
                candidate_id, review_note=body.review_note
            )
        )

    @app.post("/api/baselines", status_code=201)
    def lock_baseline(body: BaselineCreate):
        return _baseline_json(
            services.baselines.lock_run(
                body.cast_key,
                requested_candidate_id=body.requested_candidate_id,
            )
        )

    @app.get("/api/baselines")
    def list_baselines():
        return [
            _baseline_json(baseline)
            for baseline in services.baselines.list_baselines()
        ]

    @app.get("/api/baselines/{baseline_id}")
    def get_baseline(baseline_id: str):
        baseline = services.baselines.get(baseline_id)
        return {
            "id": baseline_id,
            "candidate_id": baseline.candidate_id,
            "fallback_reason": baseline.fallback_reason,
            "manifest_sha256": baseline.manifest_sha256,
            "verified": True,
        }

    @app.get("/api/baselines/{baseline_id}/manifest")
    def get_manifest(baseline_id: str):
        return services.baselines.load(baseline_id).manifest

    @app.get("/api/baselines/{baseline_id}/download/manifest")
    def download_manifest(baseline_id: str):
        content = services.baselines.read_manifest_verified(baseline_id)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{baseline_id}-manifest.json"'
                ),
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.delete("/api/baselines/{baseline_id}")
    def reject_baseline_delete(baseline_id: str):
        services.baselines.load(baseline_id)
        raise ConflictError("locked baselines are immutable")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_ROOT / "index.html")

    app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")
    return app


def _asset_json(asset: Asset) -> dict:
    return {
        "id": asset.id,
        "sha256": asset.sha256,
        "mime_type": asset.mime_type,
        "size": asset.size,
        "created_at": asset.created_at,
    }


def _pack_json(pack: Pack) -> dict:
    return asdict(pack)


def _version_json(version: PackVersion) -> dict:
    return {
        "pack_id": version.pack_id,
        "version": version.version,
        "manifest": version.manifest,
        "created_at": version.created_at,
    }


def _candidate_json(candidate: Candidate) -> dict:
    return {
        "id": candidate.id,
        "cast_key": candidate.cast_key,
        "character_versions": [
            asdict(version) for version in candidate.character_versions
        ],
        "scene_pack_id": candidate.scene_pack_id,
        "scene_version": candidate.scene_version,
        "hero_asset_id": candidate.hero_asset_id,
        "canonical_candidate_id": candidate.canonical_candidate_id,
        "theme": candidate.theme,
        "changes": candidate.changes,
        "status": candidate.status,
        "review_note": candidate.review_note,
        "created_at": candidate.created_at,
        "reviewed_at": candidate.reviewed_at,
    }


def _baseline_json(baseline: Baseline) -> dict:
    return {
        "id": baseline.id,
        "cast_key": baseline.cast_key,
        "candidate_id": baseline.candidate_id,
        "canonical_candidate_id": baseline.canonical_candidate_id,
        "fallback_reason": baseline.fallback_reason,
        "manifest_sha256": baseline.manifest_sha256,
        "created_at": baseline.created_at,
    }


def _error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


def _matches_image_signature(content: bytes, mime_type: str) -> bool:
    if mime_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if mime_type == "image/webp":
        return (
            len(content) >= 12
            and content.startswith(b"RIFF")
            and content[8:12] == b"WEBP"
        )
    return False


def _load_config(path: Path) -> dict:
    try:
        content = yaml.safe_load(path.read_text())
    except FileNotFoundError as error:
        raise SystemExit(f"config file not found: {path}") from error
    if not isinstance(content, dict):
        raise SystemExit("config must be a YAML object")
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local character pack manager")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    args = parser.parse_args()
    config = _load_config(args.config)
    host = config.get("host", "127.0.0.1")
    if host != "127.0.0.1":
        raise SystemExit("host must be 127.0.0.1")
    port = config.get("port", 8765)
    data_dir = Path(config.get("data_dir", "data"))
    max_upload_bytes = config.get("max_upload_bytes", DEFAULT_MAX_UPLOAD_BYTES)
    if (
        isinstance(port, bool)
        or not isinstance(port, int)
        or not 1 <= port <= 65535
    ):
        raise SystemExit("port must be an integer from 1 to 65535")
    if (
        isinstance(max_upload_bytes, bool)
        or not isinstance(max_upload_bytes, int)
        or max_upload_bytes <= 0
    ):
        raise SystemExit("max_upload_bytes must be a positive integer")
    app = create_app(data_dir, max_upload_bytes=max_upload_bytes)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
