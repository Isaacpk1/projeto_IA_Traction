"""A matriz é a declaração formal do desenho experimental — doc 07 §3.1 e §E2.

Se estes números mudarem sem que o documento mude, o experimento deixou de ser
o que foi pré-registrado. É por isso que eles são asserção, e não comentário.
"""

from __future__ import annotations

import pytest

from src.core.errors import ContractError
from src.evaluation.golden.loader import load_golden_dataset
from src.evaluation.matrix import (
    E1_REPETITIONS,
    E1_SEEDS,
    E2_POLICIES,
    E2_REPETITIONS,
    plan_core,
    plan_e1,
    plan_e2,
)


@pytest.fixture(scope="module")
def dataset():
    return load_golden_dataset()


def test_e1_reproduz_as_544_execucoes_declaradas(dataset):
    casos = dataset.base_cases()
    tasks = plan_e1(casos, run_id="r")

    assert len(casos) == 17
    assert len(tasks) == len(casos) * 2 * len(E1_SEEDS) * E1_REPETITIONS == 544
    assert {t.arm for t in tasks} == {"A", "B"}
    assert {t.architecture for t in tasks} == {"mono", "multi"}
    # O braço é derivado da arquitetura, nunca escolhido à mão.
    assert {(t.architecture, t.arm) for t in tasks} == {("mono", "A"), ("multi", "B")}
    # Cada seed aparece o mesmo número de vezes — a variável de degradação é balanceada.
    por_seed = {seed: sum(1 for t in tasks if t.seed == seed) for seed in E1_SEEDS}
    assert set(por_seed.values()) == {544 // len(E1_SEEDS)}


def test_e2_reproduz_as_50_execucoes_declaradas(dataset):
    casos = dataset.adversarial_cases()
    tasks = plan_e2(casos, run_id="r")

    assert len(casos) == 5
    assert len(tasks) == len(casos) * len(E2_POLICIES) * E2_REPETITIONS == 50
    assert {t.arm for t in tasks} == set(E2_POLICIES)
    # Controle experimental: só a política muda entre os braços.
    assert {t.architecture for t in tasks} == {"mono"}
    assert {t.seed for t in tasks} == {"complete"}


def test_nucleo_soma_594_com_task_ids_unicos(dataset):
    tasks = plan_core(dataset.base_cases(), dataset.adversarial_cases(), run_id="r")

    assert len(tasks) == 594
    assert len({t.task_id for t in tasks}) == 594


def test_task_id_e_deterministico_entre_planejamentos(dataset):
    """Replanejar depois de uma queda tem que colidir, não duplicar."""
    primeiro = plan_core(dataset.base_cases(), dataset.adversarial_cases(), run_id="r")
    segundo = plan_core(dataset.base_cases(), dataset.adversarial_cases(), run_id="r")

    assert [t.task_id for t in primeiro] == [t.task_id for t in segundo]


def test_run_id_diferente_produz_rodada_diferente(dataset):
    uma = {t.task_id for t in plan_e2(dataset.adversarial_cases(), run_id="piloto")}
    outra = {t.task_id for t in plan_e2(dataset.adversarial_cases(), run_id="definitiva")}

    assert uma.isdisjoint(outra)


def test_e2_recusa_caso_nao_adversarial(dataset):
    with pytest.raises(ContractError, match="adversariais"):
        plan_e2(dataset.base_cases(), run_id="r")


def test_e1_ordena_os_bracos_em_pares(dataset):
    """Uma rodada interrompida precisa deixar dados pareados, não um braço só."""
    tasks = plan_e1(dataset.base_cases(), run_id="r")

    primeiro, segundo = tasks[0], tasks[1]
    assert (primeiro.case_id, primeiro.seed, primeiro.repetition) == (
        segundo.case_id,
        segundo.seed,
        segundo.repetition,
    )
    assert (primeiro.arm, segundo.arm) == ("A", "B")
