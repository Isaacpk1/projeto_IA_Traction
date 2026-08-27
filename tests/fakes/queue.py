"""Fila em memória — implementa a mesma porta que o adaptador SQLite.

Existe para testar o worker sem tocar disco. O comportamento de lease, expiração e
taxonomia de falhas é o mesmo; a diferença é só onde o estado vive — que é exatamente
a promessa de reversibilidade do ADR-10.
"""

from __future__ import annotations

import time

from src.core.contracts.task import Lease, Task
from src.core.errors import ErrorClass

__all__ = ["InMemoryQueue"]


class InMemoryQueue:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._paused = False

    def enqueue(self, tasks: list[Task]) -> int:
        inseridas = 0
        for t in tasks:
            if t.task_id in self._tasks:
                continue  # INSERT OR IGNORE — retomar == reenfileirar
            self._tasks[t.task_id] = t.model_copy(deep=True)
            inseridas += 1
        return inseridas

    def lease(
        self,
        worker: str,
        ttl: float,
        *,
        run_id: str | None = None,
        max_attempts: int = 3,
        now: float | None = None,
    ) -> Lease | None:
        agora = now if now is not None else time.time()

        # recupera leases expirados — o TTL é o mecanismo de detecção de worker morto
        for t in self._tasks.values():
            if t.state == "leased" and (t.lease_expires or 0) < agora:
                t.attempts += 1
                t.state = "failed" if t.attempts >= max_attempts else "pending"
                t.error_class = "infra"
                t.completed_at = agora if t.state == "failed" else None
                t.leased_by = None
                t.lease_expires = None

        if self._paused:
            return None

        candidatas = [
            t
            for t in self._tasks.values()
            if t.state == "pending"
            and t.attempts < max_attempts
            and (run_id is None or t.run_id == run_id)
        ]
        if not candidatas:
            return None

        candidatas.sort(key=lambda t: (t.attempts, -t.priority, t.received_at))
        alvo = candidatas[0]
        alvo.state = "leased"
        alvo.leased_by = worker
        alvo.lease_expires = agora + ttl
        return Lease(
            task=alvo.model_copy(deep=True),
            worker=worker,
            expires_at=agora + ttl,
            attempt=alvo.attempts + 1,
        )

    def complete(
        self,
        task_id: str,
        execution_id: str,
        *,
        worker: str | None = None,
        now: float | None = None,
    ) -> None:
        t = self._tasks[task_id]
        if t.state != "leased" or (worker is not None and t.leased_by != worker):
            raise RuntimeError(f"task não pertence ao worker: {task_id}")
        t.state = "done"
        t.execution_id = execution_id
        t.completed_at = now if now is not None else time.time()
        t.leased_by = None
        t.lease_expires = None

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
        t = self._tasks[task_id]
        if t.state != "leased" or (worker is not None and t.leased_by != worker):
            raise RuntimeError(f"task não pertence ao worker: {task_id}")
        t.error_class = error_class
        t.leased_by = None
        t.lease_expires = None

        if error_class == "budget":
            # ausência de recurso, não falha da task: não incrementa `attempts`
            t.state = "pending"
            return
        if error_class == "contract":
            t.state = "failed"
            t.execution_id = execution_id
            t.completed_at = now if now is not None else time.time()
            return
        if error_class == "behavior":
            t.state = "done"
            t.execution_id = execution_id
            t.completed_at = now if now is not None else time.time()
            return

        t.attempts += 1
        t.state = "failed" if t.attempts >= max_attempts else "pending"
        if t.state == "failed":
            t.completed_at = now if now is not None else time.time()

    def heartbeat(self, task_id: str, worker: str, ttl: float, *, now: float | None = None) -> bool:
        t = self._tasks.get(task_id)
        if not t or t.state != "leased" or t.leased_by != worker:
            return False
        t.lease_expires = (now if now is not None else time.time()) + ttl
        return True

    def pause_lease(self, paused: bool = True) -> None:
        self._paused = paused

    def counts(self, run_id: str | None = None) -> dict[str, int]:
        out = {"pending": 0, "leased": 0, "done": 0, "failed": 0}
        for t in self._tasks.values():
            if run_id is None or t.run_id == run_id:
                out[t.state] += 1
        return out

    def get(self, task_id: str) -> Task | None:
        t = self._tasks.get(task_id)
        return t.model_copy(deep=True) if t else None
