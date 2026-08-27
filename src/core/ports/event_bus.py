"""Porta de coordenação efêmera — ADR-11.

Redis pub/sub em produção, in-memory nos testes. O critério da divisão: se perder o dado
dói no resultado do experimento, é SQLite; se apenas atrapalha a operação do momento, é
Redis. Nada que atravesse esta porta é durável (RNF17).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from src.core.contracts.events import ExecutionEvent

__all__ = ["EventBus", "RateLimiterPort"]


@runtime_checkable
class EventBus(Protocol):
    async def publish(self, execution_id: str, event: ExecutionEvent) -> None:
        """Publica um evento. Falha aqui é registrada e **não propaga** — o trace já
        foi gravado, e o streaming ao vivo é o único prejudicado."""
        ...

    def subscribe(self, execution_id: str) -> AsyncIterator[ExecutionEvent]: ...


@runtime_checkable
class RateLimiterPort(Protocol):
    """Token bucket na taxa documentada (ADR-09).

    Todos os workers passam por aqui antes de cada chamada, de modo que a concorrência
    deixa de determinar a vazão — 3 workers ou 8 produzem o mesmo RPM. Os workers
    existem apenas para sobrepor latência de I/O.
    """

    async def acquire(self, provider: str, cost: int = 1) -> None: ...

    async def consume_daily(self, provider: str, cost: int = 1) -> int:
        """Incrementa e devolve o consumo do dia — base da guarda de cota (RNF16)."""
        ...
