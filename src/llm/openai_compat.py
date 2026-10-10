"""Adaptador assíncrono para APIs compatíveis com OpenAI, usado pelo juiz."""

from __future__ import annotations

import json
from typing import Any

from src.core.contracts.llm import LLMResponse, Message, Usage
from src.core.contracts.tool import ToolCall, ToolDef

__all__ = ["OpenAICompatibleClient"]


class OpenAICompatibleClient:
    def __init__(
        self,
        model: str,
        *,
        api_key: str,
        base_url: str,
        provider: str,
        client: Any | None = None,
    ) -> None:
        if client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover - extra opcional
                raise RuntimeError("instale o extra 'agent' para executar o juiz") from exc
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._client = client
        self.model = model
        self.provider = provider

    async def aclose(self) -> None:
        await self._client.close()

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        temperature: float = 0.0,
        **kwargs: object,
    ) -> LLMResponse:
        payload = [
            {"role": message.role, "content": message.content or ""}
            for message in messages
            if message.role != "tool"
        ]
        tool_payload = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools or []
        ]
        create: Any = self._client.chat.completions.create
        response = await create(
            model=self.model,
            messages=payload,
            tools=tool_payload or None,
            tool_choice="required" if tool_payload else None,
            temperature=temperature,
            **kwargs,
        )
        choice = response.choices[0]
        raw_message = choice.message
        calls = [
            ToolCall(
                call_id=call.id,
                name=call.function.name,
                arguments=json.loads(call.function.arguments),
            )
            for call in (raw_message.tool_calls or [])
        ]
        usage = response.usage
        return LLMResponse(
            message=Message(role="assistant", content=raw_message.content, tool_calls=calls),
            usage=Usage(
                tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
                tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            ),
            model=self.model,
            provider=self.provider,
            finish_reason=choice.finish_reason,
        )
