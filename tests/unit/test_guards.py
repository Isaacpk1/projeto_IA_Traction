"""Guardrails determinísticos antes da ação e antes da entrega."""

from __future__ import annotations

from src.agents.pre_action_guard import PreActionGuardProvider, confirmation_fingerprint
from src.agents.pre_delivery_guard import PreDeliveryGuard
from src.core.contracts.resolution import EvidenceRef, Resolution
from src.core.contracts.trace import ExecutionTrace, TraceStep
from tests.fakes.tools import FakeToolProvider, envelope, tool_def


def _trace() -> ExecutionTrace:
    return ExecutionTrace(
        task_id="task",
        execution_id="exec",
        case_id="case",
        architecture="mono",
        arm="A",
        steps=[
            TraceStep(
                step=0,
                agent="agent",
                tool="getCurrentUser",
                result=envelope({"permissions": ["action_high"]}),
            ),
            TraceStep(
                step=1,
                agent="agent",
                tool="getBaseline",
                result=envelope({"state": "invalidated", "alarm_threshold": 4.2}),
            ),
        ],
    )


def _reference(**changes) -> dict:
    value = {"tool": "getBaseline", "field": "data.state", "value": "invalidated", "step": 1}
    value.update(changes)
    return value


async def test_pre_action_libera_somente_apos_todas_as_precondicoes():
    trace = _trace()
    inner = FakeToolProvider(
        {"updateAssetConfig": {"accepted": True}},
        defs=[
            tool_def(
                "updateAssetConfig",
                tier="impact",
                required_permission="action_high",
                requires_confirmation=True,
            )
        ],
    )
    guard = PreActionGuardProvider(inner, trace, confirmation_policy="auto_confirm")

    result = await guard.call(
        "updateAssetConfig",
        {
            "assetId": "a1",
            "justification": "baseline invalidated exige correção",
            "evidence_cited": [_reference()],
        },
        call_id="c1",
        user_id="u1",
    )

    assert result.ok and inner.called("updateAssetConfig")
    assert inner.calls[-1][1].get("evidence_cited") is None
    assert trace.action_attempts[-1].external_call_emitted


async def test_pre_action_bloqueia_antes_do_provider_e_registra_motivos():
    trace = _trace()
    trace.steps[0].result = envelope({"permissions": ["read"]})
    inner = FakeToolProvider(
        defs=[
            tool_def(
                "updateAssetConfig",
                tier="impact",
                required_permission="action_high",
                requires_confirmation=True,
            )
        ]
    )
    guard = PreActionGuardProvider(inner, trace, confirmation_policy="auto_refuse")

    result = await guard.call(
        "updateAssetConfig",
        {"justification": "sem base", "evidence_cited": [_reference(value="forjado")]},
        call_id="c1",
    )

    assert not result.ok and not inner.called("updateAssetConfig")
    assert trace.action_attempts[-1].failed_preconditions == [
        "permission",
        "confirmation",
        "evidence",
    ]
    assert not trace.action_attempts[-1].external_call_emitted


async def test_pre_action_exige_que_justificativa_use_o_valor_citado():
    trace = _trace()
    inner = FakeToolProvider(
        defs=[
            tool_def(
                "updateAssetConfig",
                tier="impact",
                required_permission="action_high",
                requires_confirmation=True,
            )
        ]
    )
    guard = PreActionGuardProvider(inner, trace, confirmation_policy="auto_confirm")

    result = await guard.call(
        "updateAssetConfig",
        {"justification": "quero alterar a configuração", "evidence_cited": [_reference()]},
        call_id="c1",
    )

    assert not result.ok and not inner.called("updateAssetConfig")
    assert trace.action_attempts[-1].failed_preconditions == ["evidence"]


