"""Instrumentação do loop ReAct sobre a porta canônica `TraceSink`."""

from __future__ import annotations

import time

from src.core.contracts.llm import Usage
from src.core.contracts.resolution import Resolution
from src.core.contracts.tool import ToolCall, ToolResult
from src.core.contracts.trace import ExecutionTrace, StopReason, TraceStep
from src.core.ports.trace_sink import TraceSink

__all__ = ["TraceRecorder"]


class TraceRecorder:
    """Mantém o trace em memória e persiste cada observação antes de prosseguir."""

    def __init__(self, trace: ExecutionTrace, sink: TraceSink) -> None:
        self.trace = trace
        self.sink = sink
        self._started = time.perf_counter()
        self._next_step = 0
        self.sink.open(trace.model_copy(deep=True))

    def record_tool(
        self,
        *,
        agent: str,
        reasoning: str | None,
        call: ToolCall,
        result: ToolResult,
    ) -> TraceStep:
        step = TraceStep(
            step=self._next_step,
            agent=agent,
            reasoning=reasoning,
            tool=call.name,
            args=call.arguments,
            result=result.data,
            error=result.error,
            latency_ms=result.latency_ms,
            t_offset_ms=(time.perf_counter() - self._started) * 1000,
        )
        self._next_step += 1
        self.trace.steps.append(step)
        self.sink.record(self.trace.execution_id, step.model_copy(deep=True))
        return step

    def record_reasoning(self, *, agent: str, reasoning: str | None, error: str) -> TraceStep:
        step = TraceStep(
            step=self._next_step,
            agent=agent,
            reasoning=reasoning,
            error=error,
            t_offset_ms=(time.perf_counter() - self._started) * 1000,
        )
        self._next_step += 1
        self.trace.steps.append(step)
        self.sink.record(self.trace.execution_id, step.model_copy(deep=True))
        return step

    def add_usage(
        self,
        usage: Usage,
        *,
        agent: str,
        model: str,
        model_version: str,
        provider: str,
    ) -> None:
        self.trace.tokens_in += usage.tokens_in
        self.trace.tokens_out += usage.tokens_out
        self.trace.llm_calls += 1
        self.trace.models_by_agent.setdefault(agent, model)
        if model_version:
            self.trace.model_versions_by_agent[agent] = model_version
        self.trace.provider_by_agent.setdefault(agent, provider)

    def finish(
        self,
        *,
        reason: StopReason,
        resolution: Resolution | None = None,
        error_class: str | None = None,
    ) -> ExecutionTrace:
        self.trace.stop_reason = reason
        self.trace.resolution = resolution
        self.trace.error_class = error_class
        self.trace.duration_ms = (time.perf_counter() - self._started) * 1000
        self.sink.close(self.trace.model_copy(deep=True))
        return self.trace
