"""Catálogo de tools por nível de impacto. **Registry**, doc 13 §5.2.

É o componente que materializa a composição por papel (RF12). A verificação de RNF05
mora aqui e não no agente: a garantia precisa valer na **montagem** do catálogo, antes de
o modelo existir — é o que a torna estrutural em vez de instrucional.
"""

from __future__ import annotations

from src.core.contracts.tool import Tier, ToolDef
from src.core.errors import CompositionViolation

__all__ = ["TierRegistry"]


class TierRegistry:
    def __init__(self, tools: list[ToolDef]) -> None:
        self._by_name: dict[str, ToolDef] = {}
        for t in tools:
            if t.name in self._by_name:
                raise ValueError(f"tool duplicada no catálogo: {t.name}")
            self._by_name[t.name] = t

    def __len__(self) -> int:
        return len(self._by_name)

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    def all(self) -> list[ToolDef]:
        return list(self._by_name.values())

    def get(self, name: str) -> ToolDef | None:
        return self._by_name.get(name)

    def names(self, tier: Tier | None = None) -> set[str]:
        return {t.name for t in self._by_name.values() if tier is None or t.tier == tier}

    def select(self, tiers: set[Tier] | None = None, only: set[str] | None = None) -> list[ToolDef]:
        """Catálogo filtrado. É a operação que compõe o conjunto de tools de um papel.

        `only` é aplicado **depois** de `tiers`, nunca no lugar dele: pedir uma tool pelo
        nome não pode contornar a restrição de tier, senão a garantia de RF12 dependeria
        de quem escreveu a lista do papel.
        """
        out = self.all()
        if tiers is not None:
            out = [t for t in out if t.tier in tiers]
        if only is not None:
            out = [t for t in out if t.name in only]
        return out

    def assert_no_impact(self, tools: list[ToolDef], *, role: str) -> None:
        """RNF05 / RF12 — interseção não-vazia com `tier: impact` aborta o processo.

        Não devolve booleano de propósito. Um papel de investigação com capacidade de
        agir é um defeito de composição, não uma condição a tratar: se isso acontecer, o
        experimento inteiro estaria medindo outra coisa.
        """
        proibidas = {t.name for t in tools if t.tier == "impact"}
        if proibidas:
            raise CompositionViolation(
                f"papel '{role}' recebeu tools de tier=impact: {sorted(proibidas)}"
            )

    def counts_by_tier(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for t in self._by_name.values():
            out[t.tier] = out.get(t.tier, 0) + 1
        return out
