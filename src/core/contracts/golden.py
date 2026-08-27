"""Golden dataset — doc 05 §6.

⚠️ **RNF02.** Os campos de gabarito nunca podem alcançar o agente: nem pelo prompt, nem
por resource, nem pelo sistema de arquivos visível ao processo. `CaseInput` é a projeção
segura — é o único modelo que atravessa a fronteira do agente e da API do BFF, e um
teste automatizado verifica a ausência dos campos privilegiados.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.core.contracts.resolution import Decision

DegradationModeGolden = Literal[
    "complete", "partial", "inconclusive", "conflict", "unavailable", "stale", "pending"
]

__all__ = [
    "DegradationModeGolden",
    "CaseInput",
    "ExpectedStep",
    "RequiredFact",
    "GoldenCase",
    "GOLDEN_ONLY_FIELDS",
]

#: Campos que jamais podem ser serializados para fora da camada de avaliação (RNF02).
GOLDEN_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "root_question",
        "degradation_mode",
        "degradation_probes",
        "expected_path",
        "expected_decision",
        "required_evidence",
        "forbidden_claims",
        "required_preconditions",
    }
)


class CaseInput(BaseModel):
    """O que o agente vê. Projeção segura de `GoldenCase` — não tem gabarito."""

    case_id: str
    ticket_id: str
    message: str
    company_id: str
    user_id: str
    asset_id: str


class ExpectedStep(BaseModel):
    """Um passo esperado da trajetória.

    `alternatives` existe porque RF05 verifica a **informação**, não a tool: o endpoint
    `/assets/{id}/rms` já devolve `baseline_state` e `alarm_threshold`, então um agente
    que obtém a pré-condição por essa via cumpriu o requisito. Exigir a tool específica
    mediria conformidade de trajetória, não disciplina de evidência.
    """

    tool: str
    alternatives: list[str] = Field(default_factory=list)
    required: bool = True
    args_contains: dict = Field(default_factory=dict)

    def satisfied_by(self, tool: str) -> bool:
        return tool == self.tool or tool in self.alternatives


class RequiredFact(BaseModel):
    """Um fato que precisa constar de algum retorno antes da conclusão (M5a).

    Descreve o fato e as fontes que podem comprová-lo; não obriga uma tool específica
    quando outra retorna a mesma evidência.
    """

    fact_id: str
    description: str
    sources: list[str] = Field(default_factory=list, description="Tools que podem comprovar o fato")
    field_paths: list[str] = Field(
        default_factory=list, description="Caminhos de campo aceitos, ex.: 'data.state'"
    )
    expected_values: list[str] = Field(
        default_factory=list, description="Vazio = qualquer valor comprova o fato"
    )


class GoldenCase(BaseModel):
    """Caso formalizado. Só a camada de avaliação e a de análise tocam este modelo."""

    case_id: str
    ticket_id: str
    source: Literal["base", "generated"] = "base"

    # --- entrada: o que o agente vê ----------------------------------------------
    message: str
    company_id: str
    user_id: str
    asset_id: str

    # --- gabarito: NUNCA visível ao agente (RNF02) --------------------------------
    root_question: str = ""
    degradation_mode: DegradationModeGolden = "complete"
    degradation_probes: list[ExpectedStep] = Field(
        default_factory=list,
        description="Conjunto fixo de consultas usado para medir intensidade antes da execução",
    )
    expected_path: list[ExpectedStep] = Field(default_factory=list)
    expected_decision: Decision = "orientar"
    required_evidence: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(
        default_factory=list, description="Ex.: 'ISO 10816' — formalização deste projeto"
    )
    required_preconditions: list[RequiredFact] = Field(default_factory=list)

    def to_input(self) -> CaseInput:
        """Projeção segura. É por aqui que um caso chega ao agente e ao BFF."""
        return CaseInput(
            case_id=self.case_id,
            ticket_id=self.ticket_id,
            message=self.message,
            company_id=self.company_id,
            user_id=self.user_id,
            asset_id=self.asset_id,
        )
