"""Provider de capacidade mínima por papel — garantia executável de RF12."""

from __future__ import annotations

from src.core.contracts.tool import Tier, ToolDef, ToolResult
from src.core.ports.tools import ToolProvider

__all__ = ["ScopedToolProvider"]


class ScopedToolProvider:
    """Expõe e executa somente as tools materializadas para um papel."""

    def __init__(self, inner: ToolProvider, tools: list[ToolDef]) -> None:
        self.inner = inner
        self._tools = {tool.name: tool for tool in tools}

    def catalog(
        self, tiers: set[Tier] | None = None, only: set[str] | None = None
    ) -> list[ToolDef]:
        selected = list(self._tools.values())
        if tiers is not None:
            selected = [tool for tool in selected if tool.tier in tiers]
        if only is not None:
            selected = [tool for tool in selected if tool.name in only]
        return selected

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        call_id: str,
        user_id: str | None = None,
        seed: str | None = None,
    ) -> ToolResult:
        if name not in self._tools:
            return ToolResult(
                call_id=call_id,
                name=name,
                error=f"tool fora da capacidade deste papel: {name}",
                error_class="contract",
                external_call_emitted=False,
            )
        return await self.inner.call(
            name,
            arguments,
            call_id=call_id,
            user_id=user_id,
            seed=seed,
        )
