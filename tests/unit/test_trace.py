"""Contratos derivados do trace experimental."""

from src.core.contracts.trace import ExecutionTrace


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
