"""Fase 2 — loop ReAct mono inteiramente determinístico com fakes."""

from __future__ import annotations

from src.agents.architectures import MonoArchitecture
from src.core.contracts.golden import CaseInput
from src.core.ports.architecture import RunContext
from tests.fakes.llm import FakeLLMClient, call_tool, call_tools, say
from tests.fakes.sinks import MemoryTraceSink
from tests.fakes.tools import FakeToolProvider


def _case() -> CaseInput:
    return CaseInput(
        case_id="case_tkt_inv_06",
        ticket_id="tkt_inv_06",
        message="O diagnóstico parece um falso positivo.",
        company_id="comp_forja_br",
        user_id="usr_ana",
        asset_id="asset_S420",
    )


def _ctx(*, max_steps: int = 8) -> RunContext:
    return RunContext(
        execution_id="exec_1",
        task_id="task_1",
        run_id="run_1",
        seed="s1",
        max_steps=max_steps,
        metadata={
            "degradation_intensity": 0.5,
            "overlay_version": "1:enriched",
            "tool_schema_version": "abc123",
            "api_contract_version": "1",
            "dataset_version": "1",
            "code_commit": "deadbeef",
        },
    )


async def test_caso_completo_verifica_baseline_e_submete_resolucao():
    llm = FakeLLMClient(
        [
            call_tool("getAnalysis", {"analysisId": "an_9903"}, thought="Vou investigar."),
            call_tool("getBaseline", {"assetId": "asset_S420"}),
            call_tool(
                "submit_resolution",
                {
                    "decision": "escalar",
                    "justification": "O baseline estava invalidado no momento da detecção.",
                    "evidence_cited": [
                        {
                            "tool": "getBaseline",
                            "field": "data.state",
                            "value": "invalidated",
                            "step": 1,
                        }
                    ],
                    "unverified": ["causa raiz"],
                },
            ),
        ],
        model="fake-model",
    )
    tools = FakeToolProvider(
        {
            "getAnalysis": {"type": "imbalance"},
            "getBaseline": {"state": "invalidated"},
        }
    )
    sink = MemoryTraceSink()

    trace = await MonoArchitecture(llm, tools, sink).run(_case(), _ctx())

    assert trace.resolution is not None and trace.resolution.decision == "escalar"
    assert trace.tools_called() == ["getAnalysis", "getBaseline", "submit_resolution"]
    assert tools.call_index("getBaseline") == 1
    assert trace.stop_reason == "sufficient"
    assert trace.llm_calls == 3
    assert trace.tokens_in == 300 and trace.tokens_out == 60
    assert trace.models_by_agent == {"agent": "fake-model"}
    assert trace.provider_by_agent == {"agent": "fake"}
    assert trace.degradation_intensity == 0.5
    assert trace.overlay_version == "1:enriched"
    assert len(sink.opened) == len(sink.closed) == 1
    assert len(sink.steps) == 3
    assert "submit_resolution" in llm.tools_offered()


async def test_texto_livre_nao_finge_que_uma_resolucao_foi_submetida():
    sink = MemoryTraceSink()
    trace = await MonoArchitecture(
        FakeLLMClient([say("Acho que está tudo bem.")]), FakeToolProvider(), sink
    ).run(_case(), _ctx())

    assert trace.resolution is None
    assert trace.stop_reason == "error"
    assert trace.error_class == "behavior"
    assert trace.steps[0].error == "resposta final sem submit_resolution"


async def test_limite_de_passos_encerra_sem_inventar_resolucao():
    llm = FakeLLMClient([call_tool("getAsset", {"assetId": "asset_S420"})] * 2)
    trace = await MonoArchitecture(
        llm, FakeToolProvider({"getAsset": {"id": "asset_S420"}}), MemoryTraceSink()
    ).run(_case(), _ctx(max_steps=2))

    assert trace.stop_reason == "max_steps"
    assert trace.resolution is None
    assert len(trace.steps) == 2


async def test_submit_misturado_com_outra_tool_nao_executa_efeito():
    llm = FakeLLMClient(
        [
            call_tools(
                [
                    ("updateAssetConfig", {"assetId": "asset_S420"}),
                    (
                        "submit_resolution",
                        {"decision": "agir", "justification": "alterar configuração"},
                    ),
                ]
            ),
            call_tool(
                "submit_resolution",
                {"decision": "escalar", "justification": "chamadas terminais conflitantes"},
            ),
        ]
    )
    tools = FakeToolProvider({"updateAssetConfig": {"accepted": True}})

    trace = await MonoArchitecture(llm, tools, MemoryTraceSink()).run(_case(), _ctx())

    assert not tools.called("updateAssetConfig")
    assert trace.resolution is not None and trace.resolution.decision == "escalar"
    assert trace.steps[0].error is not None
    assert trace.steps[1].error is not None
