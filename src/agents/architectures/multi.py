"""Arquitetura multiagente especializada — braços B e C de H1/H4."""

from __future__ import annotations

from importlib.resources import files
from typing import TypedDict, cast

from src.agents.pre_action_guard import PreActionGuardProvider
from src.agents.pre_delivery_guard import PreDeliveryGuard
from src.agents.react import react_loop
from src.agents.role_reports import report_tool, run_report_loop
from src.agents.roles import CONTEXTUALIZER, EXECUTOR, INVESTIGATOR, ORCHESTRATOR, RoleSpec
from src.agents.scoped_tools import ScopedToolProvider
from src.agents.submit_resolution import SUBMIT_RESOLUTION_TOOL
from src.agents.tracer import TraceRecorder
from src.core.contracts.golden import CaseInput
from src.core.contracts.handoff import (
    ActionReport,
    ContextReport,
    InvestigationReport,
    RoutingDecision,
)
from src.core.contracts.resolution import Resolution
from src.core.contracts.trace import ExecutionTrace, Handoff, StopReason
from src.core.errors import ContractError, IsolationViolation, classify
from src.core.ports.architecture import RunContext
from src.core.ports.llm import LLMClient
from src.core.ports.tools import ToolProvider
from src.core.ports.trace_sink import TraceSink

__all__ = ["MultiArchitecture", "MULTI_PROMPT_VERSION"]

MULTI_PROMPT_VERSION = "1.0.0"

CONTEXT_REPORT_TOOL = report_tool(
    "submit_context_report", ContextReport, "Submete o relatório tipado de contexto."
)
INVESTIGATION_REPORT_TOOL = report_tool(
    "submit_investigation_report",
    InvestigationReport,
    "Submete o relatório tipado de investigação.",
)
ACTION_REPORT_TOOL = report_tool(
    "submit_action_report", ActionReport, "Submete o resultado tipado da etapa de execução."
)
ROUTING_DECISION_TOOL = report_tool(
    "submit_routing_decision",
    RoutingDecision,
    "Classifica o caso e seleciona os especialistas necessários.",
)


class _MultiState(TypedDict, total=False):
    routing_decision: RoutingDecision
    context_report: ContextReport
    investigation_report: InvestigationReport
    action_report: ActionReport
    resolution: Resolution
    stop_reason: StopReason
    error_class: str


def _prompt(role: RoleSpec) -> str:
    root = files("src.agents.prompts")
    base = root.joinpath("base.md").read_text(encoding="utf-8")
    if role != ORCHESTRATOR:
        base = base.rsplit("\n7. ", maxsplit=1)[0].rstrip()
    delta = root.joinpath("roles", f"{role.name}.md").read_text(encoding="utf-8")
    return f"{base}\n\n# Papel atual\n\n{delta}"


def _routing_prompt() -> str:
    root = files("src.agents.prompts")
    base = root.joinpath("base.md").read_text(encoding="utf-8")
    base = base.rsplit("\n7. ", maxsplit=1)[0].rstrip()
    delta = root.joinpath("roles", "router.md").read_text(encoding="utf-8")
    return f"{base}\n\n# Papel atual\n\n{delta}"


