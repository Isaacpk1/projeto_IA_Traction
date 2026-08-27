"""Porta de persistência do trace — ADR-14.

O `JsonlTraceSink` é **canônico e bloqueante**; o `LangfuseTraceSink` é secundário e sua
falha é engolida. Observabilidade não pode virar ponto único de falha do experimento: se
o Langfuse cair no meio da rodada, nada se perde.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.core.contracts.trace import ExecutionTrace, Handoff, TraceStep

__all__ = ["TraceSink"]


@runtime_checkable
class TraceSink(Protocol):
    def open(self, trace: ExecutionTrace) -> None:
        """Registra o início de uma execução com seus metadados de reprodutibilidade."""
        ...

    def record(self, execution_id: str, step: TraceStep) -> None: ...

    def record_handoff(self, execution_id: str, handoff: Handoff) -> None: ...

    def close(self, trace: ExecutionTrace) -> None:
        """Persiste o trace final. Precisa ocorrer **antes** de marcar a task `done`.

        Se a ordem fosse invertida e o processo caísse entre os dois passos, a task
        ficaria concluída sem trace — perda silenciosa de dado experimental. Na ordem
        correta, uma queda custa no máximo uma execução repetida (doc 11 §2.5).
        """
        ...
