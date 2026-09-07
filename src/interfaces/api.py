"""BFF da plataforma — doc 11 §7 e doc 14 Fase 6, trilha B.

Serve o que o front precisa e **nada além**. Duas fronteiras que a camada
respeita porque o resto do sistema depende delas:

1. **O gabarito não atravessa a API (RNF02).** Casos são expostos pela projeção
   segura `CaseInput`; `expected_decision`, `expected_path` e `forbidden_claims`
   nunca são serializados. Um front que mostrasse o gabarito ao lado da execução
   tornaria qualquer demonstração inútil como evidência.
2. **A análise continua pura.** O BFF chama `analysis`, que lê apenas traces e
   SQLite. Nenhum número exibido é recalculado aqui.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.core.contracts.golden import CaseInput
from src.core.contracts.task import PRIORITY_BY_CRITICALITY, Task
from src.core.ids import new_ulid

__all__ = ["app", "criar_app"]

RAIZ = Path(__file__).resolve().parents[2]
TRACES = RAIZ / "artifacts" / "traces"
RUNS = RAIZ / "artifacts" / "runs"
FILA = RAIZ / "artifacts" / "queue.db"
INTENSIDADE = RAIZ / "src" / "evaluation" / "golden" / "degradation_intensity.json"

#: O recorte de E1 que a análise usa. Manter aqui evita que o front invente o seu.
E1_SEEDS_ANALISE = ("complete", "s10", "x1", "s13")

#: Rodadas de calibração e pilotos ficam fora da plataforma. Elas existem no disco
#: para auditoria, mas oferecê-las no seletor convida a ler resultado de configuração
#: que já foi descartada.
RODADAS_VISIVEIS = ("console2", "console", "e1_v1", "e2_v1")


class TicketNovo(BaseModel):
    """Chamado submetido pela interface — RF29."""

    case_id: str = Field(description="Caso do catálogo a atender")
    # A plataforma opera o mono-agente. O multi existe no experimento, e ali fica.
    architecture: str = Field(default="mono", pattern="^mono$")
    seed: str = Field(default="complete")
    criticality: str = Field(default="medium")


class TicketCriado(BaseModel):
    task_id: str
    case_id: str
    architecture: str
    seed: str
    priority: int
    state: str


def _sem_gabarito(golden: Any) -> dict:
    """Projeta o caso para o front. É a mesma fronteira que o agente enxerga."""
    entrada: CaseInput = golden.to_input()
    return {
        **entrada.model_dump(),
        "criticality": getattr(golden, "criticality", None),
        "case_type": golden.case_type,
    }


def criar_app() -> FastAPI:
    from src.analysis import load_frame
    from src.analysis.dataset import load_execution_details
    from src.analysis.report import montar_relatorio
    from src.analysis.triagem import anotar_triagem
    from src.evaluation.degradation import carregar_intensidade
    from src.evaluation.golden.loader import load_golden_dataset

    aplicacao = FastAPI(
        title="Plataforma de agentes industriais",
        version="0.1.0",
        description=(
            "Métricas, execuções e console de atendimento "
            "sobre os artefatos do experimento."
        ),
    )
    aplicacao.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    dataset = load_golden_dataset()
    por_id = dataset.by_id()
    intensidade = carregar_intensidade(INTENSIDADE) if INTENSIDADE.exists() else None
    cache: dict[str, Any] = {}

    def _metrics_db(run_id: str) -> Path:
        return RUNS / run_id / "metrics.db"

    def _quadro(run_id: str):
        df = load_frame(TRACES, _metrics_db(run_id), run_id=run_id, intensity=intensidade)
        if run_id.startswith("e1") and len(df):
            df = df[df["seed"].isin(E1_SEEDS_ANALISE) & (df["repetition"] == 0)]
        return df

    # ---- catálogo e rodadas ------------------------------------------------
    @aplicacao.get("/api/runs")
    def runs() -> list[dict]:
        """Rodadas com métricas disponíveis, mais recentes primeiro."""
        achadas = []
        for pasta in sorted(RUNS.glob("*")):
            if pasta.name not in RODADAS_VISIVEIS or not (pasta / "metrics.db").exists():
                continue
            traces = TRACES / pasta.name
            achadas.append({
                "run_id": pasta.name,
                "execucoes": len(list(traces.glob("*.jsonl"))) if traces.exists() else 0,
                # `startswith` e não `in`: "console2" contém "e2".
                "experimento": (
                    "Atendimento" if pasta.name.startswith("console")
                    else "E2" if pasta.name.startswith("e2") else "E1"
                ),
            })
        # Ordem do seletor = ordem de utilidade: a operação primeiro, o experimento depois.
        ordem = {nome: i for i, nome in enumerate(RODADAS_VISIVEIS)}
        return sorted(achadas, key=lambda r: ordem.get(r["run_id"], 99))

    @aplicacao.get("/api/cases")
    def cases() -> list[dict]:
        """Catálogo de chamados — projeção segura, sem gabarito (RNF02)."""
        return [_sem_gabarito(c) for c in (*dataset.base_cases(), *dataset.adversarial_cases())]

    # ---- métricas ----------------------------------------------------------
    @aplicacao.get("/api/report")
    def report(run_id: str = Query(...), e2_run_id: str | None = None) -> dict:
        chave = f"report:{run_id}:{e2_run_id}"
        if chave not in cache:
            e2 = _quadro(e2_run_id) if e2_run_id else None
            cache[chave] = montar_relatorio(_quadro(run_id), run_id=run_id, e2_df=e2)
        return cache[chave]

    # ---- execuções ---------------------------------------------------------
    @aplicacao.get("/api/executions")
    def executions(run_id: str = Query(...)) -> list[dict]:
        chave = f"exec:{run_id}"
        if chave not in cache:
            df = _quadro(run_id)
            vistos = set(df["execution_id"]) if len(df) else set()
            cache[chave] = anotar_triagem(
                [d for d in load_execution_details(TRACES, run_id=run_id) if d["id"] in vistos]
            )
        return cache[chave]

    @aplicacao.get("/api/executions/{execution_id}")
    def execution(execution_id: str, run_id: str = Query(...)) -> dict:
        for detalhe in executions(run_id=run_id):
            if detalhe["id"] == execution_id:
                return detalhe
        raise HTTPException(404, f"execução {execution_id} não encontrada em {run_id}")

    # ---- console de atendimento -------------------------------------------
    @aplicacao.get("/api/tickets")
    def tickets(run_id: str | None = None, limite: int = 200) -> list[dict]:
        """Fila de chamados com estado — a visão de produto, não de experimento."""
        from src.evaluation.runner.queue_sqlite import SQLiteWorkQueue

        if not FILA.exists():
            return []
        with SQLiteWorkQueue(FILA) as fila:
            conexao = fila._connection  # noqa: SLF001 — leitura de estado, sem escrita
            sql = (
                "SELECT task_id, kind, case_id, architecture, arm, seed, priority, state, "
                "attempts, execution_id, error_class, created_at, completed_at FROM tasks"
            )
            parametros: tuple = ()
            if run_id:
                sql += " WHERE run_id = ?"
                parametros = (run_id,)
            sql += " ORDER BY COALESCE(completed_at, created_at) DESC LIMIT ?"
            linhas = conexao.execute(sql, (*parametros, limite)).fetchall()
        return [dict(linha) for linha in linhas]

    @aplicacao.post("/api/tickets", response_model=TicketCriado, status_code=201)
    def criar_ticket(novo: TicketNovo) -> TicketCriado:
        """Enfileira um chamado — RF29. A execução é do worker, não do request."""
        from src.evaluation.runner.queue_sqlite import SQLiteWorkQueue

        if novo.case_id not in por_id:
            raise HTTPException(404, f"caso desconhecido: {novo.case_id}")
        tarefa = Task(
            task_id=new_ulid(),
            kind="ticket",
            case_id=novo.case_id,
            architecture=novo.architecture,  # type: ignore[arg-type]
            arm="A" if novo.architecture == "mono" else "B",
            seed=novo.seed,
            run_id="console",
            source="ui",
            priority=PRIORITY_BY_CRITICALITY.get(novo.criticality, 20),
            received_at=time.time(),
            created_at=time.time(),
        )
        FILA.parent.mkdir(parents=True, exist_ok=True)
        with SQLiteWorkQueue(FILA) as fila:
            fila.enqueue([tarefa])
        return TicketCriado(
            task_id=tarefa.task_id, case_id=tarefa.case_id, architecture=tarefa.architecture,
            seed=tarefa.seed or "complete", priority=tarefa.priority, state="pending",
        )

    return aplicacao


app = criar_app()
