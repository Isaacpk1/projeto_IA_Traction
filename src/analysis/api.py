"""Superfície pública e pura da camada de análise.

Tudo aqui roda a partir dos artefatos — JSONL e SQLite — sem chave de API e sem
importar `agents/`, `tools/` ou `evaluation/`. É o que torna os resultados
reproduzíveis por quem tem os traces e não tem a máquina que os gerou.
"""

from src.analysis.dataset import ExecutionRow, load_executions, load_frame
from src.analysis.hypotheses import (
    MARGEM_NAO_INFERIORIDADE,
    TestResult,
    avaliar_h1_dose_resposta,
    avaliar_h2_tentativa_insegura,
    avaliar_h3_mcnemar,
    avaliar_h4_nao_inferioridade,
    bootstrap_por_caso,
    intervalo_binomial,
)
from src.analysis.scorers import score, score_stability

__all__ = [
    "MARGEM_NAO_INFERIORIDADE",
    "ExecutionRow",
    "TestResult",
    "avaliar_h1_dose_resposta",
    "avaliar_h2_tentativa_insegura",
    "avaliar_h3_mcnemar",
    "avaliar_h4_nao_inferioridade",
    "bootstrap_por_caso",
    "intervalo_binomial",
    "load_executions",
    "load_frame",
    "score",
    "score_stability",
]
