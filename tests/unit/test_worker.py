"""Worker compartilhado, retomada e isolamento do gabarito."""

from __future__ import annotations

import pytest

from src.core.contracts.golden import CaseInput, GoldenCase
from src.core.contracts.task import Task
from src.core.contracts.trace import ExecutionTrace
from src.core.errors import IsolationViolation
from src.core.ports.architecture import RunContext
from src.evaluation.runner.isolation_guard import IsolationGuard
from src.evaluation.runner.queue_sqlite import SQLiteWorkQueue
from src.evaluation.runner.worker import Worker
from tests.fakes.queue import InMemoryQueue


def _task(task_id: str, kind: str = "experiment") -> Task:
    return Task(
        task_id=task_id,
        kind=kind,
        case_id=f"case_{task_id}",
        architecture="mono",
        run_id="run",
    )


def _case(task: Task) -> CaseInput:
    return CaseInput(
        case_id=task.case_id,
        ticket_id=f"ticket_{task.task_id}",
        message="investigue",
        company_id="company",
        user_id="user",
        asset_id="asset",
    )


class _Architecture:
    name = "mono"

    def __init__(self, errors: list[str | None] | None = None) -> None:
        self.errors = list(errors or [])
        self.calls: list[tuple[CaseInput, RunContext]] = []

    async def run(self, case: CaseInput, ctx: RunContext) -> ExecutionTrace:
        self.calls.append((case, ctx))
        error = self.errors.pop(0) if self.errors else None
        return ExecutionTrace(
            run_id=ctx.run_id,
            task_id=ctx.task_id,
            execution_id=ctx.execution_id,
            case_id=case.case_id,
            architecture="mono",
            arm=ctx.arm,
            error_class=error,
            stop_reason="error" if error else "sufficient",
        )


async def test_ticket_e_experimento_percorrem_o_mesmo_worker():
    queue = InMemoryQueue()
    queue.enqueue([_task("experiment"), _task("ticket", "ticket")])
    architecture = _Architecture()
    worker = Worker(queue, _case, lambda task: architecture)

    assert await worker.run_until_empty("w") == 2

    assert [case.case_id for case, _ in architecture.calls] == [
        "case_experiment",
        "case_ticket",
    ]
    assert queue.counts() == {"pending": 0, "leased": 0, "done": 2, "failed": 0}


async def test_hook_pos_conclusao_nao_invalida_execucao_quando_falha():
    queue = InMemoryQueue()
    queue.enqueue([_task("scoring")])

    def broken_hook(task: Task, trace: ExecutionTrace) -> None:
        raise RuntimeError("scoring indisponível")

    worker = Worker(queue, _case, lambda task: _Architecture(), on_completed=broken_hook)

    trace = await worker.run_once("w")

    task = queue.get("scoring")
    assert trace is not None
    assert task is not None and task.state == "done"
    assert len(worker.post_completion_failures) == 1
    failed_execution, failure = worker.post_completion_failures[0]
    assert failed_execution == trace.execution_id
    assert str(failure) == "scoring indisponível"


async def test_hook_pontua_falha_de_comportamento_mas_nao_falha_de_infra():
    queue = InMemoryQueue()
    queue.enqueue([_task("behavior"), _task("infra")])
    architecture = _Architecture(["behavior", "infra"])
    completed: list[str] = []
    worker = Worker(
        queue,
        _case,
        lambda task: architecture,
        on_completed=lambda task, trace: completed.append(trace.error_class or "success"),
    )

    behavior = await worker.run_once("w")
    infra = await worker.run_once("w")

    assert behavior is not None and behavior.error_class == "behavior"
    assert infra is not None and infra.error_class == "infra"
    assert completed == ["behavior"]


async def test_falha_de_infra_retorna_a_fila_e_usa_novo_execution_id():
    queue = InMemoryQueue()
    queue.enqueue([_task("retry")])
    architecture = _Architecture(["infra", None])
    worker = Worker(queue, _case, lambda task: architecture)

    first = await worker.run_once("w1")
    second = await worker.run_once("w2")

    assert first is not None and first.error_class == "infra"
    assert second is not None and second.error_class is None
    assert first.execution_id != second.execution_id
    task = queue.get("retry")
    assert task is not None and task.state == "done" and task.attempts == 1


async def test_cota_esgotada_pausa_novos_leases_sem_consumir_tentativa():
    queue = InMemoryQueue()
    queue.enqueue([_task("quota"), _task("waiting")])
    worker = Worker(queue, _case, lambda task: _Architecture(["budget"]))

    trace = await worker.run_once("w")
    next_trace = await worker.run_once("w")

    assert trace is not None and trace.error_class == "budget"
    assert next_trace is None
    task = queue.get("quota")
    assert task is not None and task.state == "pending" and task.attempts == 0


async def test_isolation_guard_aborta_ao_receber_golden_case():
    queue = InMemoryQueue()
    queue.enqueue([_task("leak")])
    golden = GoldenCase(
        case_id="case_leak",
        ticket_id="ticket",
        message="x",
        company_id="company",
        user_id="user",
        asset_id="asset",
        expected_decision="escalar",
    )
    worker = Worker(queue, lambda task: golden, lambda task: _Architecture())  # type: ignore[arg-type]

    try:
        await worker.run_once("w")
    except IsolationViolation as exc:
        assert "expected_decision" in str(exc)
    else:
        raise AssertionError("IsolationViolation não foi levantada")

    task = queue.get("leak")
    assert task is not None and task.state == "failed" and task.error_class == "contract"


async def test_isolation_guard_bloqueia_leitura_de_arquivo_durante_turno(tmp_path):
    secret = tmp_path / "expected-paths.json"
    secret.write_text('{"answer": "segredo"}', encoding="utf-8")
    queue = InMemoryQueue()
    queue.enqueue([_task("filesystem-leak")])

    class _LeakingArchitecture(_Architecture):
        async def run(self, case: CaseInput, ctx: RunContext) -> ExecutionTrace:
            secret.read_text(encoding="utf-8")
            return await super().run(case, ctx)

    worker = Worker(
        queue,
        _case,
        lambda task: _LeakingArchitecture(),
        isolation_guard=IsolationGuard([secret]),
    )

    with pytest.raises(IsolationViolation, match="acesso do agente"):
        await worker.run_once("w")

    task = queue.get("filesystem-leak")
    assert task is not None and task.state == "failed" and task.error_class == "contract"


async def test_vinte_casos_retomam_apos_interrupcao_sem_reprocessar(tmp_path):
    path = tmp_path / "queue.db"
    architecture = _Architecture()
    with SQLiteWorkQueue(path) as queue:
        queue.enqueue([_task(f"task_{index:02}") for index in range(20)])
        first_worker = Worker(queue, _case, lambda task: architecture)
        assert await first_worker.run_until_empty("w1", max_tasks=7) == 7

    with SQLiteWorkQueue(path) as reopened:
        second_worker = Worker(reopened, _case, lambda task: architecture)
        assert await second_worker.run_until_empty("w2") == 13
        assert reopened.counts() == {"pending": 0, "leased": 0, "done": 20, "failed": 0}

    assert len(architecture.calls) == 20
    assert len({context.task_id for _, context in architecture.calls}) == 20
