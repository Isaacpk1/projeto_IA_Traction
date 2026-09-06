"""Fase 5 — grafo multiagente, handoffs tipados e isolamento de capacidades."""

import pytest
from pydantic import ValidationError

from src.agents.architectures import MultiArchitecture
from src.core.contracts.golden import CaseInput
from src.core.contracts.handoff import RoutingDecision
from src.core.ports.architecture import RunContext
from tests.fakes.llm import FakeLLMClient, call_tool
from tests.fakes.sinks import MemoryTraceSink
from tests.fakes.tools import FakeToolProvider, tool_def

pytest.importorskip("langgraph")


@pytest.mark.parametrize(
    "payload",
    [
        {
            "modality": "action",
            "specialists": ["investigator"],
            "rationale": "A modalidade de ação não incluiu o Executor.",
        },
        {
            "modality": "action",
            "specialists": ["executor"],
            "rationale": "O Executor foi selecionado sem investigação prévia.",
        },
    ],
)
def test_contrato_de_rota_rejeita_combinacao_insegura(payload):
    with pytest.raises(ValidationError):
        RoutingDecision.model_validate(payload)


def _evidence(tool: str, field: str, value: str, step: int) -> dict:
    return {"tool": tool, "field": field, "value": value, "step": step}


async def test_braco_b_roteia_quatro_papeis_e_persiste_handoffs_tipados():
    contextualizer = FakeLLMClient(
        [
            call_tool("getCurrentUser"),
            call_tool(
                "submit_context_report",
                {
                    "user_role": "operator",
                    "user_permissions": ["read"],
                    "evidence": [
                        _evidence("getCurrentUser", "data.role", "operator", 1)
                    ],
                },
            ),
        ]
    )
    investigator = FakeLLMClient(
        [
            call_tool("getBaseline", {"assetId": "asset_S420"}),
            call_tool(
                "submit_investigation_report",
                {
                    "findings": [
                        {
                            "claim": "O baseline está invalidado.",
                            "supported_by": [
                                _evidence("getBaseline", "data.state", "invalidated", 3)
                            ],
                        }
                    ],
                    "baseline_state": "invalidated",
                    "detection_mode": "baseline",
                    "confidence": "high",
                },
            ),
        ]
    )
    executor = FakeLLMClient(
        [
            call_tool("getCurrentUser"),
            call_tool(
                "submit_action_report",
                {
                    "attempted": False,
                    "succeeded": False,
                    "blocked_reason": "usuário sem permissão de impacto",
                    "evidence": [
                        _evidence("getCurrentUser", "data.permissions", '["read"]', 5)
                    ],
                },
            ),
        ]
    )
    orchestrator = FakeLLMClient(
        [
            call_tool(
                "submit_routing_decision",
                {
                    "modality": "action",
                    "specialists": ["contextualizer", "investigator", "executor"],
                    "rationale": "O caso requer contexto, investigação e avaliação de ação.",
                },
            ),
            call_tool(
                "submit_resolution",
                {
                    "decision": "orientar",
                    "justification": "O baseline está invalidated e a ação não é autorizada.",
                    "evidence_cited": [
                        _evidence("getBaseline", "data.state", "invalidated", 3)
                    ],
                },
            )
        ]
    )
    tools = FakeToolProvider(
        {
            "getCurrentUser": {"role": "operator", "permissions": ["read"]},
            "getBaseline": {"state": "invalidated", "detection_mode": "baseline"},
        },
        defs=[
            tool_def("getCurrentUser"),
            tool_def("getBaseline"),
            tool_def(
                "requestRetraining",
                tier="impact",
                requires_confirmation=True,
                required_permission="action_high",
            ),
        ],
    )
    sink = MemoryTraceSink()
    architecture = MultiArchitecture(
        {
            "contextualizer": contextualizer,
            "investigator": investigator,
            "executor": executor,
            "orchestrator": orchestrator,
        },
        tools,
        sink,
    )
    case = CaseInput(
        case_id="case_tkt_inv_06",
        ticket_id="TKT-INV-06",
        message="O insight parece falso positivo.",
        company_id="comp_acme",
        user_id="usr_bruno",
        asset_id="asset_S420",
    )
    context = RunContext(
        execution_id="exec_multi",
        task_id="task_multi",
        run_id="run_multi",
        arm="B",
        seed="complete",
    )

    trace = await architecture.run(case, context)

    assert trace.error_class is None, trace.steps
    assert trace.resolution is not None and trace.resolution.decision == "orientar"
    assert trace.architecture == "multi" and trace.arm == "B"
    assert [handoff.from_agent for handoff in trace.handoffs] == [
        "orchestrator",
        "contextualizer",
        "orchestrator",
        "investigator",
        "orchestrator",
        "executor",
    ]
    assert len(sink.handoffs) == 6
    assert not {tool.tier for tool in investigator.calls[0][1]} & {"impact"}
    assert {tool.name for tool in executor.calls[0][1]} == {
        "getCurrentUser",
        "requestRetraining",
        "submit_action_report",
    }
    assert {tool.name for tool in orchestrator.calls[0][1]} == {"submit_routing_decision"}
    assert {tool.name for tool in orchestrator.calls[1][1]} == {"submit_resolution"}
    for specialist in (contextualizer, investigator, executor):
        assert "submit_resolution" not in specialist.calls[0][0][0].content
    assert "submit_resolution" not in orchestrator.calls[0][0][0].content
    assert "submit_resolution" in orchestrator.calls[1][0][0].content


