"""Handoff tipado entre agentes — doc 05 §4.2, ADR-05.

Princípio P3: transferência entre agentes carrega objeto validado, nunca prosa.
Resumo em linguagem natural reintroduziria alucinação exatamente na fronteira que a
hipótese H1 investiga.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.core.contracts.resolution import EvidenceRef, Finding

BaselineState = Literal["learning", "established", "invalidated", "not_applicable", "unknown"]
DetectionMode = Literal["baseline", "symptom", "unknown"]
Confidence = Literal["high", "medium", "low"]

__all__ = [
    "BaselineState",
    "DetectionMode",
    "Confidence",
    "RoutingDecision",
    "ContextReport",
    "InvestigationReport",
    "ActionReport",
]

Specialist = Literal["contextualizer", "investigator", "executor"]


class RoutingDecision(BaseModel):
    """Orquestrador → grafo: classificação e especialistas necessários."""

    modality: Literal["context", "investigation", "action"]
    specialists: list[Specialist] = Field(min_length=1)
    rationale: str = Field(min_length=10)

    @model_validator(mode="after")
    def validate_route(self) -> RoutingDecision:
        if len(self.specialists) != len(set(self.specialists)):
            raise ValueError("a rota não pode repetir especialistas")
        if "executor" in self.specialists and "investigator" not in self.specialists:
            raise ValueError("o Executor exige investigação prévia")
        if self.modality == "action" and "executor" not in self.specialists:
            raise ValueError("modalidade action exige o Executor")
        return self


class ContextReport(BaseModel):
    """Contextualizador → Orquestrador."""

    company_segment: str | None = None
    asset_criticality: str | None = None
    user_role: str | None = None
    user_permissions: list[str] = Field(default_factory=list)
    glossary: list[str] = Field(
        default_factory=list, description="Termos de domínio resolvidos para o caso"
    )
    evidence: list[EvidenceRef] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)


class InvestigationReport(BaseModel):
    """Investigador → Orquestrador. O contrato mais consequente do projeto.

    Três campos carregam o peso:

    - `supported_by` (via `findings`) ancora cada afirmação num passo do trace;
    - `unverified` força a declaração de lacunas — quem omite produz lista vazia,
      e isso é mensurável (M9);
    - `data_quality_meets_requirements = None` distingue **não verificado** de
      **verificado e falso**. Um booleano simples perderia essa diferença, que é
      exatamente o objeto de H1.
    """

    findings: list[Finding] = Field(default_factory=list)
    baseline_state: BaselineState = "unknown"
    detection_mode: DetectionMode = "unknown"
    data_quality_meets_requirements: bool | None = Field(
        default=None, description="None = não verificado; False = verificado e insuficiente"
    )
    model_processing_state: str | None = None
    conflicts: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    confidence: Confidence = "low"

    def evidence_refs(self) -> list[EvidenceRef]:
        """Toda evidência citada no relatório, achatada — insumo de M14."""
        refs: list[EvidenceRef] = []
        for f in self.findings:
            refs.extend(f.supported_by)
            refs.extend(f.contradicted_by)
        return refs


class ActionReport(BaseModel):
    """Executor → Orquestrador."""

    attempted: bool = False
    tool: str | None = None
    succeeded: bool = False
    blocked_reason: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
