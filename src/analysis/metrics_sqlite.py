"""Repositório versionado de métricas determinísticas."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from src.core.contracts.metrics import MetricResult

__all__ = ["MetricSQLiteRepository"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    execution_id TEXT NOT NULL,
    metric_id TEXT NOT NULL,
    metric_version TEXT NOT NULL,
    value REAL,
    applicable INTEGER NOT NULL,
    detail TEXT NOT NULL,
    computed_at REAL NOT NULL,
    PRIMARY KEY (execution_id, metric_id, metric_version)
);
CREATE INDEX IF NOT EXISTS idx_metrics_exec ON metrics(execution_id);
CREATE INDEX IF NOT EXISTS idx_metrics_id ON metrics(metric_id, metric_version);
"""


class MetricSQLiteRepository:
    def __init__(self, path: str | Path) -> None:
        self._connection = sqlite3.connect(str(path), timeout=30, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(_SCHEMA)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> MetricSQLiteRepository:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def save(self, metrics: list[MetricResult]) -> int:
        if not metrics:
            return 0
        rows = []
        for metric in metrics:
            computed_at = metric.computed_at or time.time()
            rows.append(
                (
                    metric.execution_id,
                    metric.metric_id,
                    metric.metric_version,
                    metric.value,
                    int(metric.applicable),
                    json.dumps(metric.detail, ensure_ascii=False, sort_keys=True),
                    computed_at,
                )
            )
        before = self._connection.total_changes
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.executemany(
                """
                INSERT OR IGNORE INTO metrics(
                    execution_id, metric_id, metric_version, value,
                    applicable, detail, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            inserted = self._connection.total_changes - before
            self._connection.commit()
            return inserted
        except BaseException:
            self._connection.rollback()
            raise

    def for_execution(self, execution_id: str) -> list[MetricResult]:
        rows = self._connection.execute(
            """
            SELECT * FROM metrics WHERE execution_id = ?
            ORDER BY metric_id, metric_version
            """,
            (execution_id,),
        ).fetchall()
        return [self._metric(row) for row in rows]

    def for_metric(self, metric_id: str, version: str | None = None) -> list[MetricResult]:
        where_version = " AND metric_version = ?" if version is not None else ""
        params: tuple[str, ...] = (metric_id,) if version is None else (metric_id, version)
        rows = self._connection.execute(
            f"""
            SELECT * FROM metrics WHERE metric_id = ?{where_version}
            ORDER BY execution_id, metric_version
            """,
            params,
        ).fetchall()
        return [self._metric(row) for row in rows]

    @staticmethod
    def _metric(row: sqlite3.Row) -> MetricResult:
        return MetricResult(
            execution_id=row["execution_id"],
            metric_id=row["metric_id"],
            metric_version=row["metric_version"],
            value=row["value"],
            applicable=bool(row["applicable"]),
            detail=json.loads(row["detail"]),
            computed_at=row["computed_at"],
        )
