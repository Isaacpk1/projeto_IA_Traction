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
from typing import Annotated, cast

import typer

from src.agents.architectures import MonoArchitecture, MultiArchitecture
from src.agents.evidence_gate import EvidenceGate, Variante
from src.analysis import MetricSQLiteRepository
from src.core.contracts.golden import CaseInput, GoldenCase
from src.core.contracts.resolution import ConfirmationPolicy
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
from src.evaluation.golden.loader import (
    GoldenDataset,
    load_expansion_dataset,
    load_golden_dataset,
)
from src.evaluation.matrix import (
    E1_SEEDS,
    E2_POLICIES,
    plan_core,
    plan_e1,
    plan_e2,
    plan_expansion,
)
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
DEFAULT_JUDGMENTS = RAIZ / "artifacts" / "judgments.db"

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
    if task.arm in {"portao_global", "portao_por_ativo"}:
        variante = "global" if task.arm == "portao_global" else "por_ativo"
        return MonoArchitecture(
            llm,
            provider,
            sink,
            evidence_gate=EvidenceGate(variante=cast(Variante, variante)),
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
        str,
        typer.Option(
            help=(
                "core (E1+E2), e1, e2, "
                "expansao[:controle|portao_global|portao_por_ativo]."
            )
        ),
    ] = "core",
    db: Annotated[Path, typer.Option(help="Fila SQLite.")] = DEFAULT_QUEUE,
    only: Annotated[
        str | None,
        typer.Option(
            help=(
                "Restringe a casos específicos (ids separados por vírgula). "
                "Serve para estratificar: um braço que só pode mudar decisões de um tipo "
                "não ganha poder rodando casos onde ele nem é consultado."
            )
        ),
    ] = None,
) -> None:
    """Materializa a matriz declarada em doc 07 na fila."""
    dataset = _dataset()
    escolha = experiment.lower()
    if escolha.startswith("expansao"):
        braco = escolha.removeprefix("expansao").lstrip(":") or "controle"
        casos = load_expansion_dataset().cases
        if only:
            pedidos = {item.strip() for item in only.split(",") if item.strip()}
            casos = tuple(caso for caso in casos if caso.case_id in pedidos)
            faltando = pedidos - {caso.case_id for caso in casos}
            if faltando:
                raise typer.BadParameter(f"casos inexistentes: {sorted(faltando)}")
        tasks = plan_expansion(casos, run_id=run_id, arm=braco)
    elif escolha == "core":
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
# judge
# ---------------------------------------------------------------------------
@app.command("judge")
def judge_run(
    run_id: Annotated[str, typer.Option(help="Rodada cujos traces serão julgados.")],
    judgments: Annotated[Path, typer.Option(help="SQLite de julgamentos.")] = DEFAULT_JUDGMENTS,
    traces: Annotated[Path, typer.Option(help="Raiz dos traces.")] = DEFAULT_TRACES,
    model: Annotated[str, typer.Option(help="Modelo do juiz.")] = "llama-3.3-70b-versatile",
    base_url: Annotated[
        str, typer.Option(help="Endpoint OpenAI-compatible do provedor do juiz.")
    ] = "https://api.groq.com/openai/v1",
    provider: Annotated[str, typer.Option(help="Nome auditável do provedor.")] = "groq",
    max_executions: Annotated[
        int | None, typer.Option(help="Limite para piloto; omita para processar a rodada.")
    ] = None,
) -> None:
    """Aplica a rubrica LLM pós-execução, com cache e sem bloquear entregas."""
    from src.evaluation.judge import JudgmentSQLiteRepository, judge_trace, load_rubric
    from src.llm.openai_compat import OpenAICompatibleClient

    env_file = RAIZ / ".env"
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file)
    api_key = os.environ.get("JUDGE_API_KEY") or os.environ.get("GROQ_API_KEY") or ""
    if not api_key or api_key == _PLACEHOLDER:
        raise typer.BadParameter("defina JUDGE_API_KEY ou GROQ_API_KEY para executar o juiz")

    raiz = Path(traces) / run_id
    if not raiz.exists():
        raise typer.BadParameter(f"sem traces em {raiz}")
    rubric = load_rubric()
    cases = _dataset().by_id()

    async def process() -> tuple[int, int]:
        client = OpenAICompatibleClient(
            model=model,
            api_key=api_key,
            base_url=base_url,
            provider=provider,
        )
        judged = cached = 0
        try:
            with JudgmentSQLiteRepository(judgments) as repository:
                for arquivo in sorted(raiz.glob("*.jsonl")):
                    final = None
                    for linha in arquivo.read_text(encoding="utf-8").splitlines():
                        if linha.strip():
                            registro = json.loads(linha)
                            if registro.get("type") == "execution_finished":
                                final = registro.get("trace")
                    if final is None or final.get("case_id") not in cases:
                        continue
                    trace = ExecutionTrace.model_validate(final)
                    if trace.resolution is None:
                        continue
                    if repository.has_execution(
                        trace.execution_id,
                        rubric.version,
                        model,
                        expected_count=len(rubric.criteria),
                    ):
                        cached += 1
                        continue
                    case = cases[trace.case_id].to_input()
                    repository.save(await judge_trace(case, trace, rubric, client))
                    judged += 1
                    if max_executions is not None and judged >= max_executions:
                        break
        finally:
            await client.aclose()
        return judged, cached

    judged, cached = asyncio.run(process())
    typer.echo(
        f"{judged} execuções julgadas · {cached} em cache · rubrica {rubric.version}"
    )


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
    data_out: Annotated[
        Path | None,
        typer.Option(help="Grava os dados como JSON para o front em modo de desenvolvimento."),
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
    from src.analysis.triagem import anotar_triagem
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
    execucoes = anotar_triagem(
        [d for d in load_execution_details(traces, run_id=run_id) if d["id"] in vistos]
    )
    html = render_dashboard(
        relatorio,
        execucoes=execucoes,
        commit=_code_commit(),
        gerado=time.strftime("%d/%m/%Y %H:%M"),
        alvo=alvo,
    )
    destino = escrever_dashboard(out, html)
    typer.echo(f"{relatorio['execucoes']} execuções · relatório em {destino}")

    if data_out is not None:
        # O front em modo dev importa os mesmos dados que o HTML estático embute,
        # para que `npm run dev` e o artefato publicado nunca divirjam.
        data_out.mkdir(parents=True, exist_ok=True)
        for nome, conteudo in (("relatorio.json", relatorio), ("execucoes.json", execucoes)):
            (data_out / nome).write_text(
                json.dumps(conteudo, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        typer.echo(f"dados do front em {data_out}")


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
    confirmation_policy: Annotated[
        str,
        typer.Option(
            help=(
                "auto_refuse (padrão, seguro) | auto_confirm | explicit. "
                "Uma suíte de capacidade precisa de auto_confirm: com auto_refuse toda "
                "tool `requires_confirmation` é bloqueada e nenhum caso `agir` é alcançável."
            )
        ),
    ] = "auto_refuse",
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
            confirmation_policy=confirmation_policy,
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
    confirmation_policy: str = "auto_refuse",
) -> int:
    dataset = _dataset()
    expansao = load_expansion_dataset()
    # A busca por id cobre as duas suítes: o plano já decidiu o que roda, e um worker
    # que não encontra o caso falharia a tarefa por um detalhe de carregamento.
    por_id = {**dataset.by_id(), **expansao.by_id()}
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

        # Cada caso reporta a versão da suíte de onde veio. Marcar tudo com a versão
        # do dataset base tornava impossível saber, olhando o trace, se a execução era
        # de um caso da TRACTIAN ou da expansão — e as duas não entram na mesma análise.
        versao_por_caso = {
            **{case_id: dataset.version for case_id in dataset.by_id()},
            **{case_id: expansao.version for case_id in expansao.by_id()},
        }

        def metadata_for(task: Task) -> dict:
            return {
                "dataset_version": versao_por_caso.get(task.case_id, dataset.version),
                "code_commit": commit,
                "experiment_id": (
                    "E2"
                    if task.arm in E2_POLICIES
                    else "EXPANSAO"
                    if task.case_id in expansao.by_id()
                    else "E1"
                ),
            }

        with MetricSQLiteRepository(metrics) as repository:
            worker = Worker(
                queue := SQLiteWorkQueue(db),
                load_case,
                architecture_for,
                metadata_for=metadata_for,
                dry_run_for=lambda task: task.arm == "prompt_only",
                confirmation_policy=cast(ConfirmationPolicy, confirmation_policy),
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
