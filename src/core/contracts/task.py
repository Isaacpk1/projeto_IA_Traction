"""Unidade de trabalho da fila — doc 09 §4.

Padrão **Command**: a intenção é serializada e reexecutável, o que é a base da
idempotência. O mesmo modelo serve ticket de cliente e caso da suíte (RF39) — a
diferença mora em `kind`, e nenhum ramo condicional por `kind` existe dentro do agente.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.core.contracts.trace import Architecture

TaskKind = Literal["ticket", "experiment"]
TaskState = Literal["pending", "leased", "done", "failed"]
TaskSource = Literal["api", "ui", "batch", "cli"]

#: Prioridade derivada da criticidade do ativo (RF38). Maior vence no lease.
PRIORITY_BY_CRITICALITY: dict[str, int] = {
    "critical": 40,
    "high": 30,
    "medium": 20,
    "low": 10,
}

#: Tarefas de experimento recebem prioridade base e são drenadas quando não há
#: ticket de cliente aguardando (doc 09 §4.5).
EXPERIMENT_PRIORITY = 5

__all__ = [
    "TaskKind",
    "TaskState",
    "TaskSource",
    "PRIORITY_BY_CRITICALITY",
    "EXPERIMENT_PRIORITY",
    "Task",
    "Lease",
]


class Task(BaseModel):
    """Uma unidade de trabalho endereçável e idempotente (princípio O2)."""

    task_id: str
    kind: TaskKind
    case_id: str
    architecture: Architecture
    priority: int = EXPERIMENT_PRIORITY
    source: TaskSource = "batch"
    received_at: float = 0.0
    session_id: str | None = None
    run_id: str | None = None
    seed: str | None = None
    repetition: int = 0
    arm: str = "A"
    state: TaskState = "pending"
    attempts: int = 0
    leased_by: str | None = None
    lease_expires: float | None = None
    execution_id: str | None = None
    error_class: str | None = None
    created_at: float = 0.0
    completed_at: float | None = None


class Lease(BaseModel):
    """Reserva por prazo. O worker não remove a task — ele a reserva.

    É o que distingue esta fila de um checkpoint ingênuo: se o processo morrer no meio
    de uma execução, a reserva vence e a task retorna a `pending` sozinha. Um checkpoint
    que só registra conclusões deixaria essa task em limbo permanente.
    """

    task: Task
    worker: str
    expires_at: float
    attempt: int = Field(ge=1)
