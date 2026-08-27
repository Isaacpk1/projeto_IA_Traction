"""Fila SQLite: idempotência, prioridade, lease e taxonomia de falhas."""

import pytest

from src.core.contracts.task import Task
from src.core.errors import ErrorClass
from src.evaluation.runner.queue_sqlite import SQLiteWorkQueue


def _task(task_id: str, *, priority: int = 5, received_at: float = 1, run_id: str = "r") -> Task:
    return Task(
        task_id=task_id,
        kind="experiment",
        case_id=f"case_{task_id}",
        architecture="mono",
        priority=priority,
        received_at=received_at,
        run_id=run_id,
    )


def test_enqueue_idempotente_e_ordem_de_lease(tmp_path) -> None:
    with SQLiteWorkQueue(tmp_path / "queue.db") as queue:
        tasks = [
            _task("low", priority=10, received_at=1),
            _task("critical", priority=40, received_at=2),
        ]
        assert queue.enqueue(tasks) == 2
        assert queue.enqueue(tasks) == 0

        lease = queue.lease("w1", 30, now=100)

        assert lease is not None and lease.task.task_id == "critical"
        assert lease.attempt == 1
        assert queue.counts() == {"pending": 1, "leased": 1, "done": 0, "failed": 0}


def test_lease_expirado_retorna_e_incrementa_tentativa(tmp_path) -> None:
    with SQLiteWorkQueue(tmp_path / "queue.db") as queue:
        queue.enqueue([_task("a")])
        first = queue.lease("dead", 10, now=100)
        second = queue.lease("replacement", 10, now=111)

        assert first is not None and second is not None
        assert second.task.task_id == "a"
        assert second.attempt == 2
        assert second.task.attempts == 1


def test_worker_antigo_nao_conclui_lease_reatribuido(tmp_path) -> None:
    with SQLiteWorkQueue(tmp_path / "queue.db") as queue:
        queue.enqueue([_task("a")])
        queue.lease("old", 10, now=100)
        replacement = queue.lease("new", 10, now=111)
        assert replacement is not None

        with pytest.raises(RuntimeError, match="leased"):
            queue.complete("a", "stale-execution", worker="old", now=112)

        queue.complete("a", "current-execution", worker="new", now=112)
        task = queue.get("a")
        assert task is not None and task.execution_id == "current-execution"


def test_filtro_de_run_pause_heartbeat_e_persistencia(tmp_path) -> None:
    path = tmp_path / "queue.db"
    with SQLiteWorkQueue(path) as queue:
        queue.enqueue([_task("a", run_id="r1"), _task("b", run_id="r2")])
        queue.pause_lease()
        assert queue.lease("w", 10, run_id="r2", now=1) is None
        queue.pause_lease(False)
        lease = queue.lease("w", 10, run_id="r2", now=1)
        assert lease is not None and lease.task.task_id == "b"
        assert not queue.heartbeat("b", "intruder", 10, now=2)
        assert queue.heartbeat("b", "w", 10, now=2)
        queue.complete("b", "exec_b", worker="w", now=3)

    with SQLiteWorkQueue(path) as reopened:
        task = reopened.get("b")
        assert task is not None and task.state == "done" and task.execution_id == "exec_b"


def test_taxonomia_define_destino_sem_contaminar_tentativas(tmp_path) -> None:
    with SQLiteWorkQueue(tmp_path / "queue.db") as queue:
        cases: list[tuple[str, ErrorClass]] = [
            ("budget", "budget"),
            ("contract", "contract"),
            ("behavior", "behavior"),
            ("infra", "infra"),
        ]
        queue.enqueue([_task(name, run_id=name) for name, _ in cases])
        for name, error_class in cases:
            lease = queue.lease("w", 10, run_id=name, now=1)
            assert lease is not None
            queue.fail(
                lease.task.task_id,
                error_class,
                execution_id=f"exec_{name}",
                worker="w",
                now=2,
                max_attempts=2,
            )

        budget = queue.get("budget")
        contract = queue.get("contract")
        behavior = queue.get("behavior")
        infra = queue.get("infra")
        assert budget is not None and budget.state == "pending" and budget.attempts == 0
        assert contract is not None and contract.state == "failed"
        assert behavior is not None and behavior.state == "done"
        assert infra is not None and infra.state == "pending" and infra.attempts == 1
