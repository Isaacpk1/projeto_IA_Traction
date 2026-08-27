"""Contratos de conversa com o provedor de LLM.

Modelo neutro de mensagem e resposta. É o que permite que `google-genai` (agente) e o
cliente compatível com OpenAI (juiz e eixo H3) fiquem atrás da mesma porta `LLMClient` —
e que `FakeLLMClient` entre no lugar dos dois nos testes.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.core.contracts.tool import ToolCall

Role = Literal["system", "user", "assistant", "tool"]

__all__ = ["Role", "Message", "Usage", "LLMResponse"]


class Message(BaseModel):
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = Field(
        default=None, description="Preenchido apenas em mensagens de role='tool'"
    )
    name: str | None = None


class Usage(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
        )


class LLMResponse(BaseModel):
    message: Message
    usage: Usage = Field(default_factory=Usage)
    model: str = ""
    model_version: str = ""
    provider: str = ""
    finish_reason: str | None = None
    raw: dict[str, Any] | None = Field(
        default=None, description="Resposta crua do provedor, para depuração"
    )
