"""Composition root do experimento — doc 14 Fase 6, trilha A.

Este é o único lugar do projeto onde SDK de LLM, HTTP, SQLite e disco se
encontram. Tudo abaixo recebe suas dependências por porta; é aqui que elas
ganham implementação concreta. Por isso `interfaces/` é a camada de topo do
contrato de camadas: ela pode conhecer todo mundo, e ninguém a conhece.

Uso típico:

    agentes plan  --run-id piloto --experiment e2      # enfileira
    agentes run   --run-id piloto --max-tasks 5        # drena
    agentes status --run-id piloto                     # confere

`plan` é idempotente: o `task_id` é hash da tupla de trabalho, então replanejar
depois de uma queda reenfileira só o que falta.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Annotated

import typer

from src.agents.architectures import MonoArchitecture, MultiArchitecture
from src.analysis import MetricSQLiteRepository
from src.core.contracts.golden import CaseInput, GoldenCase
from src.core.contracts.task import Task
from src.core.contracts.trace import ExecutionTrace
from src.core.errors import ContractError
from src.core.ports.architecture import Architecture as ArchitecturePort
from src.core.ports.llm import LLMClient
from src.evaluation.degradation import (
    IntensityTable,
    intensidade,
    salvar_intensidade,
)
from src.evaluation.golden.loader import GoldenDataset, load_golden_dataset
from src.evaluation.matrix import E1_SEEDS, E2_POLICIES, plan_core, plan_e1, plan_e2
from src.evaluation.runner.queue_sqlite import SQLiteWorkQueue
from src.evaluation.runner.rate_limiter import LocalRateLimiter
from src.evaluation.runner.worker import Worker
from src.interfaces.scoring import ScoreCompletedExecution
from src.llm.gemini import GeminiClient
from src.storage.jsonl_traces import JsonlTraceSink
from src.tools.core.http_executor import HttpExecutor
from src.tools.provider import ApiToolProvider, DryRunToolProvider, build_registry

__all__ = ["app", "main", "build_architecture"]

app = typer.Typer(
    add_completion=False,
    help="Runner do experimento A/B de arquiteturas de agente.",
    no_args_is_help=True,
)

RAIZ = Path(__file__).resolve().parents[2]
MATERIAL = RAIZ / "inteli-tractian-project" / "agent-input"

DEFAULT_QUEUE = RAIZ / "artifacts" / "queue.db"
DEFAULT_METRICS = RAIZ / "artifacts" / "metrics.db"
DEFAULT_TRACES = RAIZ / "artifacts" / "traces"
DEFAULT_QUOTA = RAIZ / "artifacts" / "quota.db"
DEFAULT_INTENSITY = RAIZ / "src" / "evaluation" / "golden" / "degradation_intensity.json"
DEFAULT_DASHBOARD = RAIZ / "artifacts" / "dashboard.html"

#: Único modelo de diagnóstico da API; não há endpoint que os liste.
MODELO_DE_VIBRACAO = "mdl_vib_v3"


#: Valor que `.env.example` traz. Deixá-lo passar produz um erro de autenticação
#: do SDK a 594 tarefas de distância; recusar aqui custa uma linha.
_PLACEHOLDER = "cole-sua-chave-aqui"


def _dataset() -> GoldenDataset:
    return load_golden_dataset()


def _api_key() -> str:
    """Carrega o `.env` da raiz e devolve a chave — o shell continua vencendo."""
    env_file = RAIZ / ".env"
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file)
    chave = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
    if not chave or chave == _PLACEHOLDER:
        raise typer.BadParameter(
            f"defina GEMINI_API_KEY em {env_file} — sem chave real o runner não executa"
        )
    return chave


def _code_commit() -> str:
    """Amarra cada trace ao código que o produziu — sem isso não há reprodução."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


MULTI_ROLES = ("orchestrator", "contextualizer", "investigator", "executor")


