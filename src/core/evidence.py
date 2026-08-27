"""Resolução determinística de referências de evidência no trace."""

from __future__ import annotations

import json
from typing import Any

from src.core.contracts.resolution import EvidenceRef
from src.core.contracts.trace import ExecutionTrace

__all__ = ["evidence_matches", "resolve_field"]


def resolve_field(value: Any, path: str) -> Any:
    """Percorre objetos JSON por caminho pontuado; índices de lista são numéricos."""
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def evidence_matches(reference: EvidenceRef, trace: ExecutionTrace) -> bool:
    """Confirma passo, tool, caminho e valor — não apenas a existência da tool."""
    step = next((item for item in trace.steps if item.step == reference.step), None)
    if step is None or step.tool != reference.tool or step.result is None:
        return False
    try:
        actual = resolve_field(step.result, reference.field)
    except KeyError:
        return False
    return _text(actual) == reference.value
