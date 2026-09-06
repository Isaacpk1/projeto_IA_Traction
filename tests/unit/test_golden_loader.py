"""Formalização e sincronização do golden dataset."""

import json
from pathlib import Path

import pytest

from src.core.errors import ContractError
from src.evaluation.golden import load_golden_dataset


def test_carrega_17_casos_base_e_5_adversariais_com_fingerprint():
    dataset = load_golden_dataset()

    assert dataset.version == "1.1.0"
    assert len(dataset.fingerprint) == 12
    assert len(dataset.cases) == 22
    assert len(dataset.base_cases()) == 17
    assert len(dataset.adversarial_cases()) == 5
    assert len(dataset.by_id()) == 22
    for case in dataset.cases:
        assert case.root_question
        assert case.expected_path
        assert case.to_input().case_id == case.case_id


def test_adversariais_cobrem_a1_a5_e_nao_expoem_rotulo_ao_agente():
    adversarial = load_golden_dataset().adversarial_cases()

    assert {case.adversarial_id for case in adversarial} == {"A1", "A2", "A3", "A4", "A5"}
    assert all(case.source == "generated" for case in adversarial)
    assert all(case.target_action for case in adversarial)
    for case in adversarial:
        projection = case.to_input().model_dump()
        assert "adversarial_id" not in projection
        assert "target_action" not in projection


def test_converte_rotas_em_tools_e_argumentos_sem_expor_seed():
    cases = load_golden_dataset().by_id()
    pending = cases["case_tkt_inv_05"]
    knowledge = cases["case_tkt_ctx_02"]

    assert pending.expected_path[0].tool == "getRmsSeries"
    assert pending.expected_path[0].args_contains == {"assetId": "asset_C710"}
    assert pending.expected_path[2].args_contains == {
        "assetId": "asset_C710",
        "status": "pending",
    }
    assert knowledge.expected_path[0].args_contains == {"q": "BPFO"}


def test_degradation_probes_excluem_acoes_de_impacto():
    case = load_golden_dataset().by_id()["case_tkt_exe_15"]

    assert "requestRetraining" in {step.tool for step in case.expected_path}
    assert "requestRetraining" not in {step.tool for step in case.degradation_probes}


def test_divergencia_entre_fontes_aborta_em_vez_de_perder_caso(tmp_path):
    source = json.loads(
        Path("inteli-tractian-project/eval/expected-paths.json").read_text(encoding="utf-8")
    )
    source.pop()
    paths = tmp_path / "expected.json"
    paths.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ContractError, match="fontes do golden divergiram"):
        load_golden_dataset(expected_paths_path=paths)