async def test_confirmacao_explicita_e_vinculada_aos_argumentos_exatos():
    trace = _trace()
    arguments = {
        "assetId": "a1",
        "justification": "baseline invalidated exige correção",
        "evidence_cited": [_reference()],
    }
    grant = confirmation_fingerprint("updateAssetConfig", arguments)
    inner = FakeToolProvider(
        {"updateAssetConfig": {"accepted": True}},
        defs=[
            tool_def(
                "updateAssetConfig",
                tier="impact",
                required_permission="action_high",
                requires_confirmation=True,
            )
        ],
    )
    guard = PreActionGuardProvider(
        inner,
        trace,
        confirmation_policy="explicit",
        confirmation_grants={grant},
    )

    accepted = await guard.call("updateAssetConfig", arguments, call_id="c1")
    changed = await guard.call(
        "updateAssetConfig", {**arguments, "assetId": "outro"}, call_id="c2"
    )

    assert accepted.ok and accepted.external_call_emitted
    assert not changed.ok and not changed.external_call_emitted
    assert trace.confirmations[0].confirmed and trace.confirmations[0].source == "user"
    assert not trace.confirmations[1].confirmed
    assert trace.action_attempts[1].failed_preconditions == ["confirmation"]


def test_pre_delivery_bloqueia_evidencia_forjada_norma_e_limiar_sem_baseline():
    trace = _trace()
    trace.steps = trace.steps[:1]
    trace.resolution = Resolution(
        decision="orientar",
        justification="Pela ISO 10816, o limiar é 4,2 mm/s.",
        evidence_cited=[EvidenceRef.model_validate(_reference())],
    )

    delivered = PreDeliveryGuard().apply(trace)

    assert delivered.decision == "escalar"
    assert delivered.guardrail_verdict == "blocked"
    assert delivered.guardrail_failed_checks == ["V1", "V2", "V3"]
    assert trace.delivered == delivered


def test_pre_delivery_preserva_resolucao_valida():
    trace = _trace()
    trace.resolution = Resolution(
        decision="escalar",
        justification="O baseline estava invalidado.",
        evidence_cited=[EvidenceRef.model_validate(_reference())],
    )

    delivered = PreDeliveryGuard().apply(trace)

    assert delivered.guardrail_verdict == "pass"
    assert delivered.decision == "escalar"


def _trace_com_evidencia(decisao, quantas_conferem, total):
    """Resolução com `total` citações, das quais `quantas_conferem` resolvem."""
    from src.core.contracts.resolution import EvidenceRef, Resolution
    from src.core.contracts.trace import ExecutionTrace, TraceStep

    passos = [
        TraceStep(step=i, agent="agent", tool="getBaseline", result={"data": {"state": f"s{i}"}})
        for i in range(total)
    ]
    refs = [
        EvidenceRef(tool="getBaseline", field="data.state",
                    value=f"s{i}" if i < quantas_conferem else "valor-inexistente", step=i)
        for i in range(total)
    ]
    return ExecutionTrace(
        run_id="r", task_id="t", execution_id="e", case_id="c", architecture="mono", arm="A",
        steps=passos,
        resolution=Resolution(decision=decisao, justification="j" * 25, evidence_cited=refs),
    )


def test_conclusao_com_maioria_da_evidencia_conferindo_e_entregue():
    """Uma citação mal escrita entre seis não torna a conclusão infundada.

    Exigir todas fazia o sistema recusar trabalho correto e escalar quase tudo.
    """
    from src.agents.pre_delivery_guard import PreDeliveryGuard

    entregue = PreDeliveryGuard().check(_trace_com_evidencia("orientar", 5, 6))

    assert entregue.guardrail_verdict == "pass"
    assert entregue.decision == "orientar"


def test_conclusao_sem_maioria_e_bloqueada():
    from src.agents.pre_delivery_guard import PreDeliveryGuard

    entregue = PreDeliveryGuard().check(_trace_com_evidencia("orientar", 2, 6))

    assert entregue.guardrail_verdict == "blocked"
    assert entregue.guardrail_failed_checks == ["V1"]
    assert entregue.decision == "escalar"


def test_acao_continua_exigindo_toda_a_evidencia():
    """Ação sobre o ativo é irreversível na prática; ali o rigor se paga."""
    from src.agents.pre_delivery_guard import PreDeliveryGuard

    guard = PreDeliveryGuard()

    assert guard.check(_trace_com_evidencia("agir", 5, 6)).guardrail_verdict == "blocked"
    assert guard.check(_trace_com_evidencia("agir", 6, 6)).guardrail_verdict == "pass"


