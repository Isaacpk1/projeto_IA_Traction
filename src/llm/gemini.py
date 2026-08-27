"""Adaptador assíncrono do SDK oficial Google Gen AI para `LLMClient`."""

from __future__ import annotations

import json
from typing import Any

from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from src.core.contracts.llm import LLMResponse, Message, Usage
from src.core.contracts.tool import ToolCall, ToolDef

__all__ = ["GeminiClient"]


def _retriable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429 or isinstance(status, int) and status >= 500:
        return True
    return type(exc).__name__ in {
        "ClientError",
        "ServerError",
        "APIError",
        "ReadTimeout",
        "ConnectTimeout",
        "ConnectError",
    }


class GeminiClient:
    provider = "google-ai-studio"

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        *,
        api_key: str | None = None,
        client: Any | None = None,
        max_attempts: int = 5,
    ) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - depende do extra opcional
            raise RuntimeError(
                "instale o extra 'agent' para usar Gemini: uv sync --extra agent"
            ) from exc

        self.model = model
        self.max_attempts = max_attempts
        self._client = client or genai.Client(api_key=api_key)

    async def aclose(self) -> None:
        await self._client.aio.aclose()

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        temperature: float = 0.0,
        **kwargs: object,
    ) -> LLMResponse:
        from google.genai import types

        system = "\n\n".join(m.content or "" for m in messages if m.role == "system")
        contents = self._contents(messages, types)
        declarations = [
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters_json_schema=tool.parameters,
            )
            for tool in tools or []
        ]
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            temperature=temperature,
            tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        response: Any = None
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_retriable),
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential_jitter(initial=0.5, max=8.0),
            reraise=True,
        ):
            with attempt:
                response = await self._client.aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
        return self._response(response)

    @staticmethod
    def _contents(messages: list[Message], types: Any) -> list[Any]:
        contents = []
        for message in messages:
            if message.role == "system":
                continue
            parts = []
            if message.content:
                if message.role == "tool":
                    try:
                        payload = json.loads(message.content)
                    except json.JSONDecodeError:
                        payload = {"raw": message.content}
                    parts.append(
                        types.Part.from_function_response(
                            name=message.name or "unknown_tool", response=payload
                        )
                    )
                else:
                    parts.append(types.Part.from_text(text=message.content))
            parts.extend(
                types.Part.from_function_call(name=call.name, args=call.arguments)
                for call in message.tool_calls
            )
            if parts:
                # Gemini representa respostas de function calling como turnos do usuario.
                role = "model" if message.role == "assistant" else "user"
                contents.append(types.Content(role=role, parts=parts))
        return contents

    def _response(self, response: Any) -> LLMResponse:
        content = response.candidates[0].content
        texts: list[str] = []
        calls: list[ToolCall] = []
        for index, part in enumerate(content.parts or []):
            if getattr(part, "text", None):
                texts.append(part.text)
            function_call = getattr(part, "function_call", None)
            if function_call:
                calls.append(
                    ToolCall(
                        call_id=getattr(function_call, "id", None) or f"gemini_call_{index}",
                        name=function_call.name,
                        arguments=dict(function_call.args or {}),
                    )
                )
        usage = getattr(response, "usage_metadata", None)
        finish = getattr(response.candidates[0], "finish_reason", None)
        raw = response.model_dump(mode="json") if hasattr(response, "model_dump") else None
        return LLMResponse(
            message=Message(
                role="assistant",
                content="\n".join(texts) or None,
                tool_calls=calls,
            ),
            usage=Usage(
                tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
                tokens_out=getattr(usage, "candidates_token_count", 0) or 0,
            ),
            model=self.model,
            model_version=getattr(response, "model_version", "") or "",
            provider=self.provider,
            finish_reason=getattr(finish, "value", None) or (str(finish) if finish else None),
            raw=raw,
        )
