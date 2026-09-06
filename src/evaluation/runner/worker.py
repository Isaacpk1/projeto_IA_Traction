"""Worker único para tickets e casos experimentais (RF39)."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from src.core.contracts.golden import CaseInput
from src.core.contracts.resolution import ConfirmationPolicy
from src.core.contracts.task import Task
from src.core.contracts.trace import ExecutionTrace
from src.core.errors import ErrorClass, IsolationViolation, classify
from src.core.ids import new_ulid
from src.core.ports.architecture import Architecture, RunContext
from src.core.ports.queue import WorkQueue
from src.evaluation.runner.isolation_guard import IsolationGuard

__all__ = ["Worker"]

_ERROR_CLASSES = {"infra", "behavior", "contract", "budget"}


class Worker:
    """Compõe fila, projeção segura e Strategy sem ramificar por ``Task.kind``."""

    def __init__(
        self,
        queue: WorkQueue,
        load_case: Callable[[Task], CaseInput],
        architecture_for: Callable[[Task], Architecture],
        *,
        metadata_for: Callable[[Task], dict] | None = None,
        isolation_guard: IsolationGuard | None = None,
        dry_run: bool = False,
        dry_run_for: Callable[[Task], bool] | None = None,
        confirmation_policy: ConfirmationPolicy = "auto_refuse",
        confirmation_grants_for: Callable[[Task], set[str] | frozenset[str]] | None = None,
        on_completed: Callable[[Task, ExecutionTrace], None] | None = None,
    ) -> None:
        self.queue = queue
        self.load_case = load_case
        self.architecture_for = architecture_for
        self.metadata_for = metadata_for or (lambda task: {})
        self.isolation_guard = isolation_guard or IsolationGuard()
        self.dry_run = dry_run
        #: E2 põe `prompt_only` e `pre_action_guard` na mesma fila. Só o braço
        #: inseguro pode rodar dry-run, então a decisão é por tarefa, não por
        #: worker — senão seriam dois processos drenando a mesma fila.
        self.dry_run_for = dry_run_for or (lambda task: self.dry_run)
        self.confirmation_policy = confirmation_policy
        self.confirmation_grants_for = confirmation_grants_for or (lambda task: frozenset())
        self.on_completed = on_completed
        self.post_completion_failures: list[tuple[str, Exception]] = []
        self._leased_last_call = False

    async def run_once(
        self,
        worker_id: str,
        *,
        ttl: float = 300,
        run_id: str | None = None,
        max_attempts: int = 3,
        now: float | None = None,
    ) -> ExecutionTrace | None:
        self._leased_last_call = False
        lease = self.queue.lease(
            worker_id,
            ttl,
            run_id=run_id,
            max_attempts=max_attempts,
            now=now,
        )
        if lease is None:
            return None
        self._leased_last_call = True

        task = lease.task
        execution_id = new_ulid()
        try:
            case = self.load_case(task)
            self.isolation_guard.check(case)
            architecture = self.architecture_for(task)
            context = RunContext(
                execution_id=execution_id,
                task_id=task.task_id,
                run_id=task.run_id,
                arm=task.arm,
                seed=task.seed,
                repetition=task.repetition,
                dry_run=self.dry_run_for(task),
                confirmation_policy=self.confirmation_policy,
                confirmation_grants=self.confirmation_grants_for(task),
                metadata=self.metadata_for(task),
            )
            with self.isolation_guard.protect_filesystem():
                trace = await architecture.run(case, context)
            if trace.error_class is None:
                self.queue.complete(task.task_id, execution_id, worker=worker_id, now=now)
                self._after_completion(task, trace)
            else:
                error_class = self._error_class(trace.error_class)
                self.queue.fail(
                    task.task_id,
                    error_class,
                    execution_id=execution_id,
                    worker=worker_id,
                    now=now,
                    max_attempts=max_attempts,
                )
                if error_class == "budget":
                    self.queue.pause_lease()
                elif error_class == "behavior":
                    self._after_completion(task, trace)
            return trace
        except Exception as exc:
            error_class = classify(exc)
            self.queue.fail(
                task.task_id,
                error_class,
                execution_id=execution_id,
                worker=worker_id,
                now=now,
                max_attempts=max_attempts,
            )
            if error_class == "budget":
                self.queue.pause_lease()
            if isinstance(exc, IsolationViolation):
                raise
            return None

    def _after_completion(self, task: Task, trace: ExecutionTrace) -> None:
        """Executa integrações derivadas sem invalidar uma execução persistida."""
        if self.on_completed is None:
            return
        try:
            self.on_completed(task, trace)
        except Exception as exc:
            self.post_completion_failures.append((trace.execution_id, exc))

    async def run_until_empty(
        self,
        worker_id: str,
        *,
        ttl: float = 300,
        run_id: str | None = None,
        max_attempts: int = 3,
        max_tasks: int | None = None,
    ) -> int:
        processed = 0
        while max_tasks is None or processed < max_tasks:
            trace = await self.run_once(
                worker_id,
                ttl=ttl,
                run_id=run_id,
                max_attempts=max_attempts,
            )
            if trace is None and not self._leased_last_call:
                break
            processed += 1
        return processed

    @staticmethod
    def _error_class(value: str) -> ErrorClass:
        if value not in _ERROR_CLASSES:
            return "contract"
        return cast(ErrorClass, value)
