"""Guarda bloqueante contra vazamento do gabarito para a execução (RNF02)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.core.contracts.golden import GOLDEN_ONLY_FIELDS
from src.core.errors import IsolationViolation

__all__ = ["IsolationGuard"]


class IsolationGuard:
    def check(self, value: Any) -> None:
        leaked = self._find(value)
        if leaked:
            raise IsolationViolation(f"gabarito exposto à execução: {', '.join(sorted(leaked))}")

    def _find(self, value: Any) -> set[str]:
        if isinstance(value, BaseModel):
            return self._find(value.model_dump())
        if isinstance(value, dict):
            keys = {str(key) for key in value}.intersection(GOLDEN_ONLY_FIELDS)
            for child in value.values():
                keys.update(self._find(child))
            return keys
        if isinstance(value, list | tuple | set):
            leaked: set[str] = set()
            for child in value:
                leaked.update(self._find(child))
            return leaked
        return set()
