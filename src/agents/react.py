"""Loop ReAct compartilhado por todas as arquiteturas — doc 05 §4.2."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from src.agents.roles import SUBMIT_RESOLUTION, RoleSpec
from src.agents.submit_resolution import parse_resolution
from src.agents.tracer import TraceRecorder
from src.core.contracts.golden import CaseInput
from src.core.contracts.llm import Message
from src.core.contracts.resolution import Resolution
from src.core.contracts.tool import ToolCall, ToolDef, ToolResult
from src.core.contracts.trace import StopReason
from src.core.ports.llm import LLMClient
from src.core.ports.tools import ToolProvider

__all__ = ["ReactOutcome", "react_loop"]


@dataclass(frozen=True)
class ReactOutcome:
    resolution: Resolution | None
    stop_reason: StopReason
    error_class: str | None = None


def _observation(result: ToolResult) -> str:
    return json.dumps(
        {
            "data": result.data,
            "error": result.error,
            "error_class": result.error_class,
            "status_code": result.status_code,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _contract_error(call: ToolCall, message: str) -> ToolResult:
    return ToolResult(call_id=call.call_id, name=call.name, error=message, error_class="contract")


async def react_loop(
    *,
    case: CaseInput,
    role: RoleSpec,
    prompt: str,
    llm: LLMClient,
    provider: ToolProvider,
    api_tools: list[ToolDef],
    application_tools: list[ToolDef],
    tracer: TraceRecorder,
    max_steps: int,
    temperature: float = 0.0,
    seed: str | None = None,
) -> ReactOutcome:
    """Executa turnos LLM até `submit_resolution` ou até o orçamento terminar."""
    messages = [
        Message(role="system", content=prompt),
        Message(
            role="user",
            content=json.dumps(case.model_dump(), ensure_ascii=False, sort_keys=True),
        ),
    ]
    offered = [*api_tools, *application_tools]

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
                error="resposta final sem submit_resolution",
            )
            return ReactOutcome(None, "error", "behavior")

        terminal = [call for call in calls if call.name == SUBMIT_RESOLUTION]
        if terminal and len(calls) != 1:
            for call in calls:
                result = _contract_error(
                    call, "submit_resolution deve ser a única chamada do turno terminal"
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
            if call.name == SUBMIT_RESOLUTION:
                try:
                    resolution = parse_resolution(call.arguments)
                    result = ToolResult(
                        call_id=call.call_id,
                        name=call.name,
                        data={"accepted": True, "resolution": resolution.model_dump(mode="json")},
                    )
                except ValidationError as exc:
                    result = _contract_error(call, f"resolução inválida: {exc}")
                    resolution = None

                tracer.record_tool(
                    agent=role.name,
                    reasoning=response.message.content,
                    call=call,
                    result=result,
                )
                if resolution is not None:
                    return ReactOutcome(resolution, "sufficient")
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

    return ReactOutcome(None, "max_steps")
