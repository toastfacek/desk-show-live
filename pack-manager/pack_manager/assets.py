import hashlib
import os
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import Database
from .errors import ValidationError


_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


@dataclass(frozen=True)
class Asset:
    id: str
    sha256: str
    mime_type: str
    size: int
    path: Path
    created_at: str


class AssetStore:
    def __init__(
        self,
        data_dir: str | Path,
        database: Database,
        *,
        max_bytes: int = 10 * 1024 * 1024,
    ):
        self.data_dir = Path(data_dir)
        self.database = database
        self.max_bytes = max_bytes

    def put_bytes(self, filename: str, content: bytes, mime_type: str) -> Asset:
        del filename  # Uploaded names never influence storage paths.
        try:
            extension = _EXTENSIONS[mime_type]
        except KeyError as error:
            raise ValidationError(f"unsupported image type: {mime_type}") from error
        if len(content) > self.max_bytes:
            raise ValidationError(
                f"upload size {len(content)} exceeds limit {self.max_bytes}"
            )

        digest = hashlib.sha256(content).hexdigest()
        blob_dir = self.data_dir / "blobs"
        blob_dir.mkdir(parents=True, exist_ok=True)
        path = blob_dir / f"{digest}{extension}"
        self._write_once(path, content)

        asset_id = f"asset_{uuid.uuid4().hex}"
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO assets
                    (id, sha256, mime_type, size, path, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (asset_id, digest, mime_type, len(content), str(path), created_at),
            )
            row = connection.execute(
                "SELECT * FROM assets WHERE sha256 = ?", (digest,)
            ).fetchone()

        if row is None:  # Defensive: the insert and select occur in one transaction.
            raise RuntimeError("asset metadata was not stored")
        return self._from_row(row)

    def get(self, asset_id: str) -> Asset:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assets WHERE id = ?", (asset_id,)
            ).fetchone()
        if row is None:
            raise KeyError(asset_id)
        return self._from_row(row)

    @staticmethod
    def _write_once(path: Path, content: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent, prefix=".upload-"
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            try:
                os.link(temporary_path, path)
            except FileExistsError:
                pass
        finally:
            temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Asset:
        return Asset(
            id=row["id"],
            sha256=row["sha256"],
            mime_type=row["mime_type"],
            size=row["size"],
            path=Path(row["path"]),
            created_at=row["created_at"],
        )
