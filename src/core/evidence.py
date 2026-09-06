"""Resolução determinística de referências de evidência no trace."""

from __future__ import annotations

import json
import re
from typing import Any

from src.core.contracts.resolution import EvidenceRef
from src.core.contracts.trace import ExecutionTrace

__all__ = ["evidence_matches", "observation_view", "resolve_field"]


#: `a[0].b` e `a.0.b` designam a mesma coisa. O prompt nunca fixou a sintaxe, e
#: recusar a forma com colchetes mediria a notação escolhida pelo modelo, não se a
#: evidência existe.
_INDICE = re.compile(r"\[(\d+)\]")


def resolve_field(value: Any, path: str) -> Any:
    """Percorre objetos JSON por caminho pontuado; índices de lista são numéricos."""
    current = value
    for part in _INDICE.sub(r".\1", path).split("."):
        if not part:
            continue
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def observation_view(result: Any) -> dict:
    """A forma em que o passo chega ao modelo — doc 09, loop ReAct.

    O trace guarda `ToolResult.data`; o agente recebe esse valor **embrulhado**
    junto de erro e status. Uma citação como `data.data.state` está correta do
    ponto de vista de quem a escreveu, e resolvê-la só contra a forma do trace
    reprovaria a referência por diferença de camada, não por evidência ausente.
    """
    return {"data": result, "error": None, "error_class": None, "status_code": None}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def evidence_matches(reference: EvidenceRef, trace: ExecutionTrace) -> bool:
    """Confirma passo, tool, caminho e valor — não apenas a existência da tool."""
    step = next((item for item in trace.steps if item.step == reference.step), None)
    if step is None or step.tool != reference.tool or step.result is None:
        return False
    # As duas formas da mesma observação: a que o trace grava e a que o agente viu.
    # O passo e a tool continuam exigidos — afrouxá-los mudaria a métrica, não a
    # corrigiria.
    for shape in (step.result, observation_view(step.result)):
        try:
            actual = resolve_field(shape, reference.field)
        except (KeyError, TypeError):
            continue
        if _text(actual) == reference.value:
            return True
    return False
