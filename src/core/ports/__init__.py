"""Portas — interfaces sem implementação (Hexagonal, doc 13 §3).

A regra que governa: *só crie uma porta onde existe, ou está prometida, uma segunda
implementação.* `LLMClient` tem duas (Gemini, OpenAI-compat). `WorkQueue` tem uma e uma
promessa registrada em ADR-10. `Architecture` tem duas — é a variável do experimento.
"""

from src.core.ports.architecture import Architecture, RunContext
from src.core.ports.event_bus import EventBus, RateLimiterPort
from src.core.ports.llm import LLMClient
from src.core.ports.queue import WorkQueue
from src.core.ports.tools import ToolProvider
from src.core.ports.trace_sink import TraceSink

__all__ = [
    "Architecture",
    "EventBus",
    "LLMClient",
    "RateLimiterPort",
    "RunContext",
    "ToolProvider",
    "TraceSink",
    "WorkQueue",
]
