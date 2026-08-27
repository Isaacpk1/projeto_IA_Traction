"""`ToolProvider` — a superfície que os agentes consomem. ADR-01.

É aqui que o núcleo genérico encontra o overlay de domínio: o parser produz operações, o
overlay produz semântica e política, a fábrica funde os dois e o registry compõe por
papel. O agente vê apenas `catalog()` e `call()`.

A camada funciona como **biblioteca Python**. O envelope MCP (`mcp_wrapper.py`) é um
adaptador aditivo sobre estas mesmas funções — não uma reescrita.
"""

from __future__ import annotations

from pathlib import Path

from src.core.contracts.tool import Tier, ToolDef, ToolResult
from src.tools.core.http_executor import HttpExecutor
from src.tools.core.openapi_parser import parse_contract
from src.tools.core.tier_registry import TierRegistry
from src.tools.core.tool_factory import build_tools, schema_fingerprint
from src.tools.overlay import Overlay, OverlayMode, load_overlay

__all__ = ["ApiToolProvider", "DryRunToolProvider", "build_registry"]


def build_registry(
    contract_path: str | Path,
    *,
    overlay: Overlay | None = None,
    overlay_path: str | Path | None = None,
    mode: OverlayMode = "enriched",
) -> tuple[TierRegistry, Overlay]:
    """Monta o catálogo na inicialização — contrato + overlay ⇒ tools.

    Emite aviso quando o overlay e o contrato saem de sincronia (ADR-02): operação sem
    entrada de overlay vira tool com descrição crua, que degrada a seleção de função sem
    quebrar nada — o tipo de defeito que só aparece na leitura de um trace.
    """
    ov = (overlay or load_overlay(overlay_path)).model_copy(update={"mode": mode})
    ops = parse_contract(contract_path)

    sem_overlay, orfaos = ov.check_coverage([op.operation_id for op in ops])
    if sem_overlay or orfaos:
        import warnings

        if sem_overlay:
            warnings.warn(
                f"operações sem overlay (descrição crua): {sorted(sem_overlay)}",
                stacklevel=2,
            )
        if orfaos:
            warnings.warn(
                f"overlay declara operações inexistentes no contrato: {sorted(orfaos)}",
                stacklevel=2,
            )

    metadados = {op.operation_id: ov.for_tool(op.operation_id, mode=mode) for op in ops}
    tools = build_tools(ops, metadados)
    return TierRegistry(tools), ov


class ApiToolProvider:
    """Provider real: catálogo derivado do contrato, execução por HTTP."""

    def __init__(
        self,
        registry: TierRegistry,
        executor: HttpExecutor,
        *,
        overlay: Overlay | None = None,
        default_user_id: str | None = None,
        default_seed: str | None = None,
    ) -> None:
        self.registry = registry
        self.executor = executor
        self.overlay = overlay
        self.default_user_id = default_user_id
        self.default_seed = default_seed

    @property
    def schema_version(self) -> str:
        return schema_fingerprint(self.registry.all())

    @property
    def overlay_version(self) -> str:
        return f"{self.overlay.version}:{self.overlay.mode}" if self.overlay else "0"

    def catalog(
        self, tiers: set[Tier] | None = None, only: set[str] | None = None
    ) -> list[ToolDef]:
        return self.registry.select(tiers=tiers, only=only)

    def get(self, name: str) -> ToolDef | None:
        return self.registry.get(name)

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        call_id: str,
        user_id: str | None = None,
        seed: str | None = None,
    ) -> ToolResult:
        tool = self.registry.get(name)
        if tool is None:
            # O modelo alucinou um nome de tool. É `contract`, não `behavior`: o
            # catálogo é fechado e a chamada nunca deveria ter sido possível.
            return ToolResult(
                call_id=call_id,
                name=name,
                error=f"tool desconhecida: {name}",
                error_class="contract",
            )
        return await self.executor.execute(
            tool,
            arguments,
            call_id=call_id,
            user_id=user_id or self.default_user_id,
            seed=seed or self.default_seed,
        )


class DryRunToolProvider:
    """Envelope que suprime efeitos externos de tools `tier: impact`.

    Obrigatório no braço `prompt_only` de E2 (RF/E2): esse braço mede **tentativas**
    inseguras, e medi-las produzindo efeito real seria inaceitável. A tentativa continua
    registrada no trace — é isso que mantém M10 mensurável — mas nenhuma chamada externa
    é emitida.

    Tools `tier: read` passam direto: elas não produzem efeito, e bloqueá-las mudaria o
    que o braço investiga.
    """

    def __init__(self, inner: ApiToolProvider) -> None:
        self.inner = inner
        #: Toda tentativa suprimida, para conferência com `trace.action_attempts`.
        self.suppressed: list[tuple[str, dict]] = []

    def catalog(
        self, tiers: set[Tier] | None = None, only: set[str] | None = None
    ) -> list[ToolDef]:
        return self.inner.catalog(tiers=tiers, only=only)

    def get(self, name: str) -> ToolDef | None:
        return self.inner.get(name)

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        call_id: str,
        user_id: str | None = None,
        seed: str | None = None,
    ) -> ToolResult:
        tool = self.inner.get(name)
        if tool is not None and tool.tier == "impact":
            self.suppressed.append((name, dict(arguments)))
            return ToolResult(
                call_id=call_id,
                name=name,
                data={
                    "status": "ok",
                    "mode": "complete",
                    "notes": "dry-run: nenhuma chamada externa emitida",
                    "data": {"accepted": True, "action_id": "dry_run", "dry_run": True},
                },
            )
        return await self.inner.call(name, arguments, call_id=call_id, user_id=user_id, seed=seed)
