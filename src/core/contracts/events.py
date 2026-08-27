"""Eventos de execução para SSE — doc 09 §8.2.

Definidos aqui, no núcleo, porque o front e o BFF são construídos contra este schema. Os
tipos TypeScript do front são gerados a partir destes modelos, o que mantém os dois
lados em sincronia (RNF13).

`precondition_checked` existe para que o front destaque a verificação de pré-condições —
o comportamento central de H1 — sem precisar reinterpretar o trace.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from src.core.contracts.resolution import Decision, EvidenceRef
from src.core.contracts.trace import Architecture

__all__ = ["ExecutionEvent", "EVENT_TYPES"]


class _Base(BaseModel):
    seq: int = Field(default=0, description="Ordinal na execução — vira o Last-Event-ID do SSE")
    execution_id: str = ""


class Started(_Base):
    type: Literal["started"] = "started"
    case_id: str
    architecture: Architecture
    model: str


class AgentEnter(_Base):
    type: Literal["agent_enter"] = "agent_enter"
    agent: str
    tools_available: list[str] = Field(default_factory=list)


class Thinking(_Base):
    type: Literal["thinking"] = "thinking"
    agent: str
    step: int
    text: str


class ToolCallEvent(_Base):
    type: Literal["tool_call"] = "tool_call"
    agent: str
    step: int
    call_id: str
    tool: str
    args: dict = Field(default_factory=dict)


class ToolResultEvent(_Base):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    mode: str | None = None
    result: dict | None = None
    error: str | None = None
    latency_ms: float = 0.0


class HandoffEvent(_Base):
    type: Literal["handoff"] = "handoff"
    from_agent: str = Field(alias="from")
    to_agent: str = Field(alias="to")
    payload: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class PreconditionChecked(_Base):
    type: Literal["precondition_checked"] = "precondition_checked"
    kind: Literal["baseline", "data_quality", "model"]
    value: str
    source_step: int


class ConfirmationRequired(_Base):
    type: Literal["confirmation_required"] = "confirmation_required"
    tool: str
    args: dict = Field(default_factory=dict)
    consequence: str = ""


class ResolutionEvent(_Base):
    type: Literal["resolution"] = "resolution"
    decision: Decision
    justification: str
    evidence_cited: list[EvidenceRef] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)


class DeliveredEvent(_Base):
    type: Literal["delivered"] = "delivered"
    decision: Decision
    guardrail_verdict: Literal["pass", "blocked"]
    guardrail_failed_checks: list[str] = Field(default_factory=list)


class Finished(_Base):
    type: Literal["finished"] = "finished"
    stop_reason: str
    duration_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0


class ErrorEvent(_Base):
    type: Literal["error"] = "error"
    error_class: Literal["infra", "behavior", "contract", "budget"]
    message: str


ExecutionEvent = Annotated[
    Started
    | AgentEnter
    | Thinking
    | ToolCallEvent
    | ToolResultEvent
    | HandoffEvent
    | PreconditionChecked
    | ConfirmationRequired
    | ResolutionEvent
    | DeliveredEvent
    | Finished
    | ErrorEvent,
    Field(discriminator="type"),
]

EVENT_TYPES = (
    Started,
    AgentEnter,
    Thinking,
    ToolCallEvent,
    ToolResultEvent,
    HandoffEvent,
    PreconditionChecked,
    ConfirmationRequired,
    ResolutionEvent,
    DeliveredEvent,
    Finished,
    ErrorEvent,
)
