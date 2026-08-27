"""Construtores de trace sintético.

Duas camadas, de propósito:

- as **factories** (polyfactory) preenchem tudo com valores válidos, e servem para testar
  serialização, schema e round-trip;
- os **construtores explícitos** (`make_trace`, `step`, `evidence`) montam o caso concreto
  que um teste de métrica precisa. Um scorer testado sobre dado aleatório não prova nada:
  o teste que dá valor à métrica é o que a faz **discriminar** dois cenários próximos.
"""

from __future__ import annotations

from typing import Any

from polyfactory.factories.pydantic_factory import ModelFactory

from src.core.contracts.golden import GoldenCase
from src.core.contracts.resolution import Decision, EvidenceRef, Resolution
from src.core.contracts.trace import Architecture, ExecutionTrace, Handoff, TraceStep

__all__ = [
    "ExecutionTraceFactory",
    "ResolutionFactory",
    "GoldenCaseFactory",
    "step",
    "evidence",
    "make_trace",
]


class ResolutionFactory(ModelFactory[Resolution]):
    __model__ = Resolution


class ExecutionTraceFactory(ModelFactory[ExecutionTrace]):
    __model__ = ExecutionTrace


class GoldenCaseFactory(ModelFactory[GoldenCase]):
    __model__ = GoldenCase


def step(
    tool: str | None = None,
    result: Any = None,
    *,
    n: int = 0,
    agent: str = "agent",
    mode: str = "complete",
    args: dict | None = None,
    reasoning: str | None = None,
    error: str | None = None,
) -> TraceStep:
    """Um passo de trace. `result` cru é embrulhado no envelope de consulta."""
    payload: dict | None
    if result is None:
        payload = None
    elif isinstance(result, dict) and "mode" in result:
        payload = result
    else:
        payload = {"status": "ok", "mode": mode, "notes": None, "data": result}
    return TraceStep(
        step=n,
        agent=agent,
        tool=tool,
        args=args,
        result=payload,
        reasoning=reasoning,
        error=error,
    )


def evidence(tool: str, field: str, value: str, step_n: int = 0) -> EvidenceRef:
    return EvidenceRef(tool=tool, field=field, value=value, step=step_n)


def make_trace(
    steps: list[TraceStep] | list[tuple[str, Any]] | None = None,
    *,
    resolution: Resolution | None = None,
    decision: Decision = "orientar",
    architecture: Architecture = "mono",
    handoffs: list[Handoff] | None = None,
    execution_id: str = "exec_test",
    case_id: str = "case_test",
    **kwargs: Any,
) -> ExecutionTrace:
    """Monta um trace válido a partir do mínimo que o teste precisa declarar.

    Aceita `steps` como lista de `TraceStep` ou como lista de tuplas `(tool, retorno)`,
    numeradas automaticamente — a forma curta cobre a maioria dos testes de scorer.
    """
    normalizados: list[TraceStep] = []
    for i, s in enumerate(steps or []):
        if isinstance(s, TraceStep):
            normalizados.append(s)
        else:
            tool, result = s
            normalizados.append(step(tool, result, n=i))

    return ExecutionTrace(
        task_id=kwargs.pop("task_id", "task_test"),
        execution_id=execution_id,
        case_id=case_id,
        architecture=architecture,
        arm=kwargs.pop("arm", "A" if architecture == "mono" else "B"),
        steps=normalizados,
        handoffs=handoffs or [],
        resolution=resolution
        if resolution is not None
        else Resolution(decision=decision, justification="justificativa de teste"),
        **kwargs,
    )
