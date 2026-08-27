"""Fila SQLite durável com lease transacional — ADR-07 e ADR-10."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from src.core.contracts.task import Lease, Task
from src.core.errors import ErrorClass

__all__ = ["SQLiteWorkQueue"]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    case_id TEXT NOT NULL,
    architecture TEXT NOT NULL,
    priority INTEGER NOT NULL,
    source TEXT NOT NULL,
    received_at REAL NOT NULL,
    session_id TEXT,
    run_id TEXT,
    seed TEXT,
    repetition INTEGER NOT NULL,
    arm TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    leased_by TEXT,
    lease_expires REAL,
    execution_id TEXT,
    error_class TEXT,
    created_at REAL NOT NULL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_lease
    ON tasks(state, attempts, priority DESC, received_at);
CREATE INDEX IF NOT EXISTS idx_run ON tasks(run_id, state);
CREATE INDEX IF NOT EXISTS idx_tickets ON tasks(kind, state, priority DESC);
"""

_COLUMNS = tuple(Task.model_fields)


class SQLiteWorkQueue:
    """Implementação ACID de ``WorkQueue``; segura para múltiplos threads/processos."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._paused = False
        self._connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(_SCHEMA)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SQLiteWorkQueue:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @staticmethod
    def _now(value: float | None) -> float:
        return value if value is not None else time.time()

    @staticmethod
    def _task(row: sqlite3.Row) -> Task:
        return Task.model_validate({column: row[column] for column in _COLUMNS})

    def enqueue(self, tasks: list[Task]) -> int:
        if not tasks:
            return 0
        now = time.time()
        placeholders = ", ".join("?" for _ in _COLUMNS)
        sql = f"INSERT OR IGNORE INTO tasks ({', '.join(_COLUMNS)}) VALUES ({placeholders})"
        rows = []
        for task in tasks:
            values = task.model_dump()
            values["received_at"] = task.received_at or now
            values["created_at"] = task.created_at or now
            rows.append(tuple(values[column] for column in _COLUMNS))
        with self._lock:
            before = self._connection.total_changes
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.executemany(sql, rows)
                inserted = self._connection.total_changes - before
                self._connection.commit()
                return inserted
            except BaseException:
                self._connection.rollback()
                raise

    def lease(
        self,
        worker: str,
        ttl: float,
        *,
        run_id: str | None = None,
        max_attempts: int = 3,
        now: float | None = None,
    ) -> Lease | None:
        if ttl <= 0:
            raise ValueError("ttl deve ser positivo")
        instant = self._now(now)
        with self._lock:
            if self._paused:
                return None
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """
                    UPDATE tasks
                       SET state = CASE WHEN attempts + 1 >= ? THEN 'failed' ELSE 'pending' END,
                           attempts = attempts + 1,
                           error_class = 'infra',
                           completed_at = CASE WHEN attempts + 1 >= ? THEN ? ELSE NULL END,
                           leased_by = NULL,
                           lease_expires = NULL
                     WHERE state = 'leased' AND lease_expires < ?
                    """,
                    (max_attempts, max_attempts, instant, instant),
                )
                where_run = " AND run_id = ?" if run_id is not None else ""
                params: tuple[object, ...] = (max_attempts,)
                if run_id is not None:
                    params += (run_id,)
                row = self._connection.execute(
                    f"""
                    SELECT * FROM tasks
                     WHERE state = 'pending' AND attempts < ?{where_run}
                     ORDER BY attempts ASC, priority DESC, received_at ASC, task_id ASC
                     LIMIT 1
                    """,
                    params,
                ).fetchone()
                if row is None:
                    self._connection.commit()
                    return None
                expires = instant + ttl
                self._connection.execute(
                    """
                    UPDATE tasks
                       SET state = 'leased', leased_by = ?, lease_expires = ?, completed_at = NULL
                     WHERE task_id = ? AND state = 'pending'
                    """,
                    (worker, expires, row["task_id"]),
                )
                leased_row = self._connection.execute(
                    "SELECT * FROM tasks WHERE task_id = ?", (row["task_id"],)
                ).fetchone()
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise
        task = self._task(leased_row)
        return Lease(task=task, worker=worker, expires_at=expires, attempt=task.attempts + 1)

    def complete(
        self,
        task_id: str,
        execution_id: str,
        *,
        worker: str | None = None,
        now: float | None = None,
    ) -> None:
        instant = self._now(now)
        owner_clause = " AND leased_by = ?" if worker is not None else ""
        params: tuple[object, ...] = (execution_id, instant, task_id)
        if worker is not None:
            params += (worker,)
        with self._lock:
            cursor = self._connection.execute(
                f"""
                UPDATE tasks
                   SET state = 'done', execution_id = ?, completed_at = ?, error_class = NULL,
                       leased_by = NULL, lease_expires = NULL
                 WHERE task_id = ? AND state = 'leased'{owner_clause}
                """,
                params,
            )
        if cursor.rowcount != 1:
            raise RuntimeError(f"task não está leased: {task_id}")

    def fail(
        self,
        task_id: str,
        error_class: ErrorClass,
        *,
        execution_id: str | None = None,
        worker: str | None = None,
        now: float | None = None,
        max_attempts: int = 3,
    ) -> None:
        instant = self._now(now)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT attempts, state, leased_by FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(task_id)
                if row["state"] != "leased" or (worker is not None and row["leased_by"] != worker):
                    raise RuntimeError(f"task não pertence ao worker: {task_id}")

                attempts = int(row["attempts"])
                if error_class == "budget":
                    state, completed_at = "pending", None
                elif error_class == "contract":
                    state, completed_at = "failed", instant
                elif error_class == "behavior":
                    state, completed_at = "done", instant
                else:
                    attempts += 1
                    state = "failed" if attempts >= max_attempts else "pending"
                    completed_at = instant if state == "failed" else None

                self._connection.execute(
                    """
                    UPDATE tasks
                       SET state = ?, attempts = ?, execution_id = ?, error_class = ?,
                           completed_at = ?, leased_by = NULL, lease_expires = NULL
                     WHERE task_id = ?
                    """,
                    (state, attempts, execution_id, error_class, completed_at, task_id),
                )
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise

    def heartbeat(self, task_id: str, worker: str, ttl: float, *, now: float | None = None) -> bool:
        if ttl <= 0:
            raise ValueError("ttl deve ser positivo")
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE tasks SET lease_expires = ?
                 WHERE task_id = ? AND state = 'leased' AND leased_by = ?
                """,
                (self._now(now) + ttl, task_id, worker),
            )
            return cursor.rowcount == 1

    def pause_lease(self, paused: bool = True) -> None:
        self._paused = paused

    def counts(self, run_id: str | None = None) -> dict[str, int]:
        params: tuple[object, ...] = ()
        where = ""
        if run_id is not None:
            where = " WHERE run_id = ?"
            params = (run_id,)
        with self._lock:
            rows = self._connection.execute(
                f"SELECT state, COUNT(*) AS n FROM tasks{where} GROUP BY state", params
            ).fetchall()
        counts = {state: 0 for state in ("pending", "leased", "done", "failed")}
        counts.update({str(row["state"]): int(row["n"]) for row in rows})
        return counts

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return self._task(row) if row is not None else None
