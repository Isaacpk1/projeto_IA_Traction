"""Arquitetura mono-agente — condição de controle de H1."""

from __future__ import annotations

from importlib.resources import files
from typing import cast

from src.agents.pre_action_guard import ConfirmationPolicy, PreActionGuardProvider
from src.agents.pre_delivery_guard import PreDeliveryGuard
from src.agents.react import react_loop
from src.agents.roles import MONO
from src.agents.submit_resolution import SUBMIT_RESOLUTION_TOOL
from src.agents.tracer import TraceRecorder
from src.core.contracts.golden import CaseInput
from src.core.contracts.trace import ExecutionTrace
from src.core.errors import ContractError, classify
from src.core.ports.architecture import RunContext
from src.core.ports.llm import LLMClient
from src.core.ports.tools import ToolProvider
from src.core.ports.trace_sink import TraceSink

__all__ = ["MonoArchitecture", "PROMPT_VERSION"]

PROMPT_VERSION = "1.0.0"


def _base_prompt() -> str:
    return files("src.agents.prompts").joinpath("base.md").read_text(encoding="utf-8")


class MonoArchitecture:
    name = "mono"

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolProvider,
        sink: TraceSink,
        *,
        enforce_pre_action_guard: bool = True,
        delivery_guard: PreDeliveryGuard | None = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.sink = sink
        self.enforce_pre_action_guard = enforce_pre_action_guard
        self.delivery_guard = delivery_guard or PreDeliveryGuard()

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
            models_by_agent={MONO.name: self.llm.model},
            provider_by_agent={MONO.name: self.llm.provider},
            temperature=float(metadata.get("temperature", 0.0)),
            api_seed=ctx.seed,
            degradation_intensity=metadata.get("degradation_intensity"),
            prompt_version=PROMPT_VERSION,
            overlay_version=str(metadata.get("overlay_version", "0")),
            tool_schema_version=str(metadata.get("tool_schema_version", "0")),
            api_contract_version=str(metadata.get("api_contract_version", "0")),
            dataset_version=str(metadata.get("dataset_version", "0")),
            code_commit=str(metadata.get("code_commit", "unknown")),
        )
        tracer = TraceRecorder(trace, self.sink)

        try:
            provider: ToolProvider = self.tools
            if self.enforce_pre_action_guard:
                if ctx.confirmation_policy not in {"auto_confirm", "auto_refuse"}:
                    raise ContractError(f"confirmation_policy inválida: {ctx.confirmation_policy}")
                provider = PreActionGuardProvider(
                    self.tools,
                    trace,
                    confirmation_policy=cast(ConfirmationPolicy, ctx.confirmation_policy),
                )
            elif not ctx.dry_run:
                raise ContractError("desabilitar PreActionGuard exige dry_run=True")

            outcome = await react_loop(
                case=case,
                role=MONO,
                prompt=_base_prompt(),
                llm=self.llm,
                provider=provider,
                api_tools=provider.catalog(tiers=set(MONO.tiers)),
                application_tools=[SUBMIT_RESOLUTION_TOOL],
                tracer=tracer,
                max_steps=ctx.max_steps,
                temperature=trace.temperature,
                seed=ctx.seed,
            )
            trace.resolution = outcome.resolution
            self.delivery_guard.apply(trace)
            return tracer.finish(
                reason=outcome.stop_reason,
                resolution=outcome.resolution,
                error_class=outcome.error_class,
            )
        except Exception as exc:
            return tracer.finish(reason="error", error_class=classify(exc))
