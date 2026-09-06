"""Persistência append-only e versionada de métricas."""

from src.analysis.metrics_sqlite import MetricSQLiteRepository
from src.core.contracts.metrics import MetricResult


def _metric(version: str, value: float) -> MetricResult:
    return MetricResult(
        execution_id="exec",
        metric_id="M8",
        metric_version=version,
        value=value,
        detail={"proof": version},
    )


def test_repositorio_nao_sobrescreve_mesma_versao_e_preserva_nova(tmp_path):
    with MetricSQLiteRepository(tmp_path / "metrics.db") as repository:
        assert repository.save([_metric("1.0.0", 0.5)]) == 1
        assert repository.save([_metric("1.0.0", 1.0)]) == 0
        assert repository.save([_metric("1.1.0", 1.0)]) == 1

        stored = repository.for_execution("exec")

    assert [(item.metric_version, item.value) for item in stored] == [
        ("1.0.0", 0.5),
        ("1.1.0", 1.0),
    ]
    assert all(item.computed_at > 0 for item in stored)


def test_repositorio_preserva_na_sem_converter_em_zero(tmp_path):
    metric = MetricResult(
        execution_id="exec",
        metric_id="M14",
        metric_version="1.0.0",
        value=None,
        applicable=False,
        detail={"reason": "mono"},
    )
    with MetricSQLiteRepository(tmp_path / "metrics.db") as repository:
        repository.save([metric])
        stored = repository.for_metric("M14", "1.0.0")[0]

    assert not stored.applicable
    assert stored.value is None
