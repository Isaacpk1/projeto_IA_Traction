"""Composição dos prompts por papel.

O `base.md` é compartilhado pelos dois braços — é o que mantém H1 comparando
arquitetura e não redação. Mas a ferramenta de encerramento **não** é a mesma
para todo papel, e instruir um especialista a chamar `submit_resolution`
contradiria o relatório tipado que ele deve produzir.

O equilíbrio é: a exigência de encerrar por chamada de ferramenta é genérica e
vale para todos; o nome da ferramenta é específico do papel.
"""

from __future__ import annotations

import pytest

from src.agents.architectures.mono import _base_prompt
from src.agents.architectures.multi import _prompt, _routing_prompt
from src.agents.roles import CONTEXTUALIZER, EXECUTOR, INVESTIGATOR, ORCHESTRATOR

ESPECIALISTAS = (CONTEXTUALIZER, INVESTIGATOR, EXECUTOR)


@pytest.mark.parametrize("papel", ESPECIALISTAS, ids=lambda p: p.name)
def test_especialista_nunca_e_instruido_a_chamar_submit_resolution(papel):
    """Ele encerra com seu relatório tipado; citar submit_resolution o confundiria."""
    assert "submit_resolution" not in _prompt(papel)


def test_roteador_tambem_nao_ve_submit_resolution():
    assert "submit_resolution" not in _routing_prompt()


def test_orquestrador_ve_submit_resolution():
    """É ele quem consolida e encerra o atendimento no braço multi."""
    assert "submit_resolution" in _prompt(ORCHESTRATOR)


@pytest.mark.parametrize("papel", [*ESPECIALISTAS, ORCHESTRATOR], ids=lambda p: p.name)
def test_todo_papel_recebe_a_exigencia_de_encerrar_por_chamada_de_ferramenta(papel):
    """A parte genérica do protocolo vale para todos, inclusive quem é podado."""
    prompt = _prompt(papel)
    assert "não** entrega nada" in prompt
    assert "chamada de\nferramenta" in prompt


def test_mono_recebe_o_protocolo_completo_com_o_nome_da_ferramenta():
    """A correção que derrubou a falha 'resposta final sem submit_resolution'.

    O mono tem 18 tools da API e nenhum papel que o restrinja; a exigência de
    encerrar precisa aparecer antes da lista de regras, não como sétimo item.
    """
    prompt = _base_prompt()

    assert "não** entrega nada" in prompt
    assert prompt.index("Como este turno termina") < prompt.index("Regras obrigatórias")
    assert "submit_resolution" in prompt
    # Evidência insuficiente não é desculpa para não encerrar — é motivo de escalar.
    assert "Não há caso sem saída" in prompt
