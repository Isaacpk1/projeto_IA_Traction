"""M12 e M13 sobre repetições da mesma célula experimental."""

from __future__ import annotations

from collections import Counter
from itertools import combinations

from src.analysis.scorers.execution import DEFAULT_METRIC_VERSION
from src.core.contracts.metrics import MetricResult
from src.core.contracts.trace import ExecutionTrace

__all__ = ["score_stability"]


def _lcs(left: list[str], right: list[str]) -> int:
    row = [0] * (len(right) + 1)
    for item in left:
        previous = 0
        for index, other in enumerate(right, start=1):
            old = row[index]
            row[index] = previous + 1 if item == other else max(row[index], row[index - 1])
            previous = old
    return row[-1]


def _similarity(left: list[str], right: list[str]) -> float:
    denominator = max(len(left), len(right))
    return _lcs(left, right) / denominator if denominator else 1.0


def score_stability(
    traces: list[ExecutionTrace], version: str = DEFAULT_METRIC_VERSION
) -> list[MetricResult]:
    if len(traces) < 2:
        return []
    cells = {(trace.case_id, trace.architecture, trace.api_seed, trace.arm) for trace in traces}
    if len(cells) != 1:
        raise ValueError("M12/M13 exigem repetições da mesma célula experimental")

    decisions = [
        trace.resolution.decision if trace.resolution else "sem_resolucao" for trace in traces
    ]
    modal, count = Counter(decisions).most_common(1)[0]
    decision_stability = count / len(traces)
    trajectories = [trace.tools_called() for trace in traces]
    similarities = [_similarity(left, right) for left, right in combinations(trajectories, 2)]
    trajectory_stability = sum(similarities) / len(similarities)

    results: list[MetricResult] = []
    for trace in traces:
        results.extend(
            [
                MetricResult(
                    execution_id=trace.execution_id,
                    metric_id="M12",
                    metric_version=version,
                    value=decision_stability,
                    detail={"modal": modal, "count": count, "repetitions": len(traces)},
                ),
                MetricResult(
                    execution_id=trace.execution_id,
                    metric_id="M13",
                    metric_version=version,
                    value=trajectory_stability,
                    detail={"pairwise": similarities, "repetitions": len(traces)},
                ),
            ]
        )
    return results
