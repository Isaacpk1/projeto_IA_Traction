"""Intensidade de degradação — a variável explicativa do teste primário de H1.

Se esta escala mudar sem que a versão mude, tabelas gravadas em momentos
diferentes deixam de ser comparáveis sem que ninguém perceba.
"""

from __future__ import annotations

import json

import pytest

from src.evaluation.degradation import (
    PESO_POR_MODO,
    VERSAO_ESCALA,
    carregar_intensidade,
    intensidade,
    salvar_intensidade,
)
from src.evaluation.matrix import E1_SEEDS


def test_evidencia_completa_e_zero_e_ausencia_total_e_um():
    assert intensidade(["complete"] * 4) == 0.0
    assert intensidade(["unavailable"] * 4) == 1.0


def test_a_escala_e_monotonica_do_completo_ao_indisponivel():
    """A ordenação é a afirmação central da escala; inverter uma daria dose falsa."""
    assert (
        PESO_POR_MODO["complete"]
        < PESO_POR_MODO["partial"]
        < PESO_POR_MODO["inconclusive"]
        <= PESO_POR_MODO["unavailable"]
    )
    assert PESO_POR_MODO["conflict"] == PESO_POR_MODO["inconclusive"]


def test_usa_media_e_nao_maximo():
    """Um recurso indisponível entre quatro não é o mesmo que quatro indisponíveis.

    O máximo apagaria essa diferença — que é exatamente a variação que a
    dose-resposta precisa enxergar.
    """
    um_de_quatro = intensidade(["unavailable", "complete", "complete", "complete"])

    assert um_de_quatro == pytest.approx(0.25)
    assert um_de_quatro < intensidade(["unavailable"] * 4)


def test_modo_desconhecido_conta_como_completo():
    """Inflar a dose por um rótulo que não sabemos ler produziria dose falsa."""
    assert intensidade(["modo_novo_da_api", "complete"]) == 0.0


def test_sem_recurso_sondado_e_erro_e_nao_zero():
    """Zero significaria 'evidência íntegra'; ausência de sonda não é isso."""
    with pytest.raises(ValueError, match="ao menos um recurso"):
        intensidade([])


def test_ida_e_volta_preserva_a_tabela(tmp_path):
    tabela = {("case_a", "complete"): 0.0, ("case_a", "s13"): 0.625}
    destino = tmp_path / "intensity.json"

    detalhe = {("case_a", "s13"): ["partial", "conflict"]}

    assert salvar_intensidade(destino, tabela, detalhe=detalhe) == 2
    assert carregar_intensidade(destino) == tabela

    documento = json.loads(destino.read_text(encoding="utf-8"))
    assert documento["scale_version"] == VERSAO_ESCALA
    # Sem os modos observados o número é inauditável.
    assert documento["entries"][1]["modes"] == ["partial", "conflict"]


def test_tabela_versionada_cobre_todos_os_seeds_declarados():
    """O arquivo versionado tem que acompanhar a matriz — senão H1 fica sem dose."""
    tabela = carregar_intensidade("src/evaluation/golden/degradation_intensity.json")
    seeds_na_tabela = {seed for _, seed in tabela}

    assert set(E1_SEEDS) <= seeds_na_tabela, "recompute com `agentes intensity`"


def test_os_seeds_escolhidos_cobrem_o_espectro():
    """Pré-requisito de validação do doc 07 §3.1, agora verificável.

    A primeira versão usava s1..s7, cuja faixa de médias era 0,08 — a
    dose-resposta viraria contraste binário. Este teste impede a regressão.
    """
    import statistics as st

    tabela = carregar_intensidade("src/evaluation/golden/degradation_intensity.json")
    medias = []
    for seed in E1_SEEDS:
        valores = [v for (_, s), v in tabela.items() if s == seed]
        medias.append(st.mean(valores))

    assert max(medias) - min(medias) > 0.30, f"seeds não cobrem o espectro: {medias}"
    assert medias == sorted(medias), "E1_SEEDS deve ir do menos ao mais degradado"
