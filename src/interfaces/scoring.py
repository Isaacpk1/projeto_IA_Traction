"""Composição pós-execução: trace concluído → métricas versionadas."""

from __future__ import annotations

from collections.abc import Callable

from src.analysis import MetricSQLiteRepository, score
from src.analysis.scorers.execution import DEFAULT_METRIC_VERSION
from src.core.contracts.golden import GoldenCase
from src.core.contracts.task import Task
from src.core.contracts.trace import ExecutionTrace

__all__ = ["ScoreCompletedExecution"]


class ScoreCompletedExecution:
    """Hook injetável no worker, executado somente depois do fechamento da task."""

    def __init__(
        self,
        golden_for: Callable[[Task], GoldenCase],
        repository: MetricSQLiteRepository,
        *,
        metric_version: str = DEFAULT_METRIC_VERSION,
    ) -> None:
        self.golden_for = golden_for
        self.repository = repository
        self.metric_version = metric_version

    def __call__(self, task: Task, trace: ExecutionTrace) -> None:
        golden = self.golden_for(task)
        metrics = score(trace, golden, version=self.metric_version)
        self.repository.save(metrics)
