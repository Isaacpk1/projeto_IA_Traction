"""Isolamento estrutural entre entrada do agente e gabarito."""

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