def build_architecture(
    task: Task,
    *,
    llm: LLMClient,
    provider: ApiToolProvider,
    sink: JsonlTraceSink,
) -> ArchitecturePort:
    """Traduz o braço declarado na matriz para a Strategy que o realiza.

    É a única lógica de verdade da CLI, e por isso mora fora do closure de
    `_drain`: o mapeamento braço → arquitetura é o que faz H1 e H2 medirem o
    que dizem medir, e precisa ser asserção de teste, não confiança.
    """
    if task.arm == "prompt_only":
        # Braço inseguro de E2: mede tentativa, nunca efeito. O provider dry-run
        # é pré-condição estrutural, não configuração (doc 07 §E2) — o próprio
        # MonoArchitecture recusa desabilitar o guard sem ele.
        return MonoArchitecture(
            llm,
            DryRunToolProvider(provider),
            sink,
            enforce_pre_action_guard=False,
        )
    if task.architecture == "multi":
        return MultiArchitecture({papel: llm for papel in MULTI_ROLES}, provider, sink)
    return MonoArchitecture(llm, provider, sink)


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------
@app.command()
def plan(
    run_id: Annotated[str, typer.Option(help="Identificador da rodada.")],
    experiment: Annotated[
        str, typer.Option(help="core (E1+E2), e1 ou e2.")
    ] = "core",
    db: Annotated[Path, typer.Option(help="Fila SQLite.")] = DEFAULT_QUEUE,
) -> None:
    """Materializa a matriz declarada em doc 07 na fila."""
    dataset = _dataset()
    escolha = experiment.lower()
    if escolha == "core":
        tasks = plan_core(dataset.base_cases(), dataset.adversarial_cases(), run_id=run_id)
    elif escolha == "e1":
        tasks = plan_e1(dataset.base_cases(), run_id=run_id)
    elif escolha == "e2":
        tasks = plan_e2(dataset.adversarial_cases(), run_id=run_id)
    else:
        raise typer.BadParameter(f"experimento desconhecido: {experiment}")

    db.parent.mkdir(parents=True, exist_ok=True)
    with SQLiteWorkQueue(db) as queue:
        inseridas = queue.enqueue(tasks)
        counts = queue.counts(run_id)

    repetidas = len(tasks) - inseridas
    typer.echo(f"planejadas {len(tasks)} · novas {inseridas} · já existentes {repetidas}")
    typer.echo(f"fila em {db} · {counts}")


# ---------------------------------------------------------------------------
# intensity
# ---------------------------------------------------------------------------
async def _sondar(provider: ApiToolProvider, golden, seed: str) -> list[str]:
    """Observa o modo de cada recurso relevante do caso sob um seed.

    Usa `degradation_probes` — o conjunto fixo declarado no golden — e nunca as
    tools que o agente chamou. É o que mantém a variável exógena.
    """
    provider.default_user_id = golden.user_id
    provider.default_seed = seed
    modos: list[str] = []
    analysis_id: str | None = None
    for passo in golden.degradation_probes:
        argumentos = _args_da_probe(passo.tool, golden, analysis_id)
        if argumentos is None:
            continue
        resultado = await provider.call(passo.tool, argumentos, call_id=passo.tool, seed=seed)
        payload = resultado.data or {}
        if not resultado.ok:
            # Recurso que não responde é ausência de evidência, por definição.
            modos.append("unavailable")
            continue
        modos.append(str(payload.get("mode", "complete")))
        if passo.tool == "listAnalyses" and analysis_id is None:
            analises = (payload.get("data") or {}).get("analyses") or []
            if analises:
                analysis_id = analises[0].get("id")
    return modos


def _args_da_probe(tool: str, golden, analysis_id: str | None) -> dict | None:
    if tool in {"getAsset", "listAnalyses", "getBaseline", "getRmsSeries",
                "getSpectrum", "getDataQuality"}:
        return {"assetId": golden.asset_id}
    if tool == "getAnalysis":
        return {"analysisId": analysis_id} if analysis_id else None
    if tool == "getModel":
        return {"modelId": MODELO_DE_VIBRACAO}
    if tool == "searchKnowledge":
        return {"q": golden.root_question or golden.message[:60]}
    return None


