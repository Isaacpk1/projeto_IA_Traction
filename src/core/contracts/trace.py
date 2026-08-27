"""Trace de execução — doc 05 §6, princípio P4.

O trace é **dado experimental**, não log. E é o contrato entre as duas metades do
sistema (doc 11 §2.5): a camada de análise lê o trace persistido e nunca conversa com o
agente — por isso ela roda sem SDK de LLM, sem API no ar e sem cota.

`schema_version` existe porque a rodada piloto e a definitiva podem usar versões
diferentes, e traces antigos precisam continuar legíveis.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.core.contracts.resolution import ActionAttempt, Delivered, Resolution

TRACE_SCHEMA_VERSION = "1.0.0"

Architecture = Literal["mono", "multi"]
StopReason = Literal["sufficient", "max_steps", "error", "budget"]
DegradationMode = Literal["complete", "partial", "inconclusive", "conflict", "unavailable"]

__all__ = [
    "TRACE_SCHEMA_VERSION",
    "Architecture",
    "StopReason",
    "DegradationMode",
    "TraceStep",
    "Handoff",
    "ExecutionTrace",
]


class TraceStep(BaseModel):
    """Um passo do loop ReAct (RF17)."""

    step: int = Field(ge=0)
    agent: str = Field(description="Papel que executou o passo — 'agent' na arquitetura mono")
    reasoning: str | None = None
    tool: str | None = None
    args: dict | None = None
    result: dict | None = None
    error: str | None = None
    latency_ms: float = 0.0
    t_offset_ms: float = Field(default=0.0, description="Desde o início da execução")

    @property
    def mode(self) -> str | None:
        """Modo do envelope de consulta da API, quando presente.

        A API embrulha respostas de GET em `{status, data, mode, notes}`. É daqui que
        sai a intensidade de degradação — a variável independente contínua de H1.
        """
        if not self.result:
            return None
        value = self.result.get("mode")
        return value if isinstance(value, str) else None


class Handoff(BaseModel):
    """Transferência entre agentes (RF18). `payload` é um relatório tipado serializado."""

    after_step: int = Field(ge=0)
    from_agent: str
    to_agent: str
    payload: dict = Field(default_factory=dict)


class ExecutionTrace(BaseModel):
    """A unidade de dado experimental. Append-only: nada é reescrito (princípio O4)."""

    schema_version: str = TRACE_SCHEMA_VERSION

    run_id: str | None = None
    task_id: str
    execution_id: str
    case_id: str
    repetition: int = 0
    architecture: Architecture
    experiment_id: str | None = None
    arm: str = Field(description="A | B | C — braço experimental (doc 09 §3.3)")

    # --- metadados de reprodutibilidade (RNF15) ---------------------------------
    models_by_agent: dict[str, str] = Field(default_factory=dict)
    model_versions_by_agent: dict[str, str] = Field(default_factory=dict)
    provider_by_agent: dict[str, str] = Field(default_factory=dict)
    temperature: float = 0.0
    api_seed: str | None = None
    degradation_intensity: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Preditor exógeno calculado antes da execução sobre recursos fixos do caso",
    )
    prompt_version: str = "0"
    overlay_version: str = "0"
    tool_schema_version: str = "0"
    api_contract_version: str = "0"
    dataset_version: str = "0"
    code_commit: str = "unknown"

    # --- execução ----------------------------------------------------------------
    steps: list[TraceStep] = Field(default_factory=list)
    handoffs: list[Handoff] = Field(default_factory=list)
    action_attempts: list[ActionAttempt] = Field(default_factory=list)
    resolution: Resolution | None = None
    delivered: Delivered | None = None
    stop_reason: StopReason = "sufficient"
    duration_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    llm_calls: int = 0
    error_class: str | None = None

    # --- leituras derivadas ------------------------------------------------------

    def tools_called(self) -> list[str]:
        """Sequência de tools chamadas, na ordem — insumo de M1, M2 e M13."""
        return [s.tool for s in self.steps if s.tool]

    def api_modes_seen(self) -> list[str]:
        return [m for m in (s.mode for s in self.steps) if m]

    def observed_degradation_intensity(self) -> float | None:
        """Proporção observada de retornos consultados que não vieram completos.

        É diagnóstico da trajetória, não a variável independente de H1: como depende
        das tools escolhidas pelo agente, usá-la como preditor faria a arquitetura
        alterar o próprio eixo explicativo. H1 usa o campo `degradation_intensity`,
        calculado antes da execução sobre o conjunto fixo de recursos do caso.
        """
        modos = self.api_modes_seen()
        if not modos:
            return None
        return sum(1 for m in modos if m != "complete") / len(modos)
