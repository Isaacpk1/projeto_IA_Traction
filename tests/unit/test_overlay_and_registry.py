"""Overlay declarativo e catálogo por tier — ADR-02."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tools.core.tier_registry import TierRegistry
from src.tools.core.tool_factory import schema_fingerprint
from src.tools.overlay import Overlay, load_overlay
from src.tools.provider import build_registry

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def test_overlay_cobre_todas_as_operacoes_do_contrato(contract_path: Path, overlay: Overlay):
    """A consequência ❌ do ADR-02 é que o overlay precisa acompanhar o contrato.

    Este teste é o que torna a dessincronização visível: sem ele, uma operação nova
    viraria tool com descrição crua e a degradação passaria despercebida.
    """
    from src.tools.core.openapi_parser import parse_contract

    sem_overlay, orfaos = overlay.check_coverage(
        [op.operation_id for op in parse_contract(contract_path)]
    )
    assert not sem_overlay, f"operações sem overlay: {sorted(sem_overlay)}"
    assert not orfaos, f"overlay declara operações inexistentes: {sorted(orfaos)}"


def test_descricao_enriquecida_substitui_a_do_contrato(registry: TierRegistry):
    """É o enriquecimento semântico que o eixo H3 manipula."""
    baseline = registry.get("getBaseline")
    assert baseline is not None
    assert "reference + tolerance" in baseline.description
    assert "ISO" in baseline.description, "o overlay precisa vedar a norma genérica (RF07)"
    assert len(baseline.description) > 400


def test_tiers_conferem_com_o_desenho(registry: TierRegistry):
    esperado_impacto = {
        "reprocessAnalysis",
        "requestSpecialistAnalysis",
        "requestRetraining",
        "updateAssetConfig",
        "escalateCase",
    }
    assert registry.names(tier="impact") == esperado_impacto
    assert len(registry.names(tier="read")) == 13
    assert registry.counts_by_tier() == {"read": 13, "impact": 5}


def test_escalar_nao_exige_confirmacao(registry: TierRegistry):
    """Encaminhar para um humano é reversível e não age sobre o equipamento.

    Exigir confirmação para escalar penalizaria o comportamento correto diante de
    evidência degradada — que é exatamente o que H1 mede.
    """
    escalate = registry.get("escalateCase")
    assert escalate is not None
    assert escalate.tier == "impact"
    assert escalate.requires_confirmation is False
    assert escalate.required_permission == "escalate"


def test_acoes_irreversiveis_exigem_confirmacao(registry: TierRegistry):
    for nome in ("updateAssetConfig", "requestRetraining", "reprocessAnalysis"):
        tool = registry.get(nome)
        assert tool is not None and tool.requires_confirmation, nome


def test_modo_raw_remove_semantica_mas_preserva_politica(contract_path: Path):
    """H3 manipula o enriquecimento semântico, **não** a política de segurança.

    Suprimir o `tier` junto tornaria o braço `raw` inseguro e mudaria duas variáveis ao
    mesmo tempo — o resultado seria ininterpretável, como A vs C em RF33.
    """
    cru, _ = build_registry(contract_path, mode="raw")
    rico, _ = build_registry(contract_path, mode="enriched")

    baseline_cru = cru.get("getBaseline")
    baseline_rico = rico.get("getBaseline")
    assert baseline_cru is not None and baseline_rico is not None

    assert len(baseline_cru.description) < len(baseline_rico.description)
    assert "ISO" not in baseline_cru.description

    for nome in cru.names():
        a, b = cru.get(nome), rico.get(nome)
        assert a is not None and b is not None
        assert a.tier == b.tier, nome
        assert a.required_permission == b.required_permission, nome
        assert a.requires_confirmation == b.requires_confirmation, nome


def test_fingerprint_do_schema_ignora_descricao(contract_path: Path):
    """`tool_schema_version` identifica o schema; `overlay_version` identifica a semântica.

    Os dois braços de H3 compartilham schema e política, e precisam ser identificáveis
    como tal no trace (RNF15).
    """
    cru, _ = build_registry(contract_path, mode="raw")
    rico, _ = build_registry(contract_path, mode="enriched")
    assert schema_fingerprint(cru.all()) == schema_fingerprint(rico.all())


def test_fingerprint_muda_quando_a_politica_muda(registry: TierRegistry):
    original = schema_fingerprint(registry.all())
    adulterado = [
        t.model_copy(update={"tier": "read"}) if t.name == "escalateCase" else t
        for t in registry.all()
    ]
    assert schema_fingerprint(adulterado) != original


def test_precondicoes_declaradas_ligam_tools(registry: TierRegistry):
    """`preconditions_for` é o que o overlay usa para dizer ao modelo o que vem antes."""
    baseline = registry.get("getBaseline")
    assert baseline is not None
    assert "getAnalysis" in baseline.preconditions_for


def test_registry_rejeita_tool_duplicada(registry: TierRegistry):
    with pytest.raises(ValueError, match="duplicada"):
        TierRegistry(registry.all() + [registry.all()[0]])


def test_overlay_ausente_gera_aviso_e_nao_quebra(contract_path: Path, tmp_path: Path):
    vazio = tmp_path / "vazio.yaml"
    vazio.write_text("version: 9\napi: outra\ntools: {}\n", encoding="utf-8")

    with pytest.warns(UserWarning, match="sem overlay"):
        reg, ov = build_registry(contract_path, overlay_path=vazio)

    assert len(reg) == 18, "sem overlay a camada continua funcional, só perde semântica"
    assert ov.version == 9
    baseline = reg.get("getBaseline")
    assert baseline is not None
    assert baseline.tier == "read", "sem entrada no overlay, cai no default seguro"


def test_load_overlay_valida_o_arquivo(tmp_path: Path):
    ruim = tmp_path / "ruim.yaml"
    ruim.write_text("version: 1\ntools:\n  x:\n    tier: superusuario\n", encoding="utf-8")
    with pytest.raises(Exception, match="tier"):
        load_overlay(ruim)
