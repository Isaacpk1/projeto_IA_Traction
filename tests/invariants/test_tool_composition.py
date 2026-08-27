"""RF12 / RNF05 — composição por `tier`.

O invariante mais defensável do projeto e a base da hipótese H2: o Investigador **não
possui** tools de impacto em seu schema. Não é uma instrução que ele possa desobedecer —
é uma capacidade que ele não tem.

Estes testes rodam contra o **catálogo real**, gerado do contrato fornecido. Um teste que
compusesse o catálogo à mão provaria apenas que a lista escrita no teste está certa.
"""

from __future__ import annotations

import pytest

from src.agents.roles import (
    CONTEXTUALIZER,
    EXECUTOR,
    INVESTIGATIVE_ROLES,
    INVESTIGATOR,
    MONO,
    ORCHESTRATOR,
    RoleSpec,
)
from src.core.errors import CompositionViolation
from src.tools.core.tier_registry import TierRegistry

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def compor(registry: TierRegistry, role: RoleSpec):
    """Composição do catálogo de um papel — o mesmo caminho que `interfaces/` usa."""
    return registry.select(
        tiers=set(role.tiers) or None,
        only=set(role.tool_names) if role.tool_names is not None else None,
    )


@pytest.mark.parametrize("role", INVESTIGATIVE_ROLES, ids=lambda r: r.name)
def test_papel_de_investigacao_nao_recebe_tool_de_impacto(registry: TierRegistry, role: RoleSpec):
    tools = compor(registry, role)
    impacto = {t.name for t in tools if t.tier == "impact"}
    assert not impacto, f"{role.name} recebeu tools de impacto: {sorted(impacto)}"


def test_intersecao_com_impact_e_vazia(registry: TierRegistry):
    """A formulação literal do RF12: interseção entre o conjunto do investigador e `impact`."""
    do_investigador = {t.name for t in compor(registry, INVESTIGATOR)}
    de_impacto = registry.names(tier="impact")

    assert de_impacto, "nenhuma tool de impacto no catálogo — o teste passaria por vacuidade"
    assert do_investigador & de_impacto == set()


def test_orquestrador_nao_tem_nenhuma_tool_da_api(registry: TierRegistry):
    """O orquestrador consolida sobre relatórios tipados, nunca sobre consulta própria."""
    assert compor(registry, ORCHESTRATOR) == []


def test_executor_e_o_unico_com_capacidade_de_agir(registry: TierRegistry):
    tools = {t.name for t in compor(registry, EXECUTOR)}
    de_impacto = registry.names(tier="impact")

    assert de_impacto <= tools, f"executor sem acesso a: {sorted(de_impacto - tools)}"
    assert "getCurrentUser" in tools, "executor precisa validar permissão antes de agir (RF13)"


def test_mono_recebe_o_catalogo_inteiro(registry: TierRegistry):
    """Braço A é a condição de controle: contexto único, catálogo completo.

    A diferença de tamanho de catálogo entre os braços (18 vs ~8) é a limitação L11,
    declarada — e é este teste que fixa o número que a limitação descreve.
    """
    tools = compor(registry, MONO)
    assert len(tools) == len(registry) == 18
    assert {t.name for t in tools} & registry.names(tier="impact")


def test_composicao_e_verificada_na_inicializacao(registry: TierRegistry):
    """`assert_no_impact` aborta o processo — não devolve booleano a ser ignorado."""
    registry.assert_no_impact(compor(registry, INVESTIGATOR), role="investigator")
    registry.assert_no_impact(compor(registry, CONTEXTUALIZER), role="contextualizer")

    with pytest.raises(CompositionViolation, match="tier=impact"):
        registry.assert_no_impact(compor(registry, EXECUTOR), role="investigator")


def test_only_nao_contorna_a_restricao_de_tier(registry: TierRegistry):
    """Pedir uma tool pelo nome não pode furar o filtro de tier.

    Se `only` fosse aplicado no lugar de `tiers`, a garantia de RF12 passaria a depender
    de quem escreveu a lista do papel — exatamente o tipo de garantia por disciplina que
    o princípio P2 rejeita.
    """
    escapista = registry.select(tiers={"read"}, only={"escalateCase", "getBaseline"})
    assert {t.name for t in escapista} == {"getBaseline"}


def test_toda_tool_de_impacto_declara_permissao(registry: TierRegistry):
    """RF13 não é verificável se o overlay não disser qual permissão a ação exige."""
    for tool in registry.select(tiers={"impact"}):
        assert tool.required_permission, f"{tool.name} sem required_permission no overlay"
        assert tool.required_permission in {"action_low", "action_high", "escalate"}
