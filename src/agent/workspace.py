"""Durable workspace store for the conversational shell (Phase 1).

A single SQLite database (stdlib ``sqlite3`` — no new dependency) holds every
workspace, its chat messages, its tasks, and the artifacts each task produced.
Everything survives a restart so a conversation and its in-flight work can be
resumed. This module stores state only; it never invokes a pipeline and never
touches interest math.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Task lifecycle. PENDING/RUNNING/FAILED are all "resumable" — RUNNING is
# treated as resumable because a process that died mid-run leaves a task stuck
# in RUNNING with no result.
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
_RESUMABLE = (STATUS_PENDING, STATUS_RUNNING, STATUS_FAILED)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Task:
    id: int
    workspace_id: int
    tool_name: str
    params: dict[str, Any]
    status: str
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    updated_at: str


@dataclass
class Artifact:
    id: int
    task_id: int
    workspace_id: int
    kind: str
    path: str
    created_at: str


@dataclass
class Message:
    id: int
    workspace_id: int
    role: str
    content: str
    created_at: str


class WorkspaceStore:
    """Thin, synchronous persistence layer over one SQLite file."""

    def __init__(self, db_path: str | Path = "data/agent/agent.db") -> None:
        self.db_path = Path(db_path)
        if str(db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    # -- schema ------------------------------------------------------------
    def _migrate(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                folder_path TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
                tool_name TEXT NOT NULL,
                params_json TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id),
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
                kind TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- workspaces --------------------------------------------------------
    def create_workspace(self, name: str, folder_path: str | Path | None = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO workspaces (name, folder_path, created_at) VALUES (?, ?, ?)",
            (name, str(folder_path) if folder_path is not None else None, _now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_workspace(self, workspace_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_workspaces(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM workspaces ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # -- messages ----------------------------------------------------------
    def add_message(self, workspace_id: int, role: str, content: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO messages (workspace_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (workspace_id, role, content, _now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_messages(self, workspace_id: int) -> list[Message]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE workspace_id = ? ORDER BY id", (workspace_id,)
        ).fetchall()
        return [Message(**dict(r)) for r in rows]

    # -- tasks -------------------------------------------------------------
    def create_task(self, workspace_id: int, tool_name: str, params: dict[str, Any]) -> int:
        ts = _now()
        cur = self._conn.execute(
            "INSERT INTO tasks (workspace_id, tool_name, params_json, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (workspace_id, tool_name, json.dumps(params, default=str), STATUS_PENDING, ts, ts),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def update_task(
        self,
        task_id: int,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self._conn.execute(
            "UPDATE tasks SET status = ?, result_json = ?, error = ?, updated_at = ? WHERE id = ?",
            (
                status,
                json.dumps(result, default=str) if result is not None else None,
                error,
                _now(),
                task_id,
            ),
        )
        self._conn.commit()

    def get_task(self, task_id: int) -> Task | None:
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def list_tasks(self, workspace_id: int) -> list[Task]:
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE workspace_id = ? ORDER BY id", (workspace_id,)
        ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def resumable_tasks(self, workspace_id: int | None = None) -> list[Task]:
        placeholders = ",".join("?" * len(_RESUMABLE))
        if workspace_id is None:
            rows = self._conn.execute(
                f"SELECT * FROM tasks WHERE status IN ({placeholders}) ORDER BY id", _RESUMABLE
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT * FROM tasks WHERE workspace_id = ? AND status IN ({placeholders}) ORDER BY id",
                (workspace_id, *_RESUMABLE),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        d = dict(row)
        return Task(
            id=d["id"],
            workspace_id=d["workspace_id"],
            tool_name=d["tool_name"],
            params=json.loads(d["params_json"]),
            status=d["status"],
            result=json.loads(d["result_json"]) if d["result_json"] else None,
            error=d["error"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
        )

    # -- artifacts ---------------------------------------------------------
    def add_artifact(self, task_id: int, workspace_id: int, kind: str, path: str | Path) -> int:
        cur = self._conn.execute(
            "INSERT INTO artifacts (task_id, workspace_id, kind, path, created_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, workspace_id, kind, str(path), _now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_artifacts(self, task_id: int | None = None, workspace_id: int | None = None) -> list[Artifact]:
        if task_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM artifacts WHERE task_id = ? ORDER BY id", (task_id,)
            ).fetchall()
        elif workspace_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM artifacts WHERE workspace_id = ? ORDER BY id", (workspace_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM artifacts ORDER BY id").fetchall()
        return [Artifact(**dict(r)) for r in rows]
