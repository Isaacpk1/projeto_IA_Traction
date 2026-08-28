"""Persistência canônica append-only dos traces (ADR-14)."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from src.core.contracts.trace import ExecutionTrace, Handoff, TraceStep

__all__ = ["JsonlTraceSink", "CompositeTraceSink"]


class JsonlTraceSink:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._paths: dict[str, Path] = {}
        self._lock = threading.Lock()

    def _path(self, trace: ExecutionTrace) -> Path:
        run = trace.run_id or "standalone"
        return self.root / run / f"{trace.execution_id}.jsonl"

    def _append(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with self._lock, path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())

    def _create(self, path: Path, record: dict[str, Any]) -> None:
        """Cria o trace de forma exclusiva para impedir colisões entre processos."""
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with self._lock, path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())

    def open(self, trace: ExecutionTrace) -> None:
        path = self._path(trace)
        metadata = trace.model_dump(
            mode="json", exclude={"steps", "handoffs", "action_attempts", "confirmations"}
        )
        try:
            self._create(path, {"type": "execution_started", "trace": metadata})
        except FileExistsError as exc:
            raise FileExistsError(f"trace já existe: {path}") from exc
        self._paths[trace.execution_id] = path

    def record(self, execution_id: str, step: TraceStep) -> None:
        self._append(
            self._paths[execution_id],
            {"type": "step", "execution_id": execution_id, "step": step.model_dump(mode="json")},
        )

    def record_handoff(self, execution_id: str, handoff: Handoff) -> None:
        self._append(
            self._paths[execution_id],
            {
                "type": "handoff",
                "execution_id": execution_id,
                "handoff": handoff.model_dump(mode="json"),
            },
        )

    def close(self, trace: ExecutionTrace) -> None:
        path = self._paths[trace.execution_id]
        self._append(path, {"type": "execution_finished", "trace": trace.model_dump(mode="json")})

    def read_final(self, execution_id: str) -> ExecutionTrace:
        path = self._paths[execution_id]
        final: dict[str, Any] | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("type") == "execution_finished":
                final = record["trace"]
        if final is None:
            raise ValueError(f"trace ainda não foi concluído: {execution_id}")
        return ExecutionTrace.model_validate(final)


class CompositeTraceSink:
    """Sink canônico bloqueante seguido de sinks secundários best-effort."""

    def __init__(self, primary: JsonlTraceSink, *secondary: object) -> None:
        self.primary = primary
        self.secondary = secondary
        self.secondary_failures: list[tuple[str, Exception]] = []

    def _secondary(self, method: str, *args: object) -> None:
        for sink in self.secondary:
            try:
                getattr(sink, method)(*args)
            except Exception as exc:
                self.secondary_failures.append((method, exc))

    def open(self, trace: ExecutionTrace) -> None:
        self.primary.open(trace)
        self._secondary("open", trace)

    def record(self, execution_id: str, step: TraceStep) -> None:
        self.primary.record(execution_id, step)
        self._secondary("record", execution_id, step)

    def record_handoff(self, execution_id: str, handoff: Handoff) -> None:
        self.primary.record_handoff(execution_id, handoff)
        self._secondary("record_handoff", execution_id, handoff)

    def close(self, trace: ExecutionTrace) -> None:
        self.primary.close(trace)
        self._secondary("close", trace)
