"""Contratos de dados — validados em toda fronteira (RNF13)."""

from src.core.contracts.events import ExecutionEvent
from src.core.contracts.golden import (
    GOLDEN_ONLY_FIELDS,
    CaseInput,
    ExpectedStep,
    GoldenCase,
    RequiredFact,
)
from src.core.contracts.handoff import (
    ActionReport,
    ContextReport,
    InvestigationReport,
)
from src.core.contracts.llm import LLMResponse, Message, Usage
from src.core.contracts.metrics import (
    HumanLabel,
    HypothesisVerdict,
    Judgment,
    MetricResult,
)
from src.core.contracts.resolution import (
    ActionAttempt,
    Decision,
    Delivered,
    EvidenceRef,
    Finding,
    Resolution,
)
from src.core.contracts.task import Lease, Task
from src.core.contracts.tool import Tier, ToolCall, ToolDef, ToolOverlay, ToolResult
from src.core.contracts.trace import (
    TRACE_SCHEMA_VERSION,
    ExecutionTrace,
    Handoff,
    TraceStep,
)

__all__ = [
    "GOLDEN_ONLY_FIELDS",
    "TRACE_SCHEMA_VERSION",
    "ActionAttempt",
    "ActionReport",
    "CaseInput",
    "ContextReport",
    "Decision",
    "Delivered",
    "EvidenceRef",
    "ExecutionEvent",
    "ExecutionTrace",
    "ExpectedStep",
    "Finding",
    "GoldenCase",
    "Handoff",
    "HumanLabel",
    "HypothesisVerdict",
    "InvestigationReport",
    "Judgment",
    "LLMResponse",
    "Lease",
    "Message",
    "MetricResult",
    "RequiredFact",
    "Resolution",
    "Task",
    "Tier",
    "ToolCall",
    "ToolDef",
    "ToolOverlay",
    "ToolResult",
    "TraceStep",
    "Usage",
]
