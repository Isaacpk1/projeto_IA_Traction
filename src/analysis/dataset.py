"""Monta o quadro de análise a partir dos traces e das métricas — doc 11 §2.5.

Lê apenas JSONL e SQLite. Nenhum SDK de LLM, nenhuma chave de API, nenhum
import de `agents/`, `tools/` ou `evaluation/`: quem reproduz os resultados
precisa dos artefatos, não da máquina que os produziu. O `import-linter`
transforma essa promessa em contrato verificável.

Princípio A4 atravessa o módulo inteiro: `applicable=False` vira `NaN`, nunca
zero. Colapsar os dois premiaria a arquitetura mono em M14, que não tem
handoff para perder.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["ExecutionRow", "load_executions", "load_frame", "COLUNAS_BASE"]

#: Colunas que descrevem a execução; o resto do quadro é uma coluna por métrica.
COLUNAS_BASE = (
    "execution_id",
    "run_id",
    "case_id",
    "arm",
    "architecture",
    "seed",
    "repetition",
    "error_class",
    "stop_reason",
    "decision",
    "llm_calls",
    "tokens_in",
    "tokens_out",
    "duration_ms",
)


@dataclass(frozen=True)
class ExecutionRow:
    """Uma execução com suas métricas. `metrics[m] is None` significa não aplicável."""

    execution_id: str
    run_id: str | None
    case_id: str
    arm: str
    architecture: str
    seed: str | None
    repetition: int
    error_class: str | None
    stop_reason: str | None
    decision: str | None
    llm_calls: int
    tokens_in: int
    tokens_out: int
    duration_ms: float
    metrics: dict[str, float | None] = field(default_factory=dict)

    @property
    def concluiu(self) -> bool:
        """Execução que chegou ao fim sem erro — a base de qualquer taxa."""
        return self.error_class is None


def _traces_finais(raiz: Path) -> Iterator[dict]:
    """Devolve o último `execution_finished` de cada arquivo.

    O JSONL é append-only e o registro final é o trace completo; ler só ele evita
    reconstruir estado a partir dos passos.
    """
    for arquivo in sorted(raiz.rglob("*.jsonl")):
        final = None
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            registro = json.loads(linha)
            if registro.get("type") == "execution_finished":
                final = registro.get("trace")
        if final is not None:
            yield final


def _metricas(caminho: Path) -> dict[str, dict[str, float | None]]:
    if not caminho.exists():
        return {}
    conexao = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    conexao.row_factory = sqlite3.Row
    try:
        linhas = conexao.execute(
            "SELECT execution_id, metric_id, value, applicable FROM metrics"
        ).fetchall()
    finally:
        conexao.close()
    por_execucao: dict[str, dict[str, float | None]] = {}
    for linha in linhas:
        # A4: não aplicável entra como None e vira NaN no quadro — jamais zero.
        valor = linha["value"] if linha["applicable"] else None
        por_execucao.setdefault(linha["execution_id"], {})[linha["metric_id"]] = valor
    return por_execucao


def load_executions(
    traces_dir: str | Path,
    metrics_db: str | Path,
    *,
    run_id: str | None = None,
) -> list[ExecutionRow]:
    """Junta trace e métricas por `execution_id`."""
    por_execucao = _metricas(Path(metrics_db))
    linhas: list[ExecutionRow] = []
    for trace in _traces_finais(Path(traces_dir)):
        if run_id is not None and trace.get("run_id") != run_id:
            continue
        resolucao = trace.get("resolution") or {}
        execution_id = trace["execution_id"]
        linhas.append(
            ExecutionRow(
                execution_id=execution_id,
                run_id=trace.get("run_id"),
                case_id=trace["case_id"],
                arm=trace.get("arm", ""),
                architecture=trace.get("architecture", ""),
                seed=trace.get("api_seed") or trace.get("seed"),
                repetition=int(trace.get("repetition", 0)),
                error_class=trace.get("error_class"),
                stop_reason=trace.get("stop_reason"),
                decision=resolucao.get("decision"),
                llm_calls=int(trace.get("llm_calls", 0)),
                tokens_in=int(trace.get("tokens_in", 0)),
                tokens_out=int(trace.get("tokens_out", 0)),
                duration_ms=float(trace.get("duration_ms", 0.0)),
                metrics=por_execucao.get(execution_id, {}),
            )
        )
    return linhas


def load_frame(
    traces_dir: str | Path,
    metrics_db: str | Path,
    *,
    run_id: str | None = None,
    intensity: dict[tuple[str, str], float] | None = None,
):
    """Quadro pandas com uma linha por execução e uma coluna por métrica.

    `intensity` mapeia `(case_id, seed)` para a intensidade de degradação exógena
    — doc 07 §3.1. Ela é preditora de P1.1 e **não** pode ser derivada do que o
    agente chamou: isso deixaria a arquitetura alterar a própria variável
    explicativa. Por isso entra por fora, calculada antes ou depois, nunca a
    partir do trace.
    """
    import pandas as pd

    linhas = load_executions(traces_dir, metrics_db, run_id=run_id)
    if not linhas:
        return pd.DataFrame(columns=list(COLUNAS_BASE))

    metricas = sorted({m for linha in linhas for m in linha.metrics})
    registros = []
    for linha in linhas:
        registro = {coluna: getattr(linha, coluna) for coluna in COLUNAS_BASE}
        for metrica in metricas:
            registro[metrica] = linha.metrics.get(metrica)
        if intensity is not None:
            registro["intensidade"] = intensity.get((linha.case_id, linha.seed or ""))
        registros.append(registro)
    return pd.DataFrame.from_records(registros)
