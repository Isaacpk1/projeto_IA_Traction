"""LLM-as-a-judge: isolamento, aplicabilidade, contrato e cache."""

import json

import pytest

from src.core.contracts.golden import GOLDEN_ONLY_FIELDS, CaseInput
from src.core.contracts.llm import LLMResponse, Message, Usage
from src.core.contracts.resolution import Resolution
from src.core.contracts.tool import ToolCall
from src.core.errors import ContractError
from src.evaluation.judge import (
    JudgmentSQLiteRepository,
    build_judge_input,
    judge_trace,
    load_rubric,
)
from tests.factories.traces import make_trace, step
from tests.fakes.llm import FakeLLMClient


def _case() -> CaseInput:
    return CaseInput(
        case_id="case_test",
        ticket_id="ticket",
        message="Posso confiar neste insight?",
        company_id="company",
        user_id="user",
        asset_id="asset",
    )


def _judge_response(ids: list[str]) -> LLMResponse:
    return LLMResponse(
        message=Message(
            role="assistant",
            tool_calls=[
                ToolCall(
                    call_id="judge-1",
                    name="submit_judgment",
                    arguments={
                        "verdicts": [
                            {
                                "criterion_id": item,
                                "verdict": "true",
                                "justification": "O critério está sustentado pelo trace fornecido.",
                            }
                            for item in ids
                        ]
                    },
                )
            ],
        ),
        usage=Usage(tokens_in=80, tokens_out=20),
        model="judge-model",
        provider="judge-provider",
    )


def test_input_do_juiz_nao_contem_gabarito():
    trace = make_trace([step("getAnalysis", {"detection_mode": "baseline"})])

    payload = build_judge_input(_case(), trace).model_dump()

    assert GOLDEN_ONLY_FIELDS.isdisjoint(payload)
    assert payload["case_message"] == "Posso confiar neste insight?"


@pytest.mark.asyncio
async def test_juiz_aplica_criterios_em_codigo_e_exige_saida_estruturada():
    rubric = load_rubric()
    applicable = [
        "C1_baseline_declarado",
        "C4_evidencia_ancorada",
        "C6_modo_deteccao_correto",
        "C8_adequacao_ao_perfil",
        "C10_redacao_utilizavel",
    ]
    llm = FakeLLMClient(
        [_judge_response(applicable)], model="judge-model", provider="judge-provider"
    )
    trace = make_trace(
        [step("getAnalysis", {"detection_mode": "baseline"})],
        resolution=Resolution(decision="orientar", justification="Baseline established."),
        models_by_agent={"agent": "agent-model"},
        provider_by_agent={"agent": "agent-provider"},
    )

    judgments = await judge_trace(_case(), trace, rubric, llm)

    assert len(judgments) == 10
    assert {item.criterion_id for item in judgments if item.verdict == "true"} == set(applicable)
    skipped = [item for item in judgments if item.criterion_id not in applicable]
    assert all(item.verdict == "not_applicable" for item in skipped)
    assert sum(item.tokens for item in judgments) == 100
    sent = json.loads(llm.calls[0][0][1].content or "{}")
    assert GOLDEN_ONLY_FIELDS.isdisjoint(sent)


@pytest.mark.asyncio
async def test_criterio_de_repasse_so_se_aplica_quando_o_caso_e_escalado():
    """Quem recebe um escalonamento não viu a investigação; a rubrica cobra esse repasse."""
    rubric = load_rubric()
    aplicaveis = [
        "C1_baseline_declarado",
        "C4_evidencia_ancorada",
        "C6_modo_deteccao_correto",
        "C8_adequacao_ao_perfil",
        "C9_repasse_ao_tecnico",
        "C10_redacao_utilizavel",
    ]
    llm = FakeLLMClient(
        [_judge_response(aplicaveis)], model="judge-model", provider="judge-provider"
    )
    trace = make_trace(
        [step("getAnalysis", {"detection_mode": "baseline"})],
        resolution=Resolution(
            decision="escalar",
            justification="Sensor offline e medição de 5 dias; segue para inspeção em campo.",
        ),
        models_by_agent={"agent": "agent-model"},
        provider_by_agent={"agent": "agent-provider"},
    )

    judgments = await judge_trace(_case(), trace, rubric, llm)

    repasse = next(item for item in judgments if item.criterion_id == "C9_repasse_ao_tecnico")
    assert repasse.verdict == "true"


@pytest.mark.asyncio
async def test_juiz_rejeita_mesmo_provedor_do_agente():
    trace = make_trace(provider_by_agent={"agent": "same"})
    llm = FakeLLMClient(model="other", provider="same")

    with pytest.raises(ContractError, match="distintos"):
        await judge_trace(_case(), trace, load_rubric(), llm)


def test_repositorio_de_julgamentos_e_idempotente(tmp_path):
    judgment = _judge_response(["C4_evidencia_ancorada"])
    item = {
        "execution_id": "exec",
        "criterion_id": "C4_evidencia_ancorada",
        "rubric_version": "1.0.0",
        "judge_model": "judge-model",
        "verdict": "true",
        "justification": "A evidência está ancorada no retorno observado.",
    }
    from src.core.contracts.metrics import Judgment

    with JudgmentSQLiteRepository(tmp_path / "judge.db") as repository:
        assert repository.save([Judgment.model_validate(item)]) == 1
        assert repository.save([Judgment.model_validate(item)]) == 0
        assert repository.has_execution("exec", "1.0.0", "judge-model")
        assert not repository.has_execution(
            "exec", "1.0.0", "judge-model", expected_count=8
        )
        assert repository.for_execution("exec")[0].verdict == "true"

    assert judgment.usage.tokens_in == 80
