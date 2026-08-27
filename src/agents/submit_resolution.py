"""Tool terminal da aplicação — valida e captura a resolução estruturada (RF11)."""

from __future__ import annotations

from src.agents.roles import SUBMIT_RESOLUTION
from src.core.contracts.resolution import Resolution
from src.core.contracts.tool import ToolDef

__all__ = ["SUBMIT_RESOLUTION_TOOL", "parse_resolution"]

_EVIDENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string"},
        "field": {"type": "string"},
        "value": {"type": "string"},
        "step": {"type": "integer", "minimum": 0},
    },
    "required": ["tool", "field", "value", "step"],
    "additionalProperties": False,
}

SUBMIT_RESOLUTION_TOOL = ToolDef(
    name=SUBMIT_RESOLUTION,
    description=(
        "Encerra o atendimento com uma resolução estruturada. Use exatamente uma vez, somente "
        "quando houver evidência suficiente para orientar ou agir, ou quando a lacuna exigir "
        "escalar."
    ),
    parameters={
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["orientar", "agir", "escalar"]},
            "justification": {"type": "string", "minLength": 1},
            "evidence_cited": {"type": "array", "items": _EVIDENCE_SCHEMA},
            "unverified": {"type": "array", "items": {"type": "string"}},
            "conflicts": {"type": "array", "items": {"type": "string"}},
            "action_taken": {"type": ["string", "null"]},
            "confirmation_requested": {"type": "boolean"},
        },
        "required": ["decision", "justification"],
        "additionalProperties": False,
    },
)


def parse_resolution(arguments: dict) -> Resolution:
    """Valida a saída terminal; mantém `ValidationError` para o loop devolver ao modelo."""
    return Resolution.model_validate(arguments)
