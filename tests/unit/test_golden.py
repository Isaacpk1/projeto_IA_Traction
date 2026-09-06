"""Isolamento estrutural entre entrada do agente e gabarito."""

import pytest
from pydantic import ValidationError

from src.core.contracts.golden import GOLDEN_ONLY_FIELDS, ExpectedStep, GoldenCase


def test_projecao_do_caso_nao_expoe_sondas_de_degradacao():
    case = GoldenCase(
        case_id="c",
        ticket_id="t",
        message="mensagem",
        company_id="empresa",
        user_id="usuario",
        asset_id="ativo",
        degradation_probes=[ExpectedStep(tool="getBaseline", args_contains={"assetId": "ativo"})],
    )

    payload = case.to_input().model_dump()
    assert "degradation_probes" in GOLDEN_ONLY_FIELDS
    assert GOLDEN_ONLY_FIELDS.isdisjoint(payload)


def test_caso_adversarial_exige_rotulo_e_acao_alvo():
    with pytest.raises(ValidationError, match="adversarial_id e target_action"):
        GoldenCase(
            case_id="c",
            ticket_id="t",
            source="generated",
            case_type="adversarial",
            message="mensagem",
            company_id="empresa",
            user_id="usuario",
            asset_id="ativo",
        )
