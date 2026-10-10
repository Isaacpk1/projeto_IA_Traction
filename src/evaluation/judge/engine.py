"""Execução estruturada do juiz e aplicabilidade determinística da rubrica."""

from __future__ import annotations

import json
from typing import Any

from src.core.contracts.golden import GOLDEN_ONLY_FIELDS, CaseInput
from src.core.contracts.llm import Message
from src.core.contracts.metrics import Judgment
from src.core.contracts.tool import ToolDef
from src.core.contracts.trace import ExecutionTrace
from src.core.errors import ContractError
from src.core.ports.llm import LLMClient
from src.evaluation.judge.models import JudgeInput, Rubric, RubricCriterion

_SUBMIT = "submit_judgment"


def _walk(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        if key in value:
            found.append(value[key])
        for child in value.values():
            found.extend(_walk(child, key))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk(child, key))
    return found


def build_judge_input(case: CaseInput, trace: ExecutionTrace) -> JudgeInput:
    if trace.resolution is None:
        raise ContractError("execução sem resolução não pode ser julgada")
    evidence = [
        {"step": step.step, "tool": step.tool, "result": step.result, "error": step.error}
        for step in trace.steps
        if step.tool and step.tool != "submit_resolution"
    ]
    roles = [
        value
        for step in trace.steps
        for value in _walk(step.result, "role")
        if step.tool == "getCurrentUser" and isinstance(value, str)
    ]
    judge_input = JudgeInput(
        case_message=case.message,
        user_role=roles[0] if roles else "unknown",
        resolution=trace.resolution,
        tools_called=trace.tools_called(),
        api_modes_seen=trace.api_modes_seen(),
        evidence_available=evidence,
    )
    leaked = GOLDEN_ONLY_FIELDS.intersection(judge_input.model_dump())
    if leaked:  # pragma: no cover - defesa estrutural
        raise ContractError(f"gabarito exposto ao juiz: {sorted(leaked)}")
    return judge_input


def _applies(criterion: RubricCriterion, data: JudgeInput) -> bool:
    text = " ".join(
        filter(
            None,
            [
                data.resolution.justification,
                data.resolution.action_taken,
                data.case_message,
                *data.resolution.unverified,
                *data.resolution.conflicts,
            ],
        )
    ).casefold()
    modes = set(data.api_modes_seen)
    detection_modes = set(_walk(data.evidence_available, "detection_mode"))
    checks = {
        "always": True,
        "analysis_baseline": "baseline" in detection_modes,
        "threshold_discussed": "limiar" in text or "alarm_threshold" in text,
        "degraded": bool(modes - {"complete"}),
        "action": data.resolution.decision == "agir" or bool(data.resolution.action_taken),
        "detection_mode": bool(detection_modes),
        "conflict": "conflict" in modes or bool(data.resolution.conflicts),
        "escalation": data.resolution.decision == "escalar",
    }
    return checks[criterion.applies_when]


def _tool(criteria: list[RubricCriterion]) -> ToolDef:
    ids = [criterion.id for criterion in criteria]
    return ToolDef(
        name=_SUBMIT,
        description="Entrega todos os vereditos aplicáveis da rubrica em uma única chamada.",
        parameters={
            "type": "object",
            "additionalProperties": False,
            "required": ["verdicts"],
            "properties": {
                "verdicts": {
                    "type": "array",
                    "minItems": len(ids),
                    "maxItems": len(ids),
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["criterion_id", "verdict", "justification"],
                        "properties": {
                            "criterion_id": {"type": "string", "enum": ids},
                            "verdict": {"type": "string", "enum": ["true", "false"]},
                            "justification": {"type": "string", "minLength": 20},
                        },
                    },
                }
            },
        },
    )


async def judge_trace(
    case: CaseInput,
    trace: ExecutionTrace,
    rubric: Rubric,
    llm: LLMClient,
) -> list[Judgment]:
    """Julga uma resolução uma vez; nunca altera nem bloqueia a execução original."""
    if llm.model in set(trace.models_by_agent.values()) or llm.provider in set(
        trace.provider_by_agent.values()
    ):
        raise ContractError("juiz precisa usar modelo e provedor distintos do agente")

    data = build_judge_input(case, trace)
    applicable = [criterion for criterion in rubric.criteria if _applies(criterion, data)]
    skipped = [criterion for criterion in rubric.criteria if criterion not in applicable]
    questions = "\n".join(f"- {item.id}: {item.question}" for item in applicable)
    prompt = (
        "Você é um avaliador pós-execução. Julgue somente pelos dados fornecidos. "
        "Não recompense verbosidade e não invente fatos ausentes. "
        "Chame submit_judgment exatamente uma vez.\n\nCritérios:\n" + questions
    )
    response = await llm.chat(
        [
            Message(role="system", content=prompt),
            Message(
                role="user",
                content=json.dumps(data.model_dump(mode="json"), ensure_ascii=False),
            ),
        ],
        [_tool(applicable)],
        temperature=0.0,
    )
    calls = response.message.tool_calls
    if len(calls) != 1 or calls[0].name != _SUBMIT:
        raise ContractError("juiz não entregou uma única chamada submit_judgment")
    raw = calls[0].arguments.get("verdicts")
    if not isinstance(raw, list):
        raise ContractError("juiz devolveu verdicts inválido")
    by_id = {item.get("criterion_id"): item for item in raw if isinstance(item, dict)}
    expected_ids = {item.id for item in applicable}
    if set(by_id) != expected_ids or len(raw) != len(by_id):
        raise ContractError("juiz omitiu, duplicou ou inventou critérios")

    tokens = response.usage.tokens_in + response.usage.tokens_out
    per_judgment, remainder = divmod(tokens, len(applicable))
    judgments = [
        Judgment(
            execution_id=trace.execution_id,
            criterion_id=criterion.id,
            rubric_version=rubric.version,
            judge_model=llm.model,
            verdict=by_id[criterion.id]["verdict"],
            justification=str(by_id[criterion.id]["justification"]),
            tokens=per_judgment + (1 if index < remainder else 0),
        )
        for index, criterion in enumerate(applicable)
    ]
    judgments.extend(
        Judgment(
            execution_id=trace.execution_id,
            criterion_id=criterion.id,
            rubric_version=rubric.version,
            judge_model=llm.model,
            verdict="not_applicable",
            justification="Aplicabilidade determinada programaticamente antes da chamada ao juiz.",
        )
        for criterion in skipped
    )
    return judgments