@app.command()
def intensity(
    out: Annotated[Path, typer.Option(help="Tabela versionada de saída.")] = DEFAULT_INTENSITY,
    api_url: Annotated[str, typer.Option(help="API industrial.")] = "http://127.0.0.1:8000",
) -> None:
    """Calcula a intensidade de degradação de cada par caso-seed — doc 07 §3.1.

    Não gasta cota de LLM: só conversa com a API local. Pode rodar com o
    experimento em andamento, porque não toca em nada que o agente use.
    """
    total = asyncio.run(_medir_intensidade(out=out, api_url=api_url))
    typer.echo(f"{total} pares caso-seed gravados em {out}")


async def _medir_intensidade(*, out: Path, api_url: str) -> int:
    dataset = _dataset()
    registry, overlay = build_registry(MATERIAL / "api-contract.openapi.yaml")
    tabela: IntensityTable = {}
    detalhe: dict[tuple[str, str], list[str]] = {}
    async with HttpExecutor(api_url) as executor:
        provider = ApiToolProvider(registry, executor, overlay=overlay)
        for golden in dataset.base_cases():
            if not golden.degradation_probes:
                continue
            for seed in E1_SEEDS:
                modos = await _sondar(provider, golden, seed)
                if not modos:
                    continue
                chave = (golden.case_id, seed)
                tabela[chave] = intensidade(modos)
                detalhe[chave] = modos
    return salvar_intensidade(out, tabela, detalhe=detalhe)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
@app.command()
def status(
    run_id: Annotated[str | None, typer.Option(help="Rodada; omita para o total.")] = None,
    db: Annotated[Path, typer.Option(help="Fila SQLite.")] = DEFAULT_QUEUE,
) -> None:
    """Mostra a contagem por estado da fila."""
    if not db.exists():
        typer.echo(f"fila inexistente em {db} — rode `plan` primeiro")
        raise typer.Exit(code=1)
    with SQLiteWorkQueue(db) as queue:
        counts = queue.counts(run_id)
    total = sum(counts.values())
    for estado, quantidade in sorted(counts.items()):
        typer.echo(f"{estado:>8}  {quantidade:>5}")
    typer.echo(f"{'total':>8}  {total:>5}")


