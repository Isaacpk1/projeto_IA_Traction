"""Contratos da camada de ferramentas — doc 05 §4.1.

`ToolDef` é o que o núcleo genérico produz a partir do contrato OpenAPI; `ToolOverlay` é
o que a camada de domínio acrescenta. A separação é o princípio P1 — genérico no núcleo,
específico na borda — e é o que entrega RNF06: outra API exige um novo contrato e um
novo overlay, e o núcleo não muda.

⚠️ Nenhum identificador de domínio (`baseline`, `rms`, `spectrum`, `asset`) aparece
neste módulo nem em `tools/core/`. Verificado por varredura automatizada.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["read", "impact"]

__all__ = ["Tier", "ToolOverlay", "ToolDef", "ToolCall", "ToolResult"]


class ToolOverlay(BaseModel):
    """Enriquecimento declarativo de uma operação — o único lugar com domínio.

    Os metadados alimentam três mecanismos distintos, todos revalidados no gateway:
    `tier` controla a composição por agente (RF12), `requires_confirmation` controla
    RF14 e `required_permission` controla RF13.
    """

    tier: Tier = "read"
    description: str | None = None
    requires_confirmation: bool = False
    required_permission: str | None = None
    preconditions_for: list[str] = Field(
        default_factory=list,
        description="Operações cuja conclusão depende desta ter sido consultada antes",
    )


class ToolDef(BaseModel):
    """Uma tool executável: schema JSON + metadados de política.

    `parameters` segue JSON Schema, que é o formato aceito por function calling em
    todos os provedores considerados.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="operationId do contrato OpenAPI")
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    tier: Tier = "read"
    requires_confirmation: bool = False
    required_permission: str | None = None
    preconditions_for: tuple[str, ...] = ()

    # --- proveniência: o que o núcleo genérico extraiu do contrato ---------------
    method: str = "get"
    path: str = ""
    path_params: tuple[str, ...] = ()
    query_params: tuple[str, ...] = ()
    body_params: tuple[str, ...] = ()
    accepts_seed: bool = False


class ToolCall(BaseModel):
    """Invocação pedida pelo modelo."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Retorno de uma invocação; em erro, `data` pode preservar o corpo do upstream."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    name: str
    data: dict[str, Any] | None = None
    error: str | None = None
    error_class: str | None = None
    status_code: int | None = None
    latency_ms: float = 0.0
    external_call_emitted: bool = Field(
        default=False,
        description="True somente depois que o transporte externo recebeu a tentativa",
    )

    @property
    def mode(self) -> str | None:
        """Modo do envelope de consulta, quando a resposta usa envelope."""
        if not self.data:
            return None
        value = self.data.get("mode")
        return value if isinstance(value, str) else None

    @property
    def ok(self) -> bool:
        return self.error is None
