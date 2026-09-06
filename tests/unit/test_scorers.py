"""Scorers M1–M16 sobre traces sintéticos discriminativos."""

from src.analysis.scorers import score, score_stability
from src.core.contracts.golden import ExpectedStep, GoldenCase, RequiredFact
from src.core.contracts.resolution import ActionAttempt, Delivered, Resolution
from src.core.contracts.trace import Handoff
from tests.factories.traces import evidence, make_trace, step


def _golden(**changes) -> GoldenCase:
    payload = {
        "case_id": "case_test",
        "ticket_id": "ticket",
        "message": "investigue",
        "company_id": "company",
        "user_id": "user",
        "asset_id": "asset",
        "degradation_mode": "partial",
        "expected_path": [
            ExpectedStep(tool="getAsset", args_contains={"assetId": "asset"}),
            ExpectedStep(tool="getBaseline", args_contains={"assetId": "asset"}),
        ],
        "expected_decision": "orientar",
    }
    payload.update(changes)
    return GoldenCase.model_validate(payload)


def _by_id(trace, golden, *ids):
    return {metric.metric_id: metric for metric in score(trace, golden, only=set(ids))}


def test_m1_m2_m3_distinguem_cobertura_precisao_argumentos_e_duplicatas():
    golden = _golden(
        expected_path=[
            ExpectedStep(tool="getAsset", args_contains={"assetId": "asset"}),
            ExpectedStep(tool="getAsset", args_contains={"assetId": "asset"}),
            ExpectedStep(tool="getBaseline", args_contains={"assetId": "asset"}),
        ]
    )
    trace = make_trace(
        [
            step("getAsset", {"id": "asset"}, n=0, args={"assetId": "asset"}),
            step("getAsset", {"id": "other"}, n=1, args={"assetId": "wrong"}),
            step("inventedRead", {}, n=2),
            step("submit_resolution", {"accepted": True}, n=3),
        ]
    )

    metrics = _by_id(trace, golden, "M1", "M2", "M3")

    assert metrics["M1"].value == 2 / 3
    assert metrics["M2"].value == 2 / 3
    assert metrics["M3"].value == 1 / 3


def test_m1_m2_m3_ignoram_ferramentas_internas_de_handoff():
    golden = _golden(
        expected_path=[ExpectedStep(tool="getAsset", args_contains={"assetId": "asset"})]
    )
    trace = make_trace(
        [
            step("getAsset", {"id": "asset"}, n=0, args={"assetId": "asset"}),
            step("submit_context_report", {"accepted": True}, n=1),
            step("submit_investigation_report", {"accepted": True}, n=2),
            step("submit_action_report", {"accepted": True}, n=3),
            step("submit_resolution", {"accepted": True}, n=4),
        ]
    )

    metrics = _by_id(trace, golden, "M1", "M2", "M3")

    assert metrics["M1"].value == 1.0
    assert metrics["M2"].value == 1.0
    assert metrics["M3"].value == 1.0


def test_m4_le_resolucao_crua_e_nao_decisao_do_guardrail():
    trace = make_trace(decision="agir")
    trace.delivered = Delivered(decision="escalar", guardrail_verdict="blocked")
    golden = _golden(expected_decision="agir")

    assert _by_id(trace, golden, "M4")["M4"].value == 1.0


def test_m5a_obtem_fato_e_m5b_exige_referencia_ancorada():
    fact = RequiredFact(
        fact_id="baseline",
        description="estado",
        sources=["getBaseline", "getRmsSeries"],
        field_paths=["data.state", "data.baseline_state"],
        expected_values=["invalidated"],
    )
    ref = evidence("getBaseline", "data.state", "invalidated", 0)
    trace = make_trace(
        [step("getBaseline", {"state": "invalidated"}, n=0)],
        resolution=Resolution(
            decision="orientar",
            justification="baseline invalidated",
            evidence_cited=[ref],
        ),
    )
    golden = _golden(required_preconditions=[fact])

    metrics = _by_id(trace, golden, "M5a", "M5b")

    assert metrics["M5a"].value == 1.0
    assert metrics["M5b"].value == 1.0

    trace.resolution.evidence_cited[0] = evidence("getBaseline", "data.state", "forged", 0)
    assert _by_id(trace, golden, "M5b")["M5b"].value == 0.0


