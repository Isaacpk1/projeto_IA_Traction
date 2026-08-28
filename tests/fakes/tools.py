"""Duplo da camada de ferramentas — doc 14 §6.1.

Permite testar o loop ReAct e os guards sem API no ar. Aceita retornos crus (embrulhados
no envelope `complete`) ou envelopes explícitos, o que é o que torna possível escrever um
teste de degradação sem subir nada.
"""

from __future__ import annotations

import time
from typing import Any

from src.core.contracts.tool import Tier, ToolDef, ToolResult

__all__ = ["FakeToolProvider", "envelope", "tool_def"]


def envelope(data: Any, mode: str = "complete", notes: str | None = None) -> dict:
    """Envelope de consulta da API industrial: `{status, data, mode, notes}`."""
    return {"status": "ok", "mode": mode, "notes": notes, "data": data}


def tool_def(
    name: str,
    *,
    tier: Tier = "read",
    requires_confirmation: bool = False,
    required_permission: str | None = None,
    description: str = "",
) -> ToolDef:
    return ToolDef(
        name=name,
        description=description or f"tool {name}",
        parameters={"type": "object", "properties": {}},
        tier=tier,
        requires_confirmation=requires_confirmation,
        required_permission=required_permission,
    )


class FakeToolProvider:
    """Catálogo e respostas roteirizados.

    `returns` mapeia nome da tool → retorno. Um valor que não seja um envelope é
    embrulhado como `complete`, para que o caso feliz seja de uma linha.
    `sequences` permite retornos distintos por chamada da mesma tool (ex.: `conflict`
    na segunda consulta).
    """

    def __init__(
        self,
        returns: dict[str, Any] | None = None,
        *,
        defs: list[ToolDef] | None = None,
        sequences: dict[str, list[Any]] | None = None,
        errors: dict[str, str] | None = None,
    ) -> None:
        self.returns = dict(returns or {})
        self.sequences = {k: list(v) for k, v in (sequences or {}).items()}
        self.errors = dict(errors or {})
        names = set(self.returns) | set(self.sequences) | set(self.errors)
        self._defs: dict[str, ToolDef] = {d.name: d for d in (defs or [])}
        for name in names:
            self._defs.setdefault(name, tool_def(name))
        #: Toda chamada recebida, para asserções sobre trajetória e argumentos.
        self.calls: list[tuple[str, dict]] = []

    def catalog(
        self, tiers: set[Tier] | None = None, only: set[str] | None = None
    ) -> list[ToolDef]:
        out = list(self._defs.values())
        if tiers is not None:
            out = [d for d in out if d.tier in tiers]
        if only is not None:
            out = [d for d in out if d.name in only]
        return out

    def get(self, name: str) -> ToolDef | None:
        return self._defs.get(name)

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        call_id: str,
        user_id: str | None = None,
        seed: str | None = None,
    ) -> ToolResult:
        self.calls.append((name, dict(arguments)))
        started = time.perf_counter()
        latency = (time.perf_counter() - started) * 1000

        if name in self.errors:
            return ToolResult(
                call_id=call_id,
                name=name,
                error=self.errors[name],
                error_class="infra",
                latency_ms=latency,
                external_call_emitted=True,
            )
        if name not in self._defs:
            return ToolResult(
                call_id=call_id,
                name=name,
                error=f"tool desconhecida: {name}",
                error_class="contract",
                latency_ms=latency,
                external_call_emitted=False,
            )

        if name in self.sequences and self.sequences[name]:
            raw = self.sequences[name].pop(0)
        else:
            raw = self.returns.get(name, {})

        data = raw if isinstance(raw, dict) and "mode" in raw else envelope(raw)
        return ToolResult(
            call_id=call_id,
            name=name,
            data=data,
            latency_ms=latency,
            external_call_emitted=True,
        )

    # --- asserções de conveniência -------------------------------------------

    def called(self, name: str) -> bool:
        return any(c == name for c, _ in self.calls)

    def call_index(self, name: str) -> int:
        """Índice da primeira chamada a `name`, ou -1. Insumo dos testes de ordem (M5a)."""
        for i, (called, _) in enumerate(self.calls):
            if called == name:
                return i
        return -1