async def test_rota_investigativa_pula_contextualizador_e_executor():
    contextualizer = FakeLLMClient()
    executor = FakeLLMClient()
    investigator = FakeLLMClient(
        [
            call_tool("getBaseline", {"assetId": "asset_S420"}),
            call_tool(
                "submit_investigation_report",
                {
                    "findings": [
                        {
                            "claim": "O baseline está invalidado.",
                            "supported_by": [
                                _evidence("getBaseline", "data.state", "invalidated", 1)
                            ],
                        }
                    ],
                    "baseline_state": "invalidated",
                    "confidence": "high",
                },
            ),
        ]
    )
    orchestrator = FakeLLMClient(
        [
            call_tool(
                "submit_routing_decision",
                {
                    "modality": "investigation",
                    "specialists": ["investigator"],
                    "rationale": "A solicitação exige somente diagnóstico do baseline.",
                },
            ),
            call_tool(
                "submit_resolution",
                {
                    "decision": "orientar",
                    "justification": "O baseline observado está invalidado.",
                    "evidence_cited": [
                        _evidence("getBaseline", "data.state", "invalidated", 1)
                    ],
                },
            ),
        ]
    )
    tools = FakeToolProvider(
        {"getBaseline": {"state": "invalidated"}},
        defs=[tool_def("getBaseline")],
    )
    architecture = MultiArchitecture(
        {
            "contextualizer": contextualizer,
            "investigator": investigator,
            "executor": executor,
            "orchestrator": orchestrator,
        },
        tools,
        MemoryTraceSink(),
    )
    case = CaseInput(
        case_id="case_route",
        ticket_id="TKT-ROUTE",
        message="Investigue o baseline.",
        company_id="comp_acme",
        user_id="usr_bruno",
        asset_id="asset_S420",
    )

    trace = await architecture.run(
        case,
        RunContext(
            execution_id="exec_route",
            task_id="task_route",
            run_id="run_route",
            arm="B",
            seed="complete",
        ),
    )

    assert trace.error_class is None
    assert contextualizer.n_calls == 0
    assert executor.n_calls == 0
    assert investigator.n_calls == 2
    assert [(item.from_agent, item.to_agent) for item in trace.handoffs] == [
        ("orchestrator", "investigator"),
        ("investigator", "orchestrator"),
    ]
