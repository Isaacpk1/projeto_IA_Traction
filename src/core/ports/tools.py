"""Porta da camada de ferramentas — ADR-01, ADR-12.

A porta **não pressupõe origem única**: tools da API industrial e tools de terceiros
(Slack, Jira, via cliente MCP) são ambas ferramentas com `tier`, e o Executor as recebe
da mesma forma. É o que torna acrescentar um provedor externo um adaptador, e não uma
reforma (ADR-12).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.core.contracts.tool import Tier, ToolDef, ToolResult

__all__ = ["ToolProvider"]


@runtime_checkable
class ToolProvider(Protocol):
    """Catálogo de tools e execução delas."""

    def catalog(
        self, tiers: set[Tier] | None = None, only: set[str] | None = None
    ) -> list[ToolDef]:
        """Tools disponíveis, filtradas por `tier` e/ou por nome.

        É a operação que materializa a composição por papel (RF12): o Investigador
        recebe `tiers={"read"}` e, por construção, não tem tool de impacto no schema.
        """
        ...

    def get(self, name: str) -> ToolDef | None: ...

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        call_id: str,
        user_id: str | None = None,
        seed: str | None = None,
    ) -> ToolResult:
        """Executa uma tool. Nunca levanta por erro do upstream — devolve `ToolResult`
        com `error` preenchido, para que a falha vire observação no trace em vez de
        derrubar o loop."""
        ...
