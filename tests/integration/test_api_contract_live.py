"""Camada de ferramentas contra a API industrial real.

Pulado quando a API não está no ar — a suíte precisa rodar em máquina limpa. Estes testes
não consomem cota de LLM: exercitam apenas o caminho tool → HTTP → envelope.

O teste central aqui é o de determinismo por `seed`. O desenho de E1 trata os seeds como
**níveis de uma variável contínua** em vez de um fator binário, o que multiplica o poder
estatístico sem custo adicional. Isso só é legítimo se a API for de fato determinística —
e essa premissa merece verificação executável, não apenas leitura do código-fonte.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from src.agents.architectures import MonoArchitecture, MultiArchitecture
from src.analysis import MetricSQLiteRepository
from src.core.contracts.task import Task
from src.core.contracts.trace import ExecutionTrace, TraceStep
from src.core.ports.architecture import RunContext
from src.evaluation.golden import load_golden_dataset
from src.evaluation.runner.worker import Worker
from src.interfaces import ScoreCompletedExecution
from src.storage.jsonl_traces import JsonlTraceSink
from src.tools.core.http_executor import HttpExecutor
from src.tools.provider import ApiToolProvider, build_registry
from tests.fakes.llm import FakeLLMClient, call_tool
from tests.fakes.queue import InMemoryQueue

API_URL = os.environ.get("TRACTIAN_API_URL", "http://127.0.0.1:8000")
ASSET = "asset_S420"


def _api_no_ar() -> bool:
    try:
        return httpx.get(f"{API_URL}/docs", timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.filterwarnings("ignore::UserWarning"),
    pytest.mark.skipif(not _api_no_ar(), reason=f"API industrial fora do ar em {API_URL}"),
]


@pytest.fixture
async def provider(contract_path: Path):
    reg, ov = build_registry(contract_path)
    async with HttpExecutor(API_URL) as ex:
        yield ApiToolProvider(reg, ex, overlay=ov, default_user_id="usr_pedro")


async def test_toda_tool_de_leitura_responde(provider):
    """Se uma tool gerada não conversa com a API real, o schema está errado."""
    args = {
        "getCompany": {"companyId": "comp_forja_br"},
        "listAssetsByCompany": {"companyId": "comp_forja_br"},
        "getCurrentUser": {},
        "getAsset": {"assetId": ASSET},
        "listAnalyses": {"assetId": ASSET},
        "getBaseline": {"assetId": ASSET},
        "getRmsSeries": {"assetId": ASSET},
        "getSpectrum": {"assetId": ASSET},
        "getDataQuality": {"assetId": ASSET},
        "searchKnowledge": {"q": "baseline"},
    }
    falhas = []
    for nome, a in args.items():
        r = await provider.call(nome, a, call_id=nome, seed="s1")
        if not r.ok or r.data is None:
            falhas.append((nome, r.error))
    assert not falhas, falhas


async def test_mesmo_seed_produz_a_mesma_resposta(provider):
    """Premissa de RNF01 e do desenho dose-resposta."""
    a = await provider.call("getBaseline", {"assetId": ASSET}, call_id="a", seed="s1")
    b = await provider.call("getBaseline", {"assetId": ASSET}, call_id="b", seed="s1")
    assert a.data == b.data


async def test_seeds_distintos_produzem_regimes_distintos(provider):
    """Sem variação entre seeds, o eixo de degradação de H1 seria constante — e a
    análise dose-resposta não teria variável independente."""
    modos = set()
    for s in [f"s{i}" for i in range(8)]:
        r = await provider.call("getBaseline", {"assetId": ASSET}, call_id=s, seed=s)
        modos.add(r.mode)
    assert len(modos) >= 2, f"todos os seeds produziram o mesmo modo: {modos}"


async def test_intensidade_de_degradacao_sai_do_trace(provider):
    """A variável independente de H1 é computada do trace, nunca do gabarito."""
    passos = []
    trajetoria = ["getAsset", "listAnalyses", "getBaseline", "getRmsSeries", "getDataQuality"]
    for i, nome in enumerate(trajetoria):
        r = await provider.call(nome, {"assetId": ASSET}, call_id=str(i), seed="s0")
        passos.append(TraceStep(step=i, agent="agent", tool=nome, result=r.data))

    trace = ExecutionTrace(
        task_id="t", execution_id="e", case_id="c", architecture="mono", arm="A", steps=passos
    )

    assert len(trace.api_modes_seen()) == len(trajetoria), "todo GET traz envelope com modo"
    intensidade = trace.observed_degradation_intensity()
    assert intensidade is not None and 0.0 <= intensidade <= 1.0


async def test_provider_bloqueia_justificativa_curta_antes_do_http(provider):
    """O schema da tool bloqueia a chamada inválida antes de qualquer efeito externo."""
    r = await provider.call(
        "escalateCase", {"caseId": "case_tkt_inv_06", "justification": "curta"}, call_id="c"
    )

    assert not r.ok
    assert r.error_class == "contract"
    assert r.status_code is None
    assert not r.external_call_emitted


async def test_api_recusa_justificativa_curta():
    """L13: a API também valida a justificativa por comprimento (≥20 chars)."""
    async with httpx.AsyncClient(base_url=API_URL) as client:
        response = await client.post(
            "/cases/case_tkt_inv_06/escalate",
            headers={"x-user-id": "usr_pedro"},
            json={"justification": "curta"},
        )

    assert response.status_code in (400, 422)


async def test_execucao_mono_real_persiste_trace_e_metricas(provider, tmp_path):
    """Caminho Fase 4: API real → trace JSONL → scoring → SQLite."""
    dataset = load_golden_dataset()
    golden = dataset.by_id()["case_tkt_inv_06"]
    provider.default_user_id = golden.user_id
    provider.default_seed = "complete"

    llm = FakeLLMClient(
        [
            call_tool("getBaseline", {"assetId": golden.asset_id}),
            call_tool(
                "submit_resolution",
                {
                    "decision": "orientar",
                    "justification": "O baseline foi invalidado apó uma intervenção de manutenção.",
                    "evidence_cited": [
                        {
                            "tool": "getBaseline",
                            "field": "data.state",
                            "value": "invalidated",
                            "step": 0,
                        }
                    ],
                },
            ),
        ]
    )
    sink = JsonlTraceSink(tmp_path / "traces")
    architecture = MonoArchitecture(llm, provider, sink)
    task = Task(
        task_id="task_live_scoring",
        kind="experiment",
        case_id=golden.case_id,
        architecture="mono",
        run_id="run_live_scoring",
        seed="complete",
    )
    queue = InMemoryQueue()
    queue.enqueue([task])

    with MetricSQLiteRepository(tmp_path / "metrics.db") as repository:
        hook = ScoreCompletedExecution(lambda leased: golden, repository)
        worker = Worker(
            queue,
            lambda leased: golden.to_input(),
            lambda leased: architecture,
            on_completed=hook,
        )

        trace = await worker.run_once("worker-live")

        assert trace is not None
        saved_metrics = repository.for_execution(trace.execution_id)
        metrics = {metric.metric_id: metric for metric in saved_metrics}

    persisted = sink.read_final(trace.execution_id)
    assert queue.get(task.task_id).state == "done"
    assert persisted.execution_id == trace.execution_id
    assert persisted.tools_called() == ["getBaseline", "submit_resolution"]
    assert metrics["M4"].value == 1.0
    assert metrics["M5a"].value == 1.0
    assert metrics["M5b"].value == 1.0


async def test_braco_b_executa_caso_contra_api_real(provider, tmp_path):
    """DoD Fase 5: quatro papéis, API real e handoffs persistidos no trace."""
    pytest.importorskip("langgraph")
    dataset = load_golden_dataset()
    golden = dataset.by_id()["case_tkt_inv_06"]
    provider.default_user_id = golden.user_id
    provider.default_seed = "complete"

    llms = {
        "contextualizer": FakeLLMClient(
            [
                call_tool("getCurrentUser"),
                call_tool("submit_context_report", {"unverified": []}),
            ]
        ),
        "investigator": FakeLLMClient(
            [
                call_tool("getBaseline", {"assetId": golden.asset_id}),
                call_tool(
                    "submit_investigation_report",
                    {
                        "findings": [
                            {
                                "claim": "O baseline está invalidado.",
                                "supported_by": [
                                    {
                                        "tool": "getBaseline",
                                        "field": "data.state",
                                        "value": "invalidated",
                                        "step": 3,
                                    }
                                ],
                            }
                        ],
                        "baseline_state": "invalidated",
                        "detection_mode": "baseline",
                        "confidence": "high",
                    },
                ),
            ]
        ),
        "executor": FakeLLMClient(
            [
                call_tool("getCurrentUser"),
                call_tool(
                    "submit_action_report",
                    {
                        "attempted": False,
                        "succeeded": False,
                        "blocked_reason": "nenhuma ação autorizada foi necessária",
                    },
                ),
            ]
        ),
        "orchestrator": FakeLLMClient(
            [
                call_tool(
                    "submit_routing_decision",
                    {
                        "modality": "action",
                        "specialists": ["contextualizer", "investigator", "executor"],
                        "rationale": "O caso exige contexto, investigação e avaliação de ação.",
                    },
                ),
                call_tool(
                    "submit_resolution",
                    {
                        "decision": "orientar",
                        "justification": "O baseline está invalidado; requer orientação técnica.",
                        "evidence_cited": [
                            {
                                "tool": "getBaseline",
                                "field": "data.state",
                                "value": "invalidated",
                                "step": 3,
                            }
                        ],
                    },
                )
            ]
        ),
    }
    sink = JsonlTraceSink(tmp_path / "multi-traces")
    architecture = MultiArchitecture(llms, provider, sink)
    context = RunContext(
        execution_id="exec_multi_live",
        task_id="task_multi_live",
        run_id="run_multi_live",
        arm="B",
        seed="complete",
    )

    trace = await architecture.run(golden.to_input(), context)

    assert trace.error_class is None, trace.steps
    assert trace.resolution is not None and trace.resolution.decision == "orientar"
    assert len(trace.handoffs) == 6
    assert sink.read_final(trace.execution_id).handoffs == trace.handoffs


async def test_sondas_adversariais_apontam_para_recursos_reais(provider):
    dataset = load_golden_dataset()
    failures = []

    for case in dataset.adversarial_cases():
        provider.default_user_id = case.user_id
        target = provider.get(case.target_action or "")
        if target is None or target.tier != "impact":
            failures.append((case.adversarial_id, case.target_action, "target não é impact"))
        for index, probe in enumerate(case.degradation_probes):
            tool = provider.get(probe.tool)
            if tool is None or tool.tier != "read":
                failures.append((case.adversarial_id, probe.tool, "sonda não é read"))
                continue
            result = await provider.call(
                probe.tool,
                probe.args_contains,
                call_id=f"{case.adversarial_id}-{index}",
                seed="complete",
            )
            if not result.ok:
                failures.append((case.adversarial_id, probe.tool, result.error))

    assert not failures, failures
