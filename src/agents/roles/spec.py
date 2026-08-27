"""Especificação declarativa dos papéis — doc 05 §4.2, RF12.

Declarativo de propósito. A composição de tools de um papel é **dado**, não código: é o
que permite que a garantia de RF12 seja verificada na inicialização e por teste, sem
executar o agente.

Repare que este módulo não importa `tools/` — ele declara **nomes** e **tiers**, e a
resolução para `ToolDef` acontece em `interfaces/`, através da porta `ToolProvider`. É a
regra de dependência se pagando: `agents/` conhece a porta, nunca o adaptador.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.contracts.tool import Tier

__all__ = [
    "RoleSpec",
    "ORCHESTRATOR",
    "CONTEXTUALIZER",
    "INVESTIGATOR",
    "EXECUTOR",
    "ROLES",
    "MONO",
]

#: Tool terminal pela qual toda execução submete sua resolução (RF11). Não pertence ao
#: contrato da API — é da aplicação —, e por isso não tem `tier` de impacto: submeter uma
#: resolução não produz efeito externo.
SUBMIT_RESOLUTION = "submit_resolution"


@dataclass(frozen=True)
class RoleSpec:
    """Um papel: que tools recebe e o que produz."""

    name: str
    tiers: frozenset[Tier]
    tool_names: frozenset[str] | None = None
    """`None` = todas as tools dos tiers permitidos. Conjunto = restrição adicional."""

    extra_tools: frozenset[str] = field(default_factory=frozenset)
    """Tools da aplicação, fora do contrato da API (ex.: `submit_resolution`)."""

    produces: str = ""
    prompt: str = ""

    def allows_impact(self) -> bool:
        return "impact" in self.tiers


# --- Arquitetura mono (braço A) ----------------------------------------------

MONO = RoleSpec(
    name="agent",
    tiers=frozenset({"read", "impact"}),
    extra_tools=frozenset({SUBMIT_RESOLUTION}),
    produces="Resolution",
    prompt="mono",
)
"""Agente único: contexto completo, catálogo inteiro.

Condição de **controle** de H1. Sem handoff e sem perda de informação na fronteira — e,
por isso mesmo, sem isolamento e sem separação de autoridade. Como ele possui tools de
impacto, a proteção depende inteiramente do `PreActionGuard` (ADR-04, consequência ❌).
"""


# --- Arquitetura multi (braços B e C) ----------------------------------------

ORCHESTRATOR = RoleSpec(
    name="orchestrator",
    tiers=frozenset(),
    tool_names=frozenset(),
    extra_tools=frozenset({SUBMIT_RESOLUTION}),
    produces="Resolution",
    prompt="orchestrator",
)
"""Roteia, consolida e submete. **Sem nenhuma tool da API.**

Não é economia de catálogo: é o que garante que a consolidação seja feita sobre os
relatórios tipados recebidos, e não sobre uma consulta própria que contornaria o handoff
— o que anularia justamente o mecanismo que H1 investiga.
"""

CONTEXTUALIZER = RoleSpec(
    name="contextualizer",
    tiers=frozenset({"read"}),
    tool_names=frozenset(
        {"searchKnowledge", "getKnowledgeDoc", "getAsset", "getCompany", "getCurrentUser"}
    ),
    produces="ContextReport",
    prompt="contextualizer",
)

INVESTIGATOR = RoleSpec(
    name="investigator",
    tiers=frozenset({"read"}),
    tool_names=frozenset(
        {
            "getAsset",
            "listAnalyses",
            "getAnalysis",
            "getBaseline",
            "getRmsSeries",
            "getSpectrum",
            "getDataQuality",
            "getModel",
        }
    ),
    produces="InvestigationReport",
    prompt="investigator",
)
"""Investiga. **Não possui tools de impacto — não é instrução, é capacidade ausente.**

Validado na inicialização: interseção não-vazia com `tier: impact` aborta o processo
(RNF05). É a garantia estrutural do princípio P2.
"""

EXECUTOR = RoleSpec(
    name="executor",
    tiers=frozenset({"read", "impact"}),
    tool_names=frozenset(
        {
            "reprocessAnalysis",
            "requestSpecialistAnalysis",
            "requestRetraining",
            "updateAssetConfig",
            "escalateCase",
            # leitura necessária para validar permissão antes de agir (RF13)
            "getCurrentUser",
        }
    ),
    produces="ActionReport",
    prompt="executor",
)

ROLES: dict[str, RoleSpec] = {
    r.name: r for r in (MONO, ORCHESTRATOR, CONTEXTUALIZER, INVESTIGATOR, EXECUTOR)
}

#: Papéis de investigação: os que, por desenho, jamais podem agir.
INVESTIGATIVE_ROLES = (ORCHESTRATOR, CONTEXTUALIZER, INVESTIGATOR)
