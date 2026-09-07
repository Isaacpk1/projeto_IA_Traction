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

__all__ = [
    "COLUNAS_BASE",
    "ExecutionRow",
    "load_execution_details",
    "load_executions",
    "load_frame",
]

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


def _resumo(valor: object, limite: int = 260) -> str:
    """Recorta o retorno de uma tool para caber na página sem virar dump."""
    texto = json.dumps(valor, ensure_ascii=False) if not isinstance(valor, str) else valor
    return texto if len(texto) <= limite else texto[:limite] + "…"


def load_execution_details(
    traces_dir: str | Path,
    *,
    run_id: str | None = None,
    max_execucoes: int | None = None,
) -> list[dict]:
    """Trajetória completa de cada execução, para inspeção humana.

    É o que responde "por que o agente decidiu isso?" — a pergunta que o trace
    canônico sempre pôde responder e que nenhuma interface expunha. Os retornos
    de tool são recortados: a página serve para ler a trajetória, e o JSONL
    continua sendo a fonte íntegra.
    """
    from src.core.contracts.trace import ExecutionTrace
    from src.core.evidence import evidence_matches

    detalhes: list[dict] = []
    for trace_raw in _traces_finais(Path(traces_dir)):
        if run_id is not None and trace_raw.get("run_id") != run_id:
            continue
        trace = ExecutionTrace.model_validate(trace_raw)
        resolucao = trace.resolution
        entregue = trace_raw.get("delivered") or {}
        detalhes.append({
            "id": trace.execution_id,
            "case_id": trace.case_id,
            "arm": trace.arm,
            "architecture": trace.architecture,
            "seed": trace_raw.get("api_seed"),
            "repetition": trace.repetition,
            "error_class": trace.error_class,
            "stop_reason": trace.stop_reason,
            "llm_calls": trace.llm_calls,
            "tokens_in": trace.tokens_in,
            "duracao_s": round((trace.duration_ms or 0) / 1000, 1),
            # O veredito gravado é do matcher vigente **na hora da execução**. Depois de
            # corrigir a resolução de evidência, ele fica desatualizado — e mostrar um
            # bloqueio que já não se sustenta seria mentir sobre o estado atual. `v1_atual`
            # recomputa a checagem V1 contra o trace com o comparador de hoje.
            "guard": {
                "verdict": entregue.get("guardrail_verdict"),
                "failed": entregue.get("guardrail_failed_checks") or [],
                "decision": entregue.get("decision"),
                "v1_atual": (
                    all(evidence_matches(ref, trace) for ref in resolucao.evidence_cited)
                    if resolucao and resolucao.evidence_cited
                    else None
                ),
            },
            "passos": [
                {
                    "step": passo.step,
                    "agent": passo.agent,
                    "tool": passo.tool,
                    "args": passo.args,
                    "resultado": _resumo(passo.result) if passo.result is not None else None,
                    "erro": passo.error,
                    "reasoning": _resumo(passo.reasoning, 400) if passo.reasoning else None,
                }
                for passo in trace.steps
            ],
            "handoffs": [
                {
                    "de": h.from_agent,
                    "para": h.to_agent,
                    "apos_passo": h.after_step,
                    "payload": _resumo(h.payload, 500),
                }
                for h in (trace.handoffs or [])
            ],
            "resolucao": None if resolucao is None else {
                "decision": resolucao.decision,
                "justification": resolucao.justification,
                "action_taken": resolucao.action_taken,
                "unverified": list(resolucao.unverified or []),
                "conflicts": list(resolucao.conflicts or []),
                "evidencias": [
                    {
                        "tool": ref.tool, "field": ref.field,
                        "value": _resumo(ref.value, 120), "step": ref.step,
                        "resolve": evidence_matches(ref, trace),
                    }
                    for ref in (resolucao.evidence_cited or [])
                ],
            },
        })
        if max_execucoes is not None and len(detalhes) >= max_execucoes:
            break
    return detalhes
