"""Contratos e carregamento da rubrica do juiz."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from src.core.contracts.resolution import Resolution
from src.core.errors import ContractError

_DEFAULT_RUBRIC = Path(__file__).with_name("rubric.yaml")


class JudgeInput(BaseModel):
    case_message: str
    user_role: str = "unknown"
    resolution: Resolution
    tools_called: list[str] = Field(default_factory=list)
    api_modes_seen: list[str] = Field(default_factory=list)
    evidence_available: list[dict] = Field(default_factory=list)


class RubricCriterion(BaseModel):
    id: str
    question: str
    applies_when: Literal[
        "analysis_baseline",
        "threshold_discussed",
        "degraded",
        "always",
        "action",
        "detection_mode",
        "conflict",
        "escalation",
    ]


class Rubric(BaseModel):
    version: str
    criteria: list[RubricCriterion]


def load_rubric(path: str | Path = _DEFAULT_RUBRIC) -> Rubric:
    try:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        rubric = Rubric.model_validate(payload)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise ContractError(f"rubrica do juiz inválida em {path}: {exc}") from exc
    ids = [criterion.id for criterion in rubric.criteria]
    if len(ids) != len(set(ids)):
        raise ContractError("rubrica do juiz contém criterion_id duplicado")
    return rubric
