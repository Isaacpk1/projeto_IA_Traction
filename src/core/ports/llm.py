"""Porta do provedor de LLM — doc 13 §5.1.

Duas implementações previstas: `llm/gemini.py` (agente) e `llm/openai_compat.py` (juiz,
via Groq, e eixo H3, via OpenRouter). A porta existe porque RNF09 exige que o juiz seja
de provedor distinto do agente — e porque sem ela não há TDD do loop ReAct.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.core.contracts.llm import LLMResponse, Message
from src.core.contracts.tool import ToolDef

__all__ = ["LLMClient"]


@runtime_checkable
class LLMClient(Protocol):
    """Cliente de chat com function calling."""

    model: str
    provider: str

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        temperature: float = 0.0,
        **kwargs: object,
    ) -> LLMResponse: ...