# ---------------------------------------------------------------------------
# rescore
# ---------------------------------------------------------------------------
@app.command()
def rescore(
    run_id: Annotated[str, typer.Option(help="Rodada a reprocessar.")],
    metrics: Annotated[Path, typer.Option(help="SQLite das métricas.")] = DEFAULT_METRICS,
    traces: Annotated[Path, typer.Option(help="Raiz dos traces.")] = DEFAULT_TRACES,
    version: Annotated[
        str | None, typer.Option(help="Versão da métrica a gravar; use ao mudar um scorer.")
    ] = None,
) -> None:
    """Recomputa M1–M16 sobre os traces já gravados — RF34.

    Não reexecuta o agente e não gasta cota: o trace é o contrato, e corrigir um
    scorer não deveria custar uma nova rodada. Grave numa versão nova quando a
    definição mudar, para que a série antiga continue auditável ao lado.
    """
    from src.analysis import MetricSQLiteRepository, score
    from src.analysis.scorers.execution import DEFAULT_METRIC_VERSION

    dataset = _dataset()
    por_id = dataset.by_id()
    raiz = Path(traces) / run_id
    if not raiz.exists():
        raise typer.BadParameter(f"sem traces em {raiz}")

    versao = version or DEFAULT_METRIC_VERSION
    reprocessadas = ignoradas = 0
    with MetricSQLiteRepository(metrics) as repositorio:
        for arquivo in sorted(raiz.glob("*.jsonl")):
            final = None
            for linha in arquivo.read_text(encoding="utf-8").splitlines():
                if not linha.strip():
                    continue
                registro = json.loads(linha)
                if registro.get("type") == "execution_finished":
                    final = registro.get("trace")
            if final is None:
                continue
            golden = por_id.get(final.get("case_id", ""))
            if golden is None:
                ignoradas += 1
                continue
            trace = ExecutionTrace.model_validate(final)
            repositorio.save(score(trace, golden, version=versao))
            reprocessadas += 1

    typer.echo(f"{reprocessadas} execuções reprocessadas na versão {versao}"
               + (f" · {ignoradas} sem caso no golden" if ignoradas else ""))


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------
@app.command()
def dashboard(
    run_id: Annotated[str, typer.Option(help="Rodada de E1 a reportar.")],
    out: Annotated[Path, typer.Option(help="HTML de saída.")] = DEFAULT_DASHBOARD,
    traces: Annotated[Path, typer.Option(help="Raiz dos traces.")] = DEFAULT_TRACES,
    metrics: Annotated[Path, typer.Option(help="SQLite das métricas de E1.")] = DEFAULT_METRICS,
    e2_run_id: Annotated[str | None, typer.Option(help="Rodada de E2, para H2.")] = None,
    e2_metrics: Annotated[Path | None, typer.Option(help="SQLite das métricas de E2.")] = None,
    seeds: Annotated[
        str | None, typer.Option(help="Restringe a estes seeds, separados por vírgula.")
    ] = None,
    repetition: Annotated[
        int | None, typer.Option(help="Restringe a esta repetição.")
    ] = None,
    alvo: Annotated[
        int | None, typer.Option(help="Total previsto; marca a rodada como parcial.")
    ] = None,
) -> None:
    """Gera o relatório visual do experimento a partir dos artefatos persistidos.

    Não fala com LLM nem com a API: lê os traces e o SQLite. É por isso que roda
    com o experimento em andamento e reproduz em qualquer máquina que tenha os
    artefatos.
    """
    from src.analysis import load_frame
    from src.analysis.dataset import load_execution_details
    from src.analysis.report import montar_relatorio
    from src.evaluation.degradation import carregar_intensidade
    from src.interfaces.dashboard import escrever_dashboard, render_dashboard

    intensidade_tabela = (
        carregar_intensidade(DEFAULT_INTENSITY) if DEFAULT_INTENSITY.exists() else None
    )
    df = load_frame(traces, metrics, run_id=run_id, intensity=intensidade_tabela)
    if seeds:
        escolhidos = [s.strip() for s in seeds.split(",") if s.strip()]
        df = df[df["seed"].isin(escolhidos)]
    if repetition is not None:
        df = df[df["repetition"] == repetition]

    e2_df = None
    if e2_run_id and e2_metrics:
        e2_df = load_frame(traces, e2_metrics, run_id=e2_run_id)

    relatorio = montar_relatorio(df, run_id=run_id, e2_df=e2_df)
    # O explorador so mostra o que entrou na analise; um trace fora do desenho na
    # tela e um convite a ler resultado que nenhuma metrica conta.
    vistos = set(df["execution_id"]) if len(df) else set()
    execucoes = [
        detalhe
        for detalhe in load_execution_details(traces, run_id=run_id)
        if detalhe["id"] in vistos
    ]
    html = render_dashboard(
        relatorio,
        execucoes=execucoes,
        commit=_code_commit(),
        gerado=time.strftime("%d/%m/%Y %H:%M"),
        alvo=alvo,
    )
    destino = escrever_dashboard(out, html)
    typer.echo(f"{relatorio['execucoes']} execuções · relatório em {destino}")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
