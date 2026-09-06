"""Integração do caminho trace concluído → scoring → SQLite."""

from src.analysis import MetricSQLiteRepository
from src.core.contracts.golden import GoldenCase
from src.core.contracts.task import Task
from src.core.contracts.trace import ExecutionTrace
from src.core.ports.architecture import RunContext
from src.evaluation.runner.worker import Worker
from src.interfaces import ScoreCompletedExecution
from tests.fakes.queue import InMemoryQueue


def _task() -> Task:
    return Task(
        task_id="task_scoring",
        kind="experiment",
        case_id="case_scoring",
        architecture="mono",
        run_id="run_scoring",
    )


def _golden() -> GoldenCase:
    return GoldenCase(
        case_id="case_scoring",
        ticket_id="ticket_scoring",
        message="investigue",
        company_id="company",
        user_id="user",
        asset_id="asset",
        expected_decision="orientar",
    )


class _Architecture:
    name = "mono"

    async def run(self, case, ctx: RunContext) -> ExecutionTrace:
        return ExecutionTrace(
            run_id=ctx.run_id,
            task_id=ctx.task_id,
            execution_id=ctx.execution_id,
            case_id=case.case_id,
            architecture="mono",
            arm=ctx.arm,
            stop_reason="sufficient",
        )


async def test_worker_persiste_metricas_depois_de_concluir_task(tmp_path):
    queue = InMemoryQueue()
    task = _task()
    golden = _golden()
    queue.enqueue([task])

    with MetricSQLiteRepository(tmp_path / "metrics.db") as repository:
        hook = ScoreCompletedExecution(lambda leased: golden, repository)
        worker = Worker(
            queue,
            lambda leased: golden.to_input(),
            lambda leased: _Architecture(),
            on_completed=hook,
        )

        trace = await worker.run_once("worker")

        assert trace is not None
        metrics = repository.for_execution(trace.execution_id)

    assert queue.get(task.task_id).state == "done"
    assert len(metrics) == 15
    assert {metric.metric_id for metric in metrics} >= {"M1", "M4", "M15"}
