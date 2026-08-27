"""Leitura do overlay declarativo — ADR-02.

Fica **fora** de `tools/core/` de propósito: o núcleo não pode conhecer a existência de
overlay de domínio nenhum. Aqui só se lê e se valida o arquivo; o merge com as operações
do contrato acontece na fábrica.

O overlay precisa ser mantido em sincronia com o contrato — é a consequência ❌ registrada
no ADR-02. `check_coverage` torna a dessincronização detectável na inicialização, em vez
de virar uma tool com descrição pobre que só se percebe na leitura de um trace.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from src.core.contracts.tool import ToolOverlay

__all__ = ["Overlay", "load_overlay", "OverlayMode", "DEFAULT_OVERLAY_PATH"]

OverlayMode = Literal["enriched", "raw"]

DEFAULT_OVERLAY_PATH = Path(__file__).parent / "overlays" / "tractian.overlay.yaml"


class Overlay(BaseModel):
    """Overlay validado. `version` entra no trace como `overlay_version` (RNF15)."""

    version: int = 1
    mode: OverlayMode = "enriched"
    api: str = ""
    contract_version: str = ""
    defaults: ToolOverlay = Field(default_factory=ToolOverlay)
    tools: dict[str, ToolOverlay] = Field(default_factory=dict)

    def for_tool(self, name: str, *, mode: OverlayMode = "enriched") -> ToolOverlay:
        """Metadados de uma operação, com fallback nos defaults.

        No modo `raw`, a **descrição semântica é suprimida** e a tool fica com o texto
        cru do contrato — mas `tier`, `required_permission` e `requires_confirmation`
        permanecem. Isso é deliberado: H3 manipula o enriquecimento semântico, não a
        política de segurança. Suprimir o `tier` junto tornaria o braço `raw` inseguro e
        mudaria duas variáveis ao mesmo tempo.
        """
        base = self.tools.get(name)
        if base is None:
            return self.defaults.model_copy()
        if mode == "raw":
            return base.model_copy(update={"description": None})
        return base

    def check_coverage(self, operation_ids: list[str]) -> tuple[set[str], set[str]]:
        """Devolve `(sem_overlay, orfaos)` — operações sem entrada e entradas sem operação."""
        declaradas = set(self.tools)
        existentes = set(operation_ids)
        return existentes - declaradas, declaradas - existentes


def load_overlay(path: str | Path | None = None) -> Overlay:
    dados = yaml.safe_load(Path(path or DEFAULT_OVERLAY_PATH).read_text(encoding="utf-8"))
    return Overlay.model_validate(dados or {})
