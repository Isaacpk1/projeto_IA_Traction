"""Cache durável e idempotente dos julgamentos."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from src.core.contracts.metrics import Judgment

_SCHEMA = """
CREATE TABLE IF NOT EXISTS judgments (
    execution_id TEXT NOT NULL,
    criterion_id TEXT NOT NULL,
    rubric_version TEXT NOT NULL,
    judge_model TEXT NOT NULL,
    verdict TEXT NOT NULL,
    justification TEXT NOT NULL,
    tokens INTEGER NOT NULL,
    judged_at REAL NOT NULL,
    PRIMARY KEY (execution_id, criterion_id, rubric_version, judge_model)
);
CREATE INDEX IF NOT EXISTS idx_judgments_exec ON judgments(execution_id);
"""


class JudgmentSQLiteRepository:
    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), timeout=30, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(_SCHEMA)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> JudgmentSQLiteRepository:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def save(self, judgments: list[Judgment]) -> int:
        if not judgments:
            return 0
        rows = [
            (
                item.execution_id,
                item.criterion_id,
                item.rubric_version,
                item.judge_model,
                item.verdict,
                item.justification,
                item.tokens,
                item.judged_at or time.time(),
            )
            for item in judgments
        ]
        before = self._connection.total_changes
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.executemany(
                "INSERT OR IGNORE INTO judgments VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
            )
            inserted = self._connection.total_changes - before
            self._connection.commit()
            return inserted
        except BaseException:
            self._connection.rollback()
            raise

    def has_execution(
        self,
        execution_id: str,
        rubric_version: str,
        judge_model: str,
        *,
        expected_count: int = 1,
    ) -> bool:
        row = self._connection.execute(
            """SELECT COUNT(*) AS total FROM judgments
               WHERE execution_id=? AND rubric_version=? AND judge_model=?""",
            (execution_id, rubric_version, judge_model),
        ).fetchone()
        return row is not None and int(row["total"]) == expected_count

    def for_execution(self, execution_id: str) -> list[Judgment]:
        rows = self._connection.execute(
            "SELECT * FROM judgments WHERE execution_id=? ORDER BY criterion_id",
            (execution_id,),
        ).fetchall()
        return [Judgment.model_validate(dict(row)) for row in rows]
