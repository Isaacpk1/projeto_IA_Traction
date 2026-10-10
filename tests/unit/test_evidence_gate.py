"""Portão de evidência ligado ao loop ReAct.

O valor do portão está em recusar **e devolver o turno**: o agente investiga o que faltava
e decide de novo. Um portão que bloqueasse a entrega apenas trocaria uma resposta rasa por
nenhuma resposta.
"""

from __future__ import annotations

from src.agents.architectures import MonoArchitecture
from src.agents.evidence_gate import EvidenceGate
from src.core.contracts.golden import CaseInput
from src.core.ports.architecture import RunContext
from tests.fakes.llm import FakeLLMClient, call_tool
from tests.fakes.sinks import MemoryTraceSink
from tests.fakes.tools import FakeToolProvider

CITACAO = [{"tool": "getBaseline", "field": "data.state", "value": "established", "step": 0}]


def _case() -> CaseInput:
    return CaseInput(
        case_id="case_x",
        ticket_id="tkt_x",
        message="Manda alguém em campo olhar isso.",
        company_id="comp_forja_br",
        user_id="usr_ana",
        asset_id="asset_M101",
    )


def _ctx() -> RunContext:
    return RunContext(execution_id="e1", task_id="t1", run_id="r1", seed="complete", max_steps=8)


def _escalar(justificativa: str = "Preciso de inspeção presencial no ativo.") -> dict:
    return {"decision": "escalar", "justification": justificativa, "evidence_cited": CITACAO}


async def test_sem_portao_escalonamento_sem_lacuna_observada_passa():
    """Controle: é este o comportamento que o portão deve mudar."""
    llm = FakeLLMClient(
        [
            call_tool("getBaseline", {"assetId": "asset_M101"}),
            call_tool("submit_resolution", _escalar()),
        ]
    )
    tools = FakeToolProvider({"getBaseline": {"state": "established"}})

    trace = await MonoArchitecture(llm, tools, MemoryTraceSink()).run(_case(), _ctx())

    assert trace.resolution is not None and trace.resolution.decision == "escalar"


async def test_portao_recusa_escalonamento_sem_lacuna_e_o_agente_reinvestiga():
    llm = FakeLLMClient(
        [
            call_tool("getBaseline", {"assetId": "asset_M101"}),
            call_tool("submit_resolution", _escalar()),
            call_tool("getDataQuality", {"assetId": "asset_M101"}),
            call_tool("submit_resolution", _escalar()),
        ]
    )
    tools = FakeToolProvider(
        {
            "getBaseline": {"state": "established"},
            "getDataQuality": {"mode": "unavailable", "notes": None, "data": {}},
        }
    )

    trace = await MonoArchitecture(
        llm, tools, MemoryTraceSink(), evidence_gate=EvidenceGate()
    ).run(_case(), _ctx())

    passos = trace.tools_called()
    assert passos.count("submit_resolution") == 2, "o primeiro encerramento tinha de ser recusado"
    assert "getDataQuality" in passos, "o agente devia voltar a investigar após a recusa"
    assert trace.resolution is not None and trace.resolution.decision == "escalar"


async def test_portao_nao_toca_orientar():
    """`orientar` é a saída segura: travá-la empurraria o agente para as decisões de risco."""
    llm = FakeLLMClient(
        [
            call_tool("getBaseline", {"assetId": "asset_M101"}),
            call_tool(
                "submit_resolution",
                {
                    "decision": "orientar",
                    "justification": "O baseline está estabelecido e o ativo opera normal.",
                    "evidence_cited": CITACAO,
                },
            ),
        ]
    )
    tools = FakeToolProvider({"getBaseline": {"state": "established"}})

    trace = await MonoArchitecture(
        llm, tools, MemoryTraceSink(), evidence_gate=EvidenceGate()
    ).run(_case(), _ctx())

    assert trace.tools_called().count("submit_resolution") == 1
    assert trace.resolution is not None and trace.resolution.decision == "orientar"


async def test_variante_por_ativo_ignora_degradacao_de_outro_recurso():
    """Ver `unavailable` num recurso alheio não sustenta 'falta evidência para este ativo'."""
    llm = FakeLLMClient(
        [
            call_tool("getModel", {"modelId": "mdl_vib_v3"}),
            call_tool("submit_resolution", _escalar()),
            call_tool("getBaseline", {"assetId": "asset_M101"}),
            call_tool("submit_resolution", _escalar()),
        ]
    )
    tools = FakeToolProvider(
        {
            "getModel": {"mode": "unavailable", "notes": None, "data": {}},
            "getBaseline": {"mode": "unavailable", "notes": None, "data": {}},
        }
    )

    trace = await MonoArchitecture(
        llm, tools, MemoryTraceSink(), evidence_gate=EvidenceGate(variante="por_ativo")
    ).run(_case(), _ctx())

    assert trace.tools_called().count("submit_resolution") == 2


async def test_portao_desiste_apos_o_limite_de_recusas():
    """Insistir até o teto de passos devolveria execução sem resolução — pior que resposta rasa."""
    llm = FakeLLMClient(
        [
            call_tool("getBaseline", {"assetId": "asset_M101"}),
            call_tool("submit_resolution", _escalar()),
            call_tool("submit_resolution", _escalar()),
        ]
    )
    tools = FakeToolProvider({"getBaseline": {"state": "established"}})

    trace = await MonoArchitecture(
        llm, tools, MemoryTraceSink(), evidence_gate=EvidenceGate(max_recusas=1)
    ).run(_case(), _ctx())

    assert trace.resolution is not None and trace.resolution.decision == "escalar"
    assert trace.stop_reason == "sufficient"
