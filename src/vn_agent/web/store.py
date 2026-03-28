"""Persistent job store backed by SQLite."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    theme TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    progress TEXT NOT NULL DEFAULT 'queued',
    errors TEXT NOT NULL DEFAULT '[]',
    output_dir TEXT,
    blackboard TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_MIGRATE_BLACKBOARD = """
ALTER TABLE jobs ADD COLUMN blackboard TEXT NOT NULL DEFAULT '{}'
"""


class JobStore:
    """SQLite-backed job persistence with blackboard support."""

    def __init__(self, db_path: Path | str = "vn_jobs.db"):
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """Add blackboard column if missing (backward compat)."""
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "blackboard" not in cols:
            try:
                self._conn.execute(_MIGRATE_BLACKBOARD)
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # already exists

    def close(self) -> None:
        self._conn.close()

    def create(self, job_id: str, theme: str, config: dict, output_dir: str) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT INTO jobs (job_id, theme, config, output_dir, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, theme, json.dumps(config), output_dir, now, now),
        )
        self._conn.commit()

    def update_status(
        self,
        job_id: str,
        status: str,
        progress: str | None = None,
        errors: list[str] | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        updates = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status, now]

        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if errors is not None:
            updates.append("errors = ?")
            params.append(json.dumps(errors))

        params.append(job_id)
        self._conn.execute(
            f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?", params
        )
        self._conn.commit()

    def update_blackboard(self, job_id: str, blackboard: dict) -> None:
        """Save the full blackboard JSON snapshot."""
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "UPDATE jobs SET blackboard = ?, updated_at = ? WHERE job_id = ?",
            (json.dumps(blackboard, ensure_ascii=False), now, job_id),
        )
        self._conn.commit()

    def get_blackboard(self, job_id: str) -> dict:
        row = self._conn.execute(
            "SELECT blackboard FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return {}
        return json.loads(row["blackboard"] or "{}")

    def get(self, job_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_recent(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete(self, job_id: str) -> bool:
        cursor = self._conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["errors"] = json.loads(d.get("errors", "[]"))
        d["config"] = json.loads(d.get("config", "{}"))
        d["blackboard"] = json.loads(d.get("blackboard", "{}"))
        return d
