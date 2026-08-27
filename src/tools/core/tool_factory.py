"""Operação do contrato + metadados ⇒ `ToolDef`. **Factory**, doc 13 §5.2.

Genérico: recebe os metadados já resolvidos, sem saber de onde vieram nem o que
significam. Quem sabe que existe um overlay de domínio é `tools/provider.py`.
"""

from __future__ import annotations

import hashlib
import json

from src.core.contracts.tool import ToolDef, ToolOverlay
from src.tools.core.openapi_parser import ParsedOperation

__all__ = ["build_tool", "build_tools", "schema_fingerprint"]


def _describe(op: ParsedOperation, overlay: ToolOverlay) -> str:
    """Descrição efetiva da tool.

    A do overlay tem precedência porque é ela que carrega a semântica que orienta a
    seleção de função. Sem overlay, cai para o texto do contrato — que é justamente o
    braço `raw` do eixo H3.
    """
    if overlay.description:
        return overlay.description.strip()
    partes = [p for p in (op.summary, op.description) if p]
    return "\n\n".join(partes).strip() or f"{op.method.upper()} {op.path}"


def build_tool(op: ParsedOperation, overlay: ToolOverlay | None = None) -> ToolDef:
    ov = overlay or ToolOverlay()
    return ToolDef(
        name=op.operation_id,
        description=_describe(op, ov),
        parameters=op.parameters,
        tier=ov.tier,
        requires_confirmation=ov.requires_confirmation,
        required_permission=ov.required_permission,
        preconditions_for=tuple(ov.preconditions_for),
        method=op.method,
        path=op.path,
        path_params=tuple(op.path_params),
        query_params=tuple(op.query_params),
        body_params=tuple(op.body_params),
        accepts_seed=op.accepts_seed,
    )


def build_tools(
    ops: list[ParsedOperation], overlays: dict[str, ToolOverlay] | None = None
) -> list[ToolDef]:
    overlays = overlays or {}
    return [build_tool(op, overlays.get(op.operation_id)) for op in ops]


def schema_fingerprint(tools: list[ToolDef]) -> str:
    """Hash estável do catálogo — vira `tool_schema_version` no trace (RNF15).

    Cobre nome, schema de parâmetros e política, mas **não** a descrição: no eixo H3 o
    braço `raw` e o `enriched` compartilham o mesmo schema e a mesma política, e devem
    ser identificáveis como tal. O que distingue os braços é `overlay_version`, gravado
    à parte.
    """
    payload = [
        {
            "name": t.name,
            "parameters": t.parameters,
            "tier": t.tier,
            "required_permission": t.required_permission,
            "requires_confirmation": t.requires_confirmation,
            "method": t.method,
            "path": t.path,
        }
        for t in sorted(tools, key=lambda t: t.name)
    ]
    bruto = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(bruto).hexdigest()[:12]
