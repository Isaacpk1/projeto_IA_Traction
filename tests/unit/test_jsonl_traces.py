"""Trace JSONL canônico e composição best-effort (ADR-14)."""

from __future__ import annotations

import json

import pytest

from src.core.contracts.trace import ExecutionTrace, TraceStep
from src.storage.jsonl_traces import CompositeTraceSink, JsonlTraceSink
from tests.fakes.sinks import AlwaysFailingSink


def _trace(execution_id: str = "exec_1") -> ExecutionTrace:
    return ExecutionTrace(
        run_id="run_1",
        task_id="task_1",
        execution_id=execution_id,
        case_id="case_1",
        architecture="mono",
        arm="A",
    )


def test_jsonl_e_append_only_valido_e_reconstroi_trace_final(tmp_path):
    sink = JsonlTraceSink(tmp_path)
    trace = _trace()
    step = TraceStep(step=0, agent="agent", tool="getAsset", result={"mode": "complete"})

    sink.open(trace)
    sink.record(trace.execution_id, step)
    trace.steps.append(step)
    trace.stop_reason = "max_steps"
    sink.close(trace)

    path = tmp_path / "run_1" / "exec_1.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [record["type"] for record in records] == [
        "execution_started",
        "step",
        "execution_finished",
    ]
    assert sink.read_final("exec_1") == trace


def test_falha_do_sink_secundario_nao_perde_trace_canonico(tmp_path):
    primary = JsonlTraceSink(tmp_path)
    sink = CompositeTraceSink(primary, AlwaysFailingSink())
    trace = _trace()

    sink.open(trace)
    sink.close(trace)

    assert primary.read_final(trace.execution_id) == trace
    assert [method for method, _ in sink.secondary_failures] == ["open", "close"]


def test_nao_sobrescreve_execution_id_existente(tmp_path):
    sink = JsonlTraceSink(tmp_path)
    trace = _trace()
    sink.open(trace)

    with pytest.raises(FileExistsError):
        JsonlTraceSink(tmp_path).open(trace)
