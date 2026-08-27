"""Porta da fila durável com lease — ADR-07, ADR-10.

Quatro requisitos que estavam especificados como mecanismos separados — checkpoint
(RF23), retry (RNF04), concorrência (RF22) e retomada (RNF03) — são a mesma coisa vista
de ângulos diferentes. Esta porta resolve os quatro.

O ADR-10 promete que trocar SQLite por Postgres não tocaria o runner. Sem esta porta,
essa promessa é falsa — e promessa arquitetural não verificável é pior que nenhuma.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.core.contracts.task import Lease, Task
from src.core.errors import ErrorClass

__all__ = ["WorkQueue"]


@runtime_checkable
class WorkQueue(Protocol):
    def enqueue(self, tasks: list[Task]) -> int:
        """Insere ignorando colisões de `task_id`. Retorna quantas foram de fato criadas.

        Reenfileirar o experimento inteiro é seguro: as tasks concluídas colidem e são
        ignoradas. Não existe lógica de "descobrir o que já fiz" — a restrição de
        unicidade é a lógica (doc 09 §4.4).
        """
        ...

    def lease(
        self,
        worker: str,
        ttl: float,
        *,
        run_id: str | None = None,
        max_attempts: int = 3,
        now: float | None = None,
    ) -> Lease | None:
        """Recupera leases expirados e reserva a próxima task, em uma transação.

        Ordem: `attempts ASC, priority DESC, received_at ASC` — tasks que nunca
        falharam primeiro (a execução não fica presa numa que falha sempre), depois
        criticidade do ativo (RF38), depois chegada (sem inanição).
        """
        ...

    def complete(self, task_id: str, execution_id: str, *, now: float | None = None) -> None: ...

    def fail(
        self,
        task_id: str,
        error_class: ErrorClass,
        *,
        execution_id: str | None = None,
        now: float | None = None,
    ) -> None:
        """Aplica a política da taxonomia (doc 09 §6).

        `budget` devolve a task a `pending` **sem incrementar `attempts`**: cota
        esgotada não é falha da task, é ausência de recurso. Contar como tentativa
        levaria tasks legítimas a `failed` por motivo alheio a elas.
        """
        ...

    def heartbeat(self, task_id: str, worker: str, ttl: float, *, now: float | None = None) -> bool:
        """Estende o lease de uma task em andamento."""
        ...

    def pause_lease(self, paused: bool = True) -> None:
        """Guarda de cota (RNF16): para de alocar trabalho e retoma no ciclo seguinte."""
        ...

    def counts(self, run_id: str | None = None) -> dict[str, int]:
        """Contagem por estado — alimenta o progresso da rodada no console."""
        ...
