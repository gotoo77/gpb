from __future__ import annotations

import json
import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS media (
  id TEXT PRIMARY KEY,
  provider_id TEXT,
  source TEXT NOT NULL,
  original_name TEXT NOT NULL,
  local_path TEXT NOT NULL UNIQUE,
  mime_type TEXT,
  size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  capture_time TEXT,
  remote_creation_time TEXT,
  imported_at TEXT NOT NULL,
  width INTEGER,
  height INTEGER,
  duration_seconds REAL,
  download_status TEXT NOT NULL DEFAULT 'complete',
  verification_status TEXT NOT NULL DEFAULT 'pending',
  remote_url TEXT,
  metadata_provenance TEXT,
  sidecar_path TEXT,
  error TEXT,
  attempts INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS media_provider ON media(source, provider_id)
  WHERE provider_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS media_hash ON media(sha256);
CREATE TABLE IF NOT EXISTS verification_cache (
  media_id TEXT PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE,
  size INTEGER NOT NULL,
  mtime_ns INTEGER NOT NULL,
  status TEXT NOT NULL,
  checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  command TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  counters_json TEXT NOT NULL DEFAULT '{}',
  result TEXT NOT NULL DEFAULT 'running',
  errors_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS picker_sessions (
  id TEXT PRIMARY KEY,
  picker_uri TEXT NOT NULL,
  media_items_set INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, root: Path, path: Path | None = None) -> None:
        self.path = path or root / ".gphotos-backup" / "state.sqlite3"

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
        os.chmod(self.path, 0o600)

    def begin_run(self, command: str) -> str:
        run_id = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO runs(id, command, started_at) VALUES (?, ?, ?)",
                (run_id, command, datetime.now(UTC).isoformat()),
            )
        return run_id

    def finish_run(
        self, run_id: str, counters: dict[str, Any], result: str, errors: list[str] | None = None
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE runs SET finished_at=?, counters_json=?, result=?, errors_json=?
                   WHERE id=?""",
                (
                    datetime.now(UTC).isoformat(),
                    json.dumps(counters, sort_keys=True),
                    result,
                    json.dumps(errors or []),
                    run_id,
                ),
            )

    def by_hash(self, digest: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM media WHERE sha256=? AND download_status='complete' LIMIT 1",
                    (digest,),
                ).fetchone(),
            )

    def by_provider(self, source: str, provider_id: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return cast(
                sqlite3.Row | None,
                connection.execute(
                    "SELECT * FROM media WHERE source=? AND provider_id=? LIMIT 1",
                    (source, provider_id),
                ).fetchone(),
            )

    def add_media(self, values: dict[str, Any]) -> str:
        media_id = str(uuid.uuid4())
        fields = {"id": media_id, "imported_at": datetime.now(UTC).isoformat(), **values}
        names = ", ".join(fields)
        placeholders = ", ".join("?" for _ in fields)
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO media ({names}) VALUES ({placeholders})",
                tuple(fields.values()),
            )
        return media_id

    def rows(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(connection.execute("SELECT * FROM media ORDER BY imported_at, id"))

    def verification_cache(self) -> dict[str, sqlite3.Row]:
        with self.connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS verification_cache (
                   media_id TEXT PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE,
                   size INTEGER NOT NULL,
                   mtime_ns INTEGER NOT NULL,
                   status TEXT NOT NULL,
                   checked_at TEXT NOT NULL
                )"""
            )
            return {
                str(row["media_id"]): row
                for row in connection.execute("SELECT * FROM verification_cache")
            }

    def counts(self) -> dict[str, int]:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) total,
                   SUM(download_status='complete') complete,
                   SUM(verification_status='verified') verified
                   FROM media"""
            ).fetchone()
        return {key: int(row[key] or 0) for key in ("total", "complete", "verified")}

    def latest_run(self) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT command, started_at, finished_at, counters_json, result, errors_json
                   FROM runs ORDER BY started_at DESC LIMIT 1"""
            ).fetchone()
        if row is None:
            return None
        return {
            "command": row["command"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "result": row["result"],
            "counters": json.loads(row["counters_json"]),
            "errors": json.loads(row["errors_json"]),
        }
