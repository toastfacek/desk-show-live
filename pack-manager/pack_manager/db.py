import sqlite3
from pathlib import Path


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL UNIQUE,
                mime_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS packs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('character', 'scene')),
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pack_versions (
                pack_id TEXT NOT NULL REFERENCES packs(id),
                version INTEGER NOT NULL CHECK (version > 0),
                manifest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (pack_id, version)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS candidates (
                id TEXT PRIMARY KEY,
                cast_key TEXT NOT NULL,
                character_versions TEXT NOT NULL,
                scene_pack_id TEXT NOT NULL,
                scene_version INTEGER NOT NULL,
                hero_asset_id TEXT NOT NULL REFERENCES assets(id),
                canonical_candidate_id TEXT REFERENCES candidates(id),
                theme TEXT,
                changes TEXT,
                status TEXT NOT NULL CHECK (status IN ('draft', 'approved', 'rejected')),
                review_note TEXT,
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS baselines (
                id TEXT PRIMARY KEY,
                cast_key TEXT NOT NULL,
                candidate_id TEXT NOT NULL REFERENCES candidates(id),
                canonical_candidate_id TEXT NOT NULL REFERENCES candidates(id),
                fallback_reason TEXT,
                manifest_path TEXT NOT NULL,
                manifest_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS canonical_candidates (
                cast_key TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL REFERENCES candidates(id),
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS baselines_immutable_update
            BEFORE UPDATE ON baselines
            BEGIN
                SELECT RAISE(ABORT, 'baselines are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS baselines_immutable_delete
            BEFORE DELETE ON baselines
            BEGIN
                SELECT RAISE(ABORT, 'baselines are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS pack_versions_immutable_update
            BEFORE UPDATE ON pack_versions
            BEGIN
                SELECT RAISE(ABORT, 'pack versions are immutable');
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS pack_versions_immutable_delete
            BEFORE DELETE ON pack_versions
            BEGIN
                SELECT RAISE(ABORT, 'pack versions are immutable');
            END
            """,
        )

        with self.connect() as connection:
            connection.execute("BEGIN")
            for statement in statements:
                connection.execute(statement)
