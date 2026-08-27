"""Resolução, evidência e entrega — doc 05 §6.

A separação entre `Resolution` (o que o agente decidiu) e `Delivered` (o que chegou ao
solicitante depois do guardrail) existe por causa do risco RA-08: as métricas leem
sempre `resolution`, nunca `delivered`. M16 mede o guardrail à parte.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["orientar", "agir", "escalar"]
GuardCheck = Literal["V1", "V2", "V3"]
PreActionCheck = Literal["permission", "confirmation", "evidence"]

__all__ = [
    "Decision",
    "GuardCheck",
    "PreActionCheck",
    "EvidenceRef",
    "Finding",
    "Resolution",
    "Delivered",
    "ActionAttempt",
]


class EvidenceRef(BaseModel):
    """Ancoragem de uma afirmação num passo concreto do trace (RF08).

    É Value Object: imutável e comparável por valor. É o que torna o *grounding
    check* (RF25/V1) uma verificação determinística, e não uma inspeção textual.
    """

    model_config = ConfigDict(frozen=True)

    tool: str = Field(description="Tool de origem do valor observado")
    field: str = Field(description="Caminho do campo no retorno, ex.: 'data.state'")
    value: str = Field(description="Valor observado, serializado como texto")
    step: int = Field(ge=0, description="Passo do trace que produziu o valor")


class Finding(BaseModel):
    """Uma afirmação com suas evidências de suporte e de contradição."""

    claim: str
    supported_by: list[EvidenceRef] = Field(default_factory=list)
    contradicted_by: list[EvidenceRef] = Field(default_factory=list)


class Resolution(BaseModel):
    """O que o AGENTE decidiu — cru, antes de qualquer verificação (RF11)."""

    decision: Decision
    justification: str
    evidence_cited: list[EvidenceRef] = Field(default_factory=list)
    unverified: list[str] = Field(
        default_factory=list,
        description="Lacunas declaradas (RF09). Vazio quando o agente omite o que não sabe.",
    )
    conflicts: list[str] = Field(
        default_factory=list, description="Divergências não resolvidas entre fontes (RF10)"
    )
    action_taken: str | None = None
    confirmation_requested: bool = False


class Delivered(BaseModel):
    """O que foi ENTREGUE ao solicitante — depois do `PreDeliveryGuard` (RF44)."""

    decision: Decision
    guardrail_verdict: Literal["pass", "blocked"]
    guardrail_failed_checks: list[GuardCheck] = Field(default_factory=list)
    guardrail_reason: str | None = None


class ActionAttempt(BaseModel):
    """Toda tentativa de tool `tier: impact`, tenha ela produzido efeito ou não.

    `external_call_emitted = False` com `pre_action_verdict = "blocked"` é a prova
    de que o `PreActionGuard` agiu antes do efeito externo (H2 / M10).
    """

    tool: str
    args: dict = Field(default_factory=dict)
    requested_at_step: int = Field(ge=0)
    pre_action_verdict: Literal["pass", "blocked", "dry_run"]
    failed_preconditions: list[PreActionCheck] = Field(default_factory=list)
    external_call_emitted: bool = False
