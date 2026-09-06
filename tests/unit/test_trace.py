"""Contratos derivados do trace experimental."""

from src.core.contracts.resolution import EvidenceRef
from src.core.contracts.trace import ExecutionTrace, TraceStep
from src.core.evidence import evidence_matches, resolve_field


def test_intensidade_sem_consulta_e_nao_aplicavel():
    trace = ExecutionTrace(task_id="t", execution_id="e", case_id="c", architecture="mono", arm="A")
    assert trace.observed_degradation_intensity() is None


def test_intensidade_exogena_fica_registrada_e_limitada():
    trace = ExecutionTrace(
        task_id="t",
        execution_id="e",
        case_id="c",
        architecture="mono",
        arm="A",
        degradation_intensity=0.625,
    )
    assert trace.degradation_intensity == 0.625


def test_evidencia_resolve_na_forma_que_o_agente_viu():
    """O trace guarda `ToolResult.data`; o agente recebe esse valor embrulhado.

    Reprovar `data.state` porque o trace guarda `{"state": ...}` mediria a camada
    em que a citação foi escrita, não se a evidência existe. Defeito real: zerou
    M6 e fez o PreDeliveryGuard bloquear 94% das resoluções.
    """
    trace = ExecutionTrace(
        run_id="r", task_id="t", execution_id="e", case_id="c", architecture="mono", arm="A",
        steps=[TraceStep(step=0, agent="agent", tool="getBaseline",
                         result={"data": {"state": "invalidated"}, "mode": "complete"})],
    )

    # forma do trace
    assert evidence_matches(
        EvidenceRef(tool="getBaseline", field="data.state", value="invalidated", step=0), trace)
    # forma que o agente viu — um nível a mais de `data`
    citacao = EvidenceRef(tool="getBaseline", field="data.data.state", value="invalidated", step=0)
    assert evidence_matches(citacao, trace)


def test_indice_de_lista_aceita_colchete_e_ponto():
    """O prompt nunca fixou a sintaxe; recusar colchetes mediria notação."""
    dados = {"data": {"results": [{"body": "texto"}]}}
    assert resolve_field(dados, "data.results[0].body") == "texto"
    assert resolve_field(dados, "data.results.0.body") == "texto"

    trace = ExecutionTrace(
        run_id="r", task_id="t", execution_id="e", case_id="c", architecture="mono", arm="A",
        steps=[TraceStep(step=0, agent="agent", tool="searchKnowledge", result=dados)],
    )
    assert evidence_matches(
        EvidenceRef(tool="searchKnowledge", field="data.results[0].body", value="texto", step=0),
        trace)


def test_passo_e_tool_continuam_exigidos():
    """Afrouxar isso mudaria a métrica em vez de corrigi-la."""
    trace = ExecutionTrace(
        run_id="r", task_id="t", execution_id="e", case_id="c", architecture="mono", arm="A",
        steps=[TraceStep(step=3, agent="agent", tool="getBaseline",
                         result={"data": {"state": "invalidated"}})],
    )
    certo = EvidenceRef(tool="getBaseline", field="data.state", value="invalidated", step=3)
    assert evidence_matches(certo, trace)
    assert not evidence_matches(certo.model_copy(update={"step": 1}), trace)
    assert not evidence_matches(certo.model_copy(update={"tool": "getAsset"}), trace)
