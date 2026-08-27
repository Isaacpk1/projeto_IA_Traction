"""Duplo do provedor de LLM — doc 14 §6.1.

TDD exige teste rápido e determinístico. Um agente que chama LLM não é nenhum dos dois.
A solução não é abrir mão do TDD — é injetar um duplo na porta `LLMClient`.

**Isto é o hexagonal se pagando.**
"""

from __future__ import annotations

from collections.abc import Callable

from src.core.contracts.llm import LLMResponse, Message, Usage
from src.core.contracts.tool import ToolCall, ToolDef

__all__ = ["FakeLLMClient", "say", "call_tool", "call_tools"]


def call_tool(name: str, arguments: dict | None = None, *, thought: str = "") -> LLMResponse:
    """Resposta com uma única tool call."""
    return call_tools([(name, arguments or {})], thought=thought)


def call_tools(calls: list[tuple[str, dict]], *, thought: str = "") -> LLMResponse:
    """Resposta com N tool calls no mesmo passo (paralelismo do modelo)."""
    return LLMResponse(
        message=Message(
            role="assistant",
            content=thought or None,
            tool_calls=[
                ToolCall(call_id=f"call_{i}", name=name, arguments=args)
                for i, (name, args) in enumerate(calls)
            ],
        ),
        usage=Usage(tokens_in=100, tokens_out=20),
        model="fake",
        provider="fake",
    )


def say(text: str) -> LLMResponse:
    """Resposta sem tool call — encerra o loop com `stop_reason='sufficient'`."""
    return LLMResponse(
        message=Message(role="assistant", content=text),
        usage=Usage(tokens_in=100, tokens_out=20),
        model="fake",
        provider="fake",
        finish_reason="stop",
    )


class FakeLLMClient:
    """Devolve uma sequência roteirizada. Determinístico, instantâneo, sem cota.

    Registra `calls` (mensagens e tools recebidas em cada turno), o que permite asserções
    sobre **o que o agente viu** — em particular, sobre o catálogo composto por papel,
    que é o objeto de RF12.
    """

    def __init__(
        self,
        script: list[LLMResponse] | None = None,
        *,
        model: str = "fake-model",
        provider: str = "fake",
        on_exhausted: Callable[[], LLMResponse] | None = None,
    ) -> None:
        self.script = list(script or [])
        self.model = model
        self.provider = provider
        self.calls: list[tuple[list[Message], list[ToolDef]]] = []
        #: Por padrão, roteiro esgotado devolve texto — o loop encerra por suficiência
        #: em vez de estourar `IndexError` e mascarar o teste como falha de infra.
        self.on_exhausted = on_exhausted or (lambda: say("(roteiro esgotado)"))

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        temperature: float = 0.0,
        **kwargs: object,
    ) -> LLMResponse:
        self.calls.append((list(messages), list(tools or [])))
        if not self.script:
            return self.on_exhausted()
        return self.script.pop(0)

    # --- asserções de conveniência -------------------------------------------

    @property
    def n_calls(self) -> int:
        return len(self.calls)

    def tools_offered(self, turn: int = 0) -> set[str]:
        """Nomes das tools oferecidas ao modelo num turno — insumo do teste de RF12."""
        return {t.name for t in self.calls[turn][1]}
