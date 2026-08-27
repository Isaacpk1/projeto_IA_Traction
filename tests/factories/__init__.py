"""Fábricas de traces sintéticos — polyfactory sobre os modelos Pydantic.

`ExecutionTrace` tem passos aninhados, handoffs e resolução com evidências. Escrever isso
à mão em cada teste é inviável para 16 métricas × 2 testes cada. Aqui o teste **sobrescreve
só o campo que importa** — é o que torna o TDD das métricas executável em dois dias.
"""

from tests.factories.traces import (
    ExecutionTraceFactory,
    GoldenCaseFactory,
    ResolutionFactory,
    evidence,
    make_trace,
    step,
)

__all__ = [
    "ExecutionTraceFactory",
    "GoldenCaseFactory",
    "ResolutionFactory",
    "evidence",
    "make_trace",
    "step",
]