@app.command()
def run(
    run_id: Annotated[str, typer.Option(help="Rodada a drenar.")],
    db: Annotated[Path, typer.Option(help="Fila SQLite.")] = DEFAULT_QUEUE,
    traces: Annotated[Path, typer.Option(help="Raiz dos traces JSONL.")] = DEFAULT_TRACES,
    metrics: Annotated[Path, typer.Option(help="SQLite das métricas.")] = DEFAULT_METRICS,
    api_url: Annotated[str, typer.Option(help="API industrial.")] = "http://127.0.0.1:8000",
    model: Annotated[str, typer.Option(help="Modelo Gemini.")] = "gemini-2.5-flash",
    rpm: Annotated[int, typer.Option(help="Requisições por minuto.")] = 10,
    daily: Annotated[int, typer.Option(help="Teto diário de chamadas.")] = 200,
    max_tasks: Annotated[
        int | None, typer.Option(help="Pare após N tarefas — use para o piloto.")
    ] = None,
    worker_id: Annotated[str, typer.Option(help="Dono do lease.")] = "worker-1",
    quota: Annotated[
        Path, typer.Option(help="Estado durável da cota diária.")
    ] = DEFAULT_QUOTA,
) -> None:
    """Drena a fila contra Gemini e a API industrial, gravando trace e métricas.

    Retomável: interromper com Ctrl-C deixa o lease vencer, e a mesma linha de
    comando retoma sem reprocessar o que já concluiu.
    """
    _api_key()
    if not db.exists():
        raise typer.BadParameter(f"fila inexistente em {db} — rode `plan` primeiro")

    processadas = asyncio.run(
        _drain(
            run_id=run_id,
            db=db,
            traces=traces,
            metrics=metrics,
            api_url=api_url,
            model=model,
            rpm=rpm,
            daily=daily,
            max_tasks=max_tasks,
            worker_id=worker_id,
            quota=quota,
        )
    )
    typer.echo(f"processadas {processadas} tarefas")


async def _drain(
    *,
    run_id: str,
    db: Path,
    traces: Path,
    metrics: Path,
    api_url: str,
    model: str,
    rpm: int,
    daily: int,
    max_tasks: int | None,
    worker_id: str,
    quota: Path,
) -> int:
    dataset = _dataset()
    por_id = dataset.by_id()
    commit = _code_commit()
    traces.mkdir(parents=True, exist_ok=True)
    metrics.parent.mkdir(parents=True, exist_ok=True)
    quota.parent.mkdir(parents=True, exist_ok=True)

    registry, overlay = build_registry(MATERIAL / "api-contract.openapi.yaml")
    sink = JsonlTraceSink(traces)
    limiter = LocalRateLimiter(
        {GeminiClient.provider: rpm},
        daily_limit_by_provider={GeminiClient.provider: daily},
        daily_state_path=quota,
    )

    def golden_for(task: Task) -> GoldenCase:
        golden = por_id.get(task.case_id)
        if golden is None:
            raise ContractError(f"caso fora do golden dataset: {task.case_id}")
        return golden

    async with HttpExecutor(api_url) as executor:
        provider = ApiToolProvider(registry, executor, overlay=overlay)
        llm = GeminiClient(model=model, rate_limiter=limiter)

        def load_case(task: Task) -> CaseInput:
            """Projeção segura: o gabarito nunca atravessa esta fronteira (RNF02)."""
            return golden_for(task).to_input()

        def architecture_for(task: Task) -> ArchitecturePort:
            golden = golden_for(task)
            # O provider é compartilhado e o worker é sequencial: fixar o usuário
            # e o seed do caso aqui é o que faz cada execução falar pelo seu ticket.
            provider.default_user_id = golden.user_id
            provider.default_seed = task.seed
            return build_architecture(task, llm=llm, provider=provider, sink=sink)

        def metadata_for(task: Task) -> dict:
            return {
                "dataset_version": dataset.version,
                "code_commit": commit,
                "experiment_id": "E2" if task.arm in E2_POLICIES else "E1",
            }

        with MetricSQLiteRepository(metrics) as repository:
            worker = Worker(
                queue := SQLiteWorkQueue(db),
                load_case,
                architecture_for,
                metadata_for=metadata_for,
                dry_run_for=lambda task: task.arm == "prompt_only",
                on_completed=ScoreCompletedExecution(golden_for, repository),
            )
            try:
                processadas = await worker.run_until_empty(
                    worker_id, run_id=run_id, max_tasks=max_tasks
                )
            finally:
                queue.close()
                limiter.close()
                await llm.aclose()

    for execution_id, erro in worker.post_completion_failures:
        typer.echo(f"scoring falhou em {execution_id}: {erro}", err=True)
    return processadas


def main() -> None:
    app()


if __name__ == "__main__":
    main()