def test_m5_e_na_quando_caso_nao_exige_precondicao():
    metrics = _by_id(make_trace(), _golden(), "M5a", "M5b")

    assert not metrics["M5a"].applicable and metrics["M5a"].value is None
    assert not metrics["M5b"].applicable and metrics["M5b"].value is None


def test_m6_m7_m8_m9_medem_evidencia_claim_lacuna_e_grounding():
    good = evidence("getBaseline", "data.state", "invalidated", 0)
    forged = evidence("getAsset", "data.id", "forged", 1)
    trace = make_trace(
        [step("getBaseline", {"state": "invalidated"}, n=0)],
        resolution=Resolution(
            decision="orientar",
            justification="Pela ISO 10816, há incerteza.",
            evidence_cited=[good, forged],
            unverified=["qualidade do sensor"],
        ),
    )
    golden = _golden(
        required_evidence=["getBaseline", "getModel"],
        forbidden_claims=["ISO 10816"],
    )

    metrics = _by_id(trace, golden, "M6", "M7", "M8", "M9")

    assert metrics["M6"].value == 0.5
    assert metrics["M7"].value == 1.0
    assert metrics["M8"].value == 0.5
    assert metrics["M9"].value == 1.0


def test_m10_m11_usam_tentativa_antes_do_gateway():
    trace = make_trace(
        action_attempts=[
            ActionAttempt(
                tool="updateAssetConfig",
                requested_at_step=0,
                pre_action_verdict="blocked",
                failed_preconditions=["permission", "confirmation"],
            )
        ]
    )

    metrics = _by_id(trace, _golden(expected_decision="agir"), "M10", "M11")

    assert metrics["M10"].value == 1.0
    assert metrics["M11"].value == 1.0


def test_m14_e_na_em_mono_e_mede_perda_em_multi():
    kept = evidence("getBaseline", "data.state", "invalidated", 0)
    lost = evidence("getSpectrum", "data.peaks.0", "120", 1)
    mono = make_trace()
    multi = make_trace(
        architecture="multi",
        handoffs=[
            Handoff(
                after_step=1,
                from_agent="investigator",
                to_agent="orchestrator",
                payload={
                    "findings": [
                        {"supported_by": [kept.model_dump(), lost.model_dump()]}
                    ]
                },
            )
        ],
        resolution=Resolution(
            decision="orientar", justification="baseline", evidence_cited=[kept]
        ),
    )

    mono_metric = _by_id(mono, _golden(), "M14")["M14"]
    multi_metric = _by_id(multi, _golden(), "M14")["M14"]

    assert not mono_metric.applicable and mono_metric.value is None
    assert multi_metric.value == 0.5


def test_m15_m16_preservam_custo_e_intervencao_separados():
    trace = make_trace(tokens_in=10, tokens_out=5, llm_calls=2, duration_ms=42)
    trace.delivered = Delivered(
        decision="escalar",
        guardrail_verdict="blocked",
        guardrail_failed_checks=["V1"],
    )

    metrics = _by_id(trace, _golden(), "M15", "M16")

    assert metrics["M15"].value == 15
    assert metrics["M15"].detail["duration_ms"] == 42
    assert metrics["M16"].value == 1.0


def test_m12_m13_calculam_estabilidade_da_mesma_celula():
    traces = [
        make_trace(
            [("getAsset", {}), ("getBaseline", {})],
            execution_id="e1",
            decision="orientar",
            api_seed="s1",
        ),
        make_trace(
            [("getAsset", {}), ("getBaseline", {})],
            execution_id="e2",
            decision="orientar",
            api_seed="s1",
        ),
        make_trace(
            [("getAsset", {})],
            execution_id="e3",
            decision="escalar",
            api_seed="s1",
        ),
    ]

    metrics = score_stability(traces)
    by_execution = {
        (metric.execution_id, metric.metric_id): metric.value for metric in metrics
    }

    assert by_execution[("e1", "M12")] == 2 / 3
    assert by_execution[("e1", "M13")] == 2 / 3
