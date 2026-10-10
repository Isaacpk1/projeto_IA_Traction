"""Política de decisão e suíte de expansão.

O valor da política está na *ordem* das regras: é ela que decide, por exemplo, que uma
análise stale sobre baseline invalidado é reprocesso (agir) e não artefato (orientar).
Estes testes travam essa ordem — sem eles, mexer numa regra reetiqueta a suíte em
silêncio.
"""

from collections import Counter

import pytest

from src.evaluation.golden import load_expansion_dataset
from src.evaluation.golden.policy import Analise, Situacao, decidir

BASE = {
    "user_id": "usr_x",
    "permissoes": frozenset({"read", "action_low"}),
    "company_id": "comp_x",
    "asset_id": "asset_X",
    "machine_type": "pump",
    "criticality": "high",
    "sensor_status": "online",
    "baseline_state": "established",
    "baseline_learnable": True,
    "baseline_detection_mode": "baseline",
    "invalidation_reason": None,
    "dq_completeness": 0.95,
    "dq_snr_db": 16.0,
    "dq_staleness": False,
    "req_min_completeness": 0.8,
    "req_min_snr_db": 12.0,
    "model_id": "mdl_vib_v3",
    "model_processing_state": "current",
    "cobertura_suportada": True,
    "cobertura_aprende_baseline": True,
}


def situacao(**kwargs) -> Situacao:
    return Situacao(**{**BASE, **kwargs})


def analise(**kwargs) -> Analise:
    padrao = {
        "id": "an_0001",
        "status": "current",
        "tipo": "bearing_fault",
        "detection_mode": "baseline",
        "baseline_state_at_detection": "established",
        "confidence": 0.8,
    }
    return Analise(**{**padrao, **kwargs})


def test_stale_sobre_baseline_invalidado_age_antes_de_virar_artefato():
    """A ordem importa: `stale` é correção pendente; `current` inválido é artefato."""
    stale = situacao(
        intencao="validar_insight",
        baseline_state="invalidated",
        analises=(analise(status="stale", baseline_state_at_detection="invalidated"),),
    )
    corrente = situacao(
        intencao="validar_insight",
        baseline_state="invalidated",
        analises=(analise(status="current", baseline_state_at_detection="invalidated"),),
    )

    assert decidir(stale).decisao == "agir"
    assert decidir(stale).acoes == ("reprocessAnalysis",)
    assert decidir(corrente).decisao == "orientar"
    assert "requestRetraining" in decidir(corrente).proibidas


def test_falta_de_permissao_decide_antes_de_qualquer_outra_regra():
    s = situacao(
        intencao="pedir_retreinamento",
        permissoes=frozenset({"read"}),
        analises=(analise(baseline_state_at_detection="invalidated"),),
    )
    veredito = decidir(s)

    assert veredito.regra == "R01"
    assert veredito.decisao == "orientar"
    assert not veredito.acoes


def test_mudanca_de_config_nao_depende_da_qualidade_do_sinal():
    """Qualidade ruim bloqueia confiar num diagnóstico, não uma mudança administrativa."""
    s = situacao(
        intencao="pedir_mudanca_config",
        permissoes=frozenset({"read", "action_high"}),
        dq_completeness=0.62,
        dq_snr_db=8.4,
    )
    veredito = decidir(s)

    assert veredito.decisao == "agir"
    assert veredito.acoes == ("updateAssetConfig",)


def test_escalonamento_exige_dois_sinais_de_indisponibilidade():
    um_sinal = situacao(
        intencao="pedir_visita_campo",
        permissoes=frozenset({"read", "escalate"}),
        baseline_state="learning",
    )
    dois_sinais = situacao(
        intencao="pedir_visita_campo",
        permissoes=frozenset({"read", "escalate"}),
        baseline_state="learning",
        dq_completeness=0.18,
        dq_snr_db=3.1,
    )

    assert decidir(um_sinal).decisao == "orientar"
    assert "escalateCase" in decidir(um_sinal).proibidas
    assert decidir(dois_sinais).decisao == "escalar"
    assert decidir(dois_sinais).acoes == ("escalateCase",)


def test_sensor_offline_com_dado_velho_escala_mesmo_com_baseline_estabelecido():
    s = situacao(
        intencao="relatar_sintoma",
        permissoes=frozenset({"read", "escalate"}),
        sensor_status="offline",
        dq_staleness=True,
    )

    assert decidir(s).decisao == "escalar"


def test_pergunta_de_contexto_nao_e_sequestrada_por_regra_de_diagnostico():
    s = situacao(
        intencao="perguntar_termo",
        baseline_state="invalidated",
        analises=(analise(status="stale", baseline_state_at_detection="invalidated"),),
    )
    veredito = decidir(s)

    assert veredito.regra == "R17"
    assert veredito.decisao == "orientar"


def test_ativo_sadio_nao_vira_diagnostico_inventado():
    s = situacao(intencao="relatar_sintoma", analises=(analise(tipo="none", confidence=0.96),))
    veredito = decidir(s)

    assert veredito.regra == "R16"
    assert veredito.decisao == "orientar"
    assert not veredito.acoes


def test_suite_de_expansao_carrega_com_as_invariantes_do_golden():
    dataset = load_expansion_dataset()

    assert len(dataset.cases) == 58
    assert all(case.source == "generated" for case in dataset.cases)
    assert all(case.case_type == "normal" for case in dataset.cases)
    for case in dataset.cases:
        assert case.decision_rationale.startswith("[R")
        assert case.success_criteria
        assert case.required_evidence_groups
        projecao = case.to_input().model_dump()
        assert "expected_decision" not in projecao


@pytest.mark.parametrize("decisao,minimo", [("agir", 8), ("escalar", 8)])
def test_expansao_nao_colapsa_na_classe_majoritaria(decisao: str, minimo: int):
    """Uma suíte só de `orientar` mediria a classe majoritária, não a competência."""
    contagem = Counter(case.expected_decision for case in load_expansion_dataset().cases)

    assert contagem[decisao] >= minimo
