"""Métricas, julgamentos e vereditos — doc 11 §3.

Princípio A4: **"não aplicável" nunca é zero.** Colapsar os dois cria vantagem
artificial na agregação — M14 em arquitetura mono viraria zero e premiaria quem não tem
handoff; M5a/M5b penalizariam o comportamento correto em detecção sintomática.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Verdict = Literal["true", "false", "not_applicable"]
HypothesisStatus = Literal["sustentada", "refutada", "inconclusiva", "nao_executada"]

__all__ = [
    "Verdict",
    "HypothesisStatus",
    "MetricResult",
    "Judgment",
    "HumanLabel",
    "HypothesisVerdict",
]


class MetricResult(BaseModel):
    """Resultado de um scorer. Value Object: imutável e comparável por valor.

    `applicable=False` exige `value=None` — a invariante que sustenta A4 no schema, e
    não apenas na disciplina de quem escreve o scorer.
    """

    model_config = ConfigDict(frozen=True)

    execution_id: str
    metric_id: str = Field(description="M1, M4, M5a, M5b, ...")
    metric_version: str = Field(description="semver da definição da métrica (A3)")
    value: float | None = None
    applicable: bool = True
    detail: dict = Field(
        default_factory=dict,
        description="A prova do cálculo: o que sustentou o valor. Auditável sem reabrir o trace.",
    )
    computed_at: float = 0.0

    @model_validator(mode="after")
    def _nao_aplicavel_nunca_e_zero(self) -> MetricResult:
        if not self.applicable and self.value is not None:
            raise ValueError(f"{self.metric_id}: applicable=False exige value=None (princípio A4)")
        if self.applicable and self.value is None:
            raise ValueError(f"{self.metric_id}: applicable=True exige um valor")
        return self


class Judgment(BaseModel):
    """Veredito do juiz LLM sobre um critério da rubrica (RF26).

    A chave `(execution_id, criterion_id, rubric_version, judge_model)` é o mecanismo de
    cache (RF36): rejulgar com a mesma rubrica e o mesmo juiz é `INSERT OR IGNORE` e não
    gasta cota; mudar a rubrica gera chave nova e força novo julgamento.
    """

    execution_id: str
    criterion_id: str = Field(description="C1..C8")
    rubric_version: str
    judge_model: str
    verdict: Verdict
    justification: str
    tokens: int = 0
    judged_at: float = 0.0


class HumanLabel(BaseModel):
    """Rotulação humana para a meta-avaliação do juiz (RF27).

    `labeled_before_results` é um compromisso auditável: a rotulação precisa acontecer
    **antes** de ver qualquer agregado, senão o viés de confirmação contamina a própria
    régua usada para validar o juiz.
    """

    execution_id: str
    criterion_id: str
    rubric_version: str
    verdict: Verdict
    labeled_at: float = 0.0
    labeled_before_results: bool = True


class HypothesisVerdict(BaseModel):
    """Resultado do teste de uma predição — doc 11 §6.

    `inconclusiva` é desfecho de primeira classe: quando os dados não sustentam
    veredito, a conclusão é essa, e não uma leitura favorável forçada.
    """

    hypothesis_id: str = Field(description="H1..H4")
    prediction_id: str = Field(description="P1.1, P2.2, ...")
    status: HypothesisStatus
    test: str = Field(description="Teste declarado antes da execução (princípio A5)")
    primary_metric: str
    estimate: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    p_value: float | None = None
    n_cases: int = 0
    n_executions: int = 0
    notes: str = ""