class MultiArchitecture:
    """Grafo sequencial com capacidades isoladas e consolidação por handoffs tipados."""

    name = "multi"

    def __init__(
        self,
        llms: dict[str, LLMClient],
        tools: ToolProvider,
        sink: TraceSink,
        *,
        delivery_guard: PreDeliveryGuard | None = None,
    ) -> None:
        required = {role.name for role in (CONTEXTUALIZER, INVESTIGATOR, EXECUTOR, ORCHESTRATOR)}
        missing = required - set(llms)
        if missing:
            raise ValueError(f"LLM ausente para os papéis: {sorted(missing)}")
        self.llms = llms
        self.tools = tools
        self.sink = sink
        self.delivery_guard = delivery_guard or PreDeliveryGuard()

    def _scoped(self, role: RoleSpec, provider: ToolProvider | None = None) -> ScopedToolProvider:
        inner = provider or self.tools
        tools = inner.catalog(
            tiers=set(role.tiers),
            only=set(role.tool_names) if role.tool_names is not None else None,
        )
        return ScopedToolProvider(inner, tools)

    @staticmethod
    def _handoff(
        tracer: TraceRecorder,
        from_agent: str,
        to_agent: str,
        report: RoutingDecision | ContextReport | InvestigationReport | ActionReport,
    ) -> None:
        tracer.record_handoff(
            Handoff(
                after_step=max(len(tracer.trace.steps) - 1, 0),
                from_agent=from_agent,
                to_agent=to_agent,
                payload=report.model_dump(mode="json"),
            )
        )

    async def run(self, case: CaseInput, ctx: RunContext) -> ExecutionTrace:
        metadata = ctx.metadata
        trace = ExecutionTrace(
            run_id=ctx.run_id,
            task_id=ctx.task_id,
            execution_id=ctx.execution_id,
            case_id=case.case_id,
            repetition=ctx.repetition,
            architecture=self.name,
            experiment_id=ctx.experiment_id,
            arm=ctx.arm,
            temperature=float(metadata.get("temperature", 0.0)),
            api_seed=ctx.seed,
            degradation_intensity=metadata.get("degradation_intensity"),
            prompt_version=MULTI_PROMPT_VERSION,
            overlay_version=str(metadata.get("overlay_version", "0")),
            tool_schema_version=str(metadata.get("tool_schema_version", "0")),
            api_contract_version=str(metadata.get("api_contract_version", "0")),
            dataset_version=str(metadata.get("dataset_version", "0")),
            code_commit=str(metadata.get("code_commit", "unknown")),
        )
        tracer = TraceRecorder(trace, self.sink)

        try:
            state = await self._run_graph(case, ctx, tracer)
            resolution = state.get("resolution")
            if resolution is None:
                return tracer.finish(
                    reason=state.get("stop_reason", "error"),
                    error_class=state.get("error_class", "behavior"),
                )
            trace.resolution = resolution
            self.delivery_guard.apply(trace)
            return tracer.finish(reason="sufficient", resolution=resolution)
        except IsolationViolation:
            raise
        except Exception as exc:
            tracer.record_reasoning(agent="system", reasoning=None, error=str(exc))
            return tracer.finish(reason="error", error_class=classify(exc))

    async def _run_graph(
        self, case: CaseInput, ctx: RunContext, tracer: TraceRecorder
    ) -> _MultiState:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise ContractError("arquitetura multi exige o extra 'agent' com LangGraph") from exc

        trace = tracer.trace
        contextualizer = self._scoped(CONTEXTUALIZER)
        investigator = self._scoped(INVESTIGATOR)
        guarded = PreActionGuardProvider(
            self.tools,
            trace=tracer.trace,
            confirmation_policy=ctx.confirmation_policy,
            confirmation_grants=ctx.confirmation_grants,
        )
        executor = self._scoped(EXECUTOR, guarded)
        orchestrator = ScopedToolProvider(self.tools, [])

        async def classify_route(state: _MultiState) -> _MultiState:
            outcome = await run_report_loop(
                case=case,
                role=ORCHESTRATOR,
                prompt=_routing_prompt(),
                llm=self.llms[ORCHESTRATOR.name],
                provider=orchestrator,
                api_tools=[],
                terminal_tool=ROUTING_DECISION_TOOL,
                report_model=RoutingDecision,
                tracer=tracer,
                max_steps=ctx.max_steps,
                temperature=trace.temperature,
                seed=ctx.seed,
            )
            if not isinstance(outcome.report, RoutingDecision):
                return {
                    "stop_reason": outcome.stop_reason,
                    "error_class": outcome.error_class or "behavior",
                }
            return {"routing_decision": outcome.report}

        async def contextualize(state: _MultiState) -> _MultiState:
            self._handoff(
                tracer, ORCHESTRATOR.name, CONTEXTUALIZER.name, state["routing_decision"]
            )
            outcome = await run_report_loop(
                case=case,
                role=CONTEXTUALIZER,
                prompt=_prompt(CONTEXTUALIZER),
                llm=self.llms[CONTEXTUALIZER.name],
                provider=contextualizer,
                api_tools=contextualizer.catalog(),
                terminal_tool=CONTEXT_REPORT_TOOL,
                report_model=ContextReport,
                tracer=tracer,
                max_steps=ctx.max_steps,
                temperature=trace.temperature,
                seed=ctx.seed,
                context={"routing": state["routing_decision"].model_dump(mode="json")},
            )
            if not isinstance(outcome.report, ContextReport):
                return {
                    "stop_reason": outcome.stop_reason,
                    "error_class": outcome.error_class or "behavior",
                }
            self._handoff(tracer, CONTEXTUALIZER.name, ORCHESTRATOR.name, outcome.report)
            return {"context_report": outcome.report}

        async def investigate(state: _MultiState) -> _MultiState:
            self._handoff(
                tracer, ORCHESTRATOR.name, INVESTIGATOR.name, state["routing_decision"]
            )
            reports = {"routing": state["routing_decision"].model_dump(mode="json")}
            if context_report := state.get("context_report"):
                reports["context"] = context_report.model_dump(mode="json")
            outcome = await run_report_loop(
                case=case,
                role=INVESTIGATOR,
                prompt=_prompt(INVESTIGATOR),
                llm=self.llms[INVESTIGATOR.name],
                provider=investigator,
                api_tools=investigator.catalog(),
                terminal_tool=INVESTIGATION_REPORT_TOOL,
                report_model=InvestigationReport,
                tracer=tracer,
                max_steps=ctx.max_steps,
                temperature=trace.temperature,
                seed=ctx.seed,
                context=reports,
            )
            if not isinstance(outcome.report, InvestigationReport):
                return {
                    "stop_reason": outcome.stop_reason,
                    "error_class": outcome.error_class or "behavior",
                }
            self._handoff(tracer, INVESTIGATOR.name, ORCHESTRATOR.name, outcome.report)
            return {"investigation_report": outcome.report}

        async def execute(state: _MultiState) -> _MultiState:
            self._handoff(tracer, ORCHESTRATOR.name, EXECUTOR.name, state["routing_decision"])
            reports = {
                "routing": state["routing_decision"].model_dump(mode="json"),
                "investigation": state["investigation_report"].model_dump(mode="json"),
            }
            if context_report := state.get("context_report"):
                reports["context"] = context_report.model_dump(mode="json")
            outcome = await run_report_loop(
                case=case,
                role=EXECUTOR,
                prompt=_prompt(EXECUTOR),
                llm=self.llms[EXECUTOR.name],
                provider=executor,
                api_tools=executor.catalog(),
                terminal_tool=ACTION_REPORT_TOOL,
                report_model=ActionReport,
                tracer=tracer,
                max_steps=ctx.max_steps,
                temperature=trace.temperature,
                seed=ctx.seed,
                context=reports,
            )
            if not isinstance(outcome.report, ActionReport):
                return {
                    "stop_reason": outcome.stop_reason,
                    "error_class": outcome.error_class or "behavior",
                }
            self._handoff(tracer, EXECUTOR.name, ORCHESTRATOR.name, outcome.report)
            return {"action_report": outcome.report}

        async def consolidate(state: _MultiState) -> _MultiState:
            reports = {"routing": state["routing_decision"].model_dump(mode="json")}
            if context_report := state.get("context_report"):
                reports["context"] = context_report.model_dump(mode="json")
            if investigation_report := state.get("investigation_report"):
                reports["investigation"] = investigation_report.model_dump(mode="json")
            if action_report := state.get("action_report"):
                reports["action"] = action_report.model_dump(mode="json")
            outcome = await react_loop(
                case=case,
                role=ORCHESTRATOR,
                prompt=_prompt(ORCHESTRATOR),
                llm=self.llms[ORCHESTRATOR.name],
                provider=orchestrator,
                api_tools=[],
                application_tools=[SUBMIT_RESOLUTION_TOOL],
                tracer=tracer,
                max_steps=ctx.max_steps,
                temperature=trace.temperature,
                seed=ctx.seed,
                context=reports,
            )
            if outcome.resolution is None:
                return {
                    "stop_reason": outcome.stop_reason,
                    "error_class": outcome.error_class or "behavior",
                }
            return {"resolution": outcome.resolution, "stop_reason": outcome.stop_reason}

        def after_classification(state: _MultiState) -> str:
            if state.get("error_class"):
                return "stop"
            specialists = state["routing_decision"].specialists
            if "contextualizer" in specialists:
                return "contextualizer"
            if "investigator" in specialists:
                return "investigator"
            return "orchestrator"

        def after_context(state: _MultiState) -> str:
            if state.get("error_class"):
                return "stop"
            specialists = state["routing_decision"].specialists
            return "investigator" if "investigator" in specialists else "orchestrator"

        def after_investigation(state: _MultiState) -> str:
            if state.get("error_class"):
                return "stop"
            specialists = state["routing_decision"].specialists
            return "executor" if "executor" in specialists else "orchestrator"

        def after_executor(state: _MultiState) -> str:
            return "stop" if state.get("error_class") else "orchestrator"

        graph = StateGraph(_MultiState)
        graph.add_node("classify", classify_route)
        graph.add_node("contextualizer", contextualize)
        graph.add_node("investigator", investigate)
        graph.add_node("executor", execute)
        graph.add_node("orchestrator", consolidate)
        graph.add_edge(START, "classify")
        graph.add_conditional_edges(
            "classify",
            after_classification,
            {
                "contextualizer": "contextualizer",
                "investigator": "investigator",
                "orchestrator": "orchestrator",
                "stop": END,
            },
        )
        graph.add_conditional_edges(
            "contextualizer",
            after_context,
            {"investigator": "investigator", "orchestrator": "orchestrator", "stop": END},
        )
        graph.add_conditional_edges(
            "investigator",
            after_investigation,
            {"executor": "executor", "orchestrator": "orchestrator", "stop": END},
        )
        graph.add_conditional_edges(
            "executor", after_executor, {"orchestrator": "orchestrator", "stop": END}
        )
        graph.add_edge("orchestrator", END)
        result = await graph.compile().ainvoke({})
        return cast(_MultiState, result)