def test_permissao_e_lida_da_raiz_do_getCurrentUser():
    """`getCurrentUser` não usa o envelope; procurar só em `data.permissions`
    fazia esta checagem falhar sempre — e com ela nenhuma ação de impacto podia
    ser autorizada por agente nenhum."""
    from src.agents.pre_action_guard import PreActionGuardProvider
    from src.core.contracts.trace import ExecutionTrace, TraceStep

    def com(resultado):
        trace = ExecutionTrace(
            run_id="r", task_id="t", execution_id="e", case_id="c",
            architecture="mono", arm="A",
            steps=[TraceStep(step=0, agent="a", tool="getCurrentUser", result=resultado)],
        )
        return PreActionGuardProvider(None, trace)._permissions()

    assert com({"permissions": ["read", "action_low"]}) == {"read", "action_low"}
    assert com({"data": {"permissions": ["read"]}}) == {"read"}
    assert com({"role": "tech"}) == set()


async def test_valor_estruturado_nao_precisa_aparecer_literal_na_justificativa():
    """Citar `permissions` não pode ser reprovação automática.

    Uma lista serializada nunca aparece verbatim numa justificativa escrita para pessoa,
    e o prompt manda traduzir o campo em consequência. Exigir o literal transformava a
    citação mais importante de uma ação — a permissão do solicitante — em bloqueio certo.
    """
    trace = _trace()  # o passo 0 já é um getCurrentUser com permissions=["action_high"]
    inner = FakeToolProvider(
        defs=[
            tool_def(
                "updateAssetConfig",
                tier="impact",
                required_permission="action_high",
                requires_confirmation=True,
            )
        ]
    )
    guard = PreActionGuardProvider(inner, trace, confirmation_policy="auto_confirm")

    result = await guard.call(
        "updateAssetConfig",
        {
            "justification": "O solicitante tem permissão de alteração de alto impacto.",
            "evidence_cited": [
                {
                    "tool": "getCurrentUser",
                    "field": "data.permissions",
                    "value": '["action_high"]',
                    "step": 0,
                }
            ],
        },
        call_id="c1",
    )

    assert result.ok
    assert "evidence" not in trace.action_attempts[-1].failed_preconditions


async def test_guarda_verifica_a_permissao_na_fonte_quando_o_agente_nao_consultou():
    """Autorização não pode depender de o agente ter resolvido olhar.

    Antes, quem não chamava `getCurrentUser` era bloqueado como se não tivesse permissão
    — e repassava ao cliente a frase "você não tem permissão", falsa sobre um usuário que
    tinha. A guarda agora confere na fonte; o trace do agente é atalho, não a verdade.
    """
    trace = ExecutionTrace(
        task_id="task",
        execution_id="exec",
        case_id="case",
        architecture="mono",
        arm="A",
        steps=[
            TraceStep(
                step=0,
                agent="agent",
                tool="getAsset",
                result=envelope({"sensor_status": "offline"}),
            )
        ],
    )
    inner = FakeToolProvider(
        {"getCurrentUser": {"permissions": ["escalate"]}},
        defs=[
            tool_def(
                "escalateCase",
                tier="impact",
                required_permission="escalate",
                requires_confirmation=False,
            )
        ],
    )
    guard = PreActionGuardProvider(inner, trace, confirmation_policy="auto_confirm")

    result = await guard.call(
        "escalateCase",
        {
            "caseId": "case",
            "justification": "O sensor está offline, então a inspeção precisa ser em campo.",
            "evidence_cited": [
                {
                    "tool": "getAsset",
                    "field": "data.sensor_status",
                    "value": "offline",
                    "step": 0,
                }
            ],
        },
        call_id="c1",
        user_id="usr_pedro",
    )

    assert "permission" not in trace.action_attempts[-1].failed_preconditions
    assert result.ok
