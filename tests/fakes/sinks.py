"""Duplos de `TraceSink` e `EventBus`.

`AlwaysFailingSink` existe para um teste específico e importante: garantir que a falha do
sink secundário (Langfuse) nunca perde o trace canônico — ADR-14.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from src.core.contracts.events import ExecutionEvent
from src.core.contracts.trace import ExecutionTrace, Handoff, TraceStep

__all__ = ["MemoryTraceSink", "AlwaysFailingSink", "MemoryEventBus"]


class MemoryTraceSink:
    def __init__(self) -> None:
        self.opened: list[ExecutionTrace] = []
        self.steps: list[tuple[str, TraceStep]] = []
        self.handoffs: list[tuple[str, Handoff]] = []
        self.closed: list[ExecutionTrace] = []

    def open(self, trace: ExecutionTrace) -> None:
        self.opened.append(trace)

    def record(self, execution_id: str, step: TraceStep) -> None:
        self.steps.append((execution_id, step))

    def record_handoff(self, execution_id: str, handoff: Handoff) -> None:
        self.handoffs.append((execution_id, handoff))

    def close(self, trace: ExecutionTrace) -> None:
        self.closed.append(trace)


class AlwaysFailingSink:
    """Simula o sink secundário indisponível."""

    def __init__(self, exc: type[Exception] = RuntimeError) -> None:
        self.exc = exc

    def open(self, trace: ExecutionTrace) -> None:
        raise self.exc("sink secundário fora do ar")

    def record(self, execution_id: str, step: TraceStep) -> None:
        raise self.exc("sink secundário fora do ar")

    def record_handoff(self, execution_id: str, handoff: Handoff) -> None:
        raise self.exc("sink secundário fora do ar")

    def close(self, trace: ExecutionTrace) -> None:
        raise self.exc("sink secundário fora do ar")


class MemoryEventBus:
    def __init__(self, *, fail: bool = False) -> None:
        self.published: list[tuple[str, ExecutionEvent]] = []
        self.fail = fail

    async def publish(self, execution_id: str, event: ExecutionEvent) -> None:
        if self.fail:
            raise ConnectionError("redis indisponível")
        self.published.append((execution_id, event))

    async def subscribe(self, execution_id: str) -> AsyncIterator[ExecutionEvent]:
        for eid, ev in self.published:
            if eid == execution_id:
                yield ev

    def types(self) -> list[str]:
        return [ev.type for _, ev in self.published]
