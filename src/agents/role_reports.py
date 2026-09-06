"""Loop ReAct terminal para relatórios tipados dos especialistas."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from src.agents.roles import RoleSpec
from src.agents.tracer import TraceRecorder
from src.core.contracts.golden import CaseInput
from src.core.contracts.llm import Message
from src.core.contracts.tool import ToolCall, ToolDef, ToolResult
from src.core.contracts.trace import StopReason
from src.core.ports.llm import LLMClient
from src.core.ports.tools import ToolProvider

__all__ = ["ReportOutcome", "report_tool", "run_report_loop"]

ReportT = TypeVar("ReportT", bound=BaseModel)


@dataclass(frozen=True)
class ReportOutcome:
    report: BaseModel | None
    stop_reason: StopReason
    error_class: str | None = None


def report_tool(name: str, model: type[BaseModel], description: str) -> ToolDef:
    return ToolDef(name=name, description=description, parameters=model.model_json_schema())


def _observation(result: ToolResult) -> str:
    return json.dumps(
        {"data": result.data, "error": result.error, "error_class": result.error_class},
        ensure_ascii=False,
        sort_keys=True,
    )


def _contract_error(call: ToolCall, message: str) -> ToolResult:
    return ToolResult(call_id=call.call_id, name=call.name, error=message, error_class="contract")


async def run_report_loop(
    *,
    case: CaseInput,
    role: RoleSpec,
    prompt: str,
    llm: LLMClient,
    provider: ToolProvider,
    api_tools: list[ToolDef],
    terminal_tool: ToolDef,
    report_model: type[ReportT],
    tracer: TraceRecorder,
    max_steps: int,
    temperature: float = 0.0,
    seed: str | None = None,
    context: dict | None = None,
) -> ReportOutcome:
    payload = {"case": case.model_dump(), "reports": context or {}}
    messages = [
        Message(role="system", content=prompt),
        Message(role="user", content=json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    ]
    offered = [*api_tools, terminal_tool]

    for _ in range(max_steps):
        response = await llm.chat(messages, offered, temperature=temperature)
        tracer.add_usage(
            response.usage,
            agent=role.name,
            model=response.model or llm.model,
            model_version=response.model_version,
            provider=response.provider or llm.provider,
        )
        messages.append(response.message)
        calls = response.message.tool_calls
        if not calls:
            tracer.record_reasoning(
                agent=role.name,
                reasoning=response.message.content,
                error=f"resposta final sem {terminal_tool.name}",
            )
            return ReportOutcome(None, "error", "behavior")

        terminal = [call for call in calls if call.name == terminal_tool.name]
        if terminal and len(calls) != 1:
            for call in calls:
                result = _contract_error(
                    call, f"{terminal_tool.name} deve ser a única chamada do turno terminal"
                )
                tracer.record_tool(
                    agent=role.name,
                    reasoning=response.message.content,
                    call=call,
                    result=result,
                )
                messages.append(
                    Message(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.call_id,
                        content=_observation(result),
                    )
                )
            continue

        for call in calls:
            report: ReportT | None = None
            if call.name == terminal_tool.name:
                try:
                    report = report_model.model_validate(call.arguments)
                    result = ToolResult(
                        call_id=call.call_id,
                        name=call.name,
                        data={"accepted": True, "report": report.model_dump(mode="json")},
                    )
                except ValidationError as exc:
                    result = _contract_error(call, f"relatório inválido: {exc}")
            else:
                result = await provider.call(
                    call.name,
                    call.arguments,
                    call_id=call.call_id,
                    user_id=case.user_id,
                    seed=seed,
                )

            tracer.record_tool(
                agent=role.name,
                reasoning=response.message.content,
                call=call,
                result=result,
            )
            messages.append(
                Message(
                    role="tool",
                    name=call.name,
                    tool_call_id=call.call_id,
                    content=_observation(result),
                )
            )
            if report is not None:
                return ReportOutcome(report, "sufficient")

    return ReportOutcome(None, "max_steps")
