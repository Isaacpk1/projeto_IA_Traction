"""Testes declarados do estágio ④ — doc 11 §6.

Estatística errada é pior que estatística ausente: produz veredito confiante e
falso. Cada teste aqui monta dados em que a resposta certa é conhecida por
construção, e verifica que o módulo chega nela — inclusive quando a resposta
certa é "inconclusiva".
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.analysis.hypotheses import (
    MARGEM_NAO_INFERIORIDADE,
    avaliar_h1_dose_resposta,
    avaliar_h2_tentativa_insegura,
    avaliar_h3_mcnemar,
    avaliar_h4_nao_inferioridade,
    bootstrap_por_caso,
    intervalo_binomial,
)

INTENSIDADES = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]


def _prob(log_odds: float) -> float:
    return 1 / (1 + math.exp(-log_odds))


def _frame_dose_resposta(log_odds_a, log_odds_b, *, casos=17, repeticoes=20):
    """Monta E1 sintético a partir de funções em **log-odds**, não em probabilidade.

    A distinção importa e é fácil de errar: uma diferença constante em
    probabilidade (0,8 vs 0,9, depois 0,4 vs 0,5) *não* é diferença constante em
    log-odds — o gap encolhe de 0,81 para 0,40 — e a logística leria isso como
    interação negativa. Para testar o caso nulo é preciso construir o nulo na
    escala em que o modelo trabalha.
    """
    registros = []
    for c in range(casos):
        for intensidade in INTENSIDADES:
            for arm, f in (("A", log_odds_a), ("B", log_odds_b)):
                acertos = round(_prob(f(intensidade)) * repeticoes)
                for r in range(repeticoes):
                    registros.append({
                        "case_id": f"case_{c}", "arm": arm, "seed": f"s{intensidade}",
                        "repetition": r, "intensidade": intensidade,
                        "M4": 1.0 if r < acertos else 0.0,
                    })
    return pd.DataFrame.from_records(registros)


# --- H1 --------------------------------------------------------------------
def test_h1_confirma_quando_a_vantagem_da_multi_cresce_com_a_degradacao():
    """P1.1 por construção: A despenca com a degradação, B quase não sente."""
    df = _frame_dose_resposta(lambda i: 2.0 - 4.0 * i, lambda i: 2.0 - 0.5 * i)

    r = avaliar_h1_dose_resposta(df)

    assert r.status == "sustentada"
    assert r.estimate > 0 and r.ci_low > 0


def test_h1_refuta_quando_a_diferenca_e_constante():
    """Diferença que não acompanha a causa proposta não sustenta o mecanismo."""
    # Mesmo declive em log-odds nos dois braços: interação exatamente zero.
    df = _frame_dose_resposta(lambda i: 1.5 - 2.0 * i, lambda i: 2.3 - 2.0 * i)

    r = avaliar_h1_dose_resposta(df)

    assert r.status == "inconclusiva"
    assert r.ci_low < 0 < r.ci_high


def test_h1_detecta_direcao_oposta():
    """Se a mono se sai relativamente melhor sob degradação, isso tem que aparecer."""
    df = _frame_dose_resposta(lambda i: 2.0 - 0.5 * i, lambda i: 2.0 - 4.0 * i)

    r = avaliar_h1_dose_resposta(df)

    assert r.status == "refutada_direcao_oposta"
    assert r.ci_high < 0


def test_h1_sem_variacao_de_intensidade_e_inconclusivo_nao_erro():
    df = _frame_dose_resposta(lambda i: 1.5, lambda i: 2.0)
    df["intensidade"] = 0.5

    r = avaliar_h1_dose_resposta(df)

    assert r.status == "inconclusiva"
    assert "variação" in r.detail["motivo"]


# --- H2 --------------------------------------------------------------------
def test_h2_sustentada_quando_ha_tentativa_insegura_frequente():
    df = pd.DataFrame({"arm": ["prompt_only"] * 20, "M10": [1.0] * 8 + [0.0] * 12})

    r = avaliar_h2_tentativa_insegura(df)

    assert r.status == "sustentada"
    assert r.estimate == pytest.approx(0.4)
    assert r.ci_low > 0


def test_h2_zero_tentativas_e_inconclusivo_nao_refutado():
    """Ausência na amostra não prova taxa populacional zero — doc 07 §H2."""
    df = pd.DataFrame({"arm": ["prompt_only"] * 25, "M10": [0.0] * 25})

    r = avaliar_h2_tentativa_insegura(df)

    assert r.status == "inconclusiva"
    assert r.ci_low == 0.0 and r.ci_high > 0


def test_h2_sem_braco_prompt_only_e_nao_executada():
    df = pd.DataFrame({"arm": ["pre_action_guard"] * 5, "M10": [0.0] * 5})

    assert avaliar_h2_tentativa_insegura(df).status == "nao_executada"


# --- H3 --------------------------------------------------------------------
def test_h3_detecta_diferenca_pareada_consistente():
    registros = []
    for c in range(30):
        for arm, valor in (("raw", 1.0), ("enriched", 0.0)):
            registros.append({"case_id": f"c{c}", "seed": "s", "repetition": 0,
                              "arm": arm, "M7": valor})
    r = avaliar_h3_mcnemar(pd.DataFrame.from_records(registros))

    assert r.status == "sustentada"
    assert r.detail["discordantes"] == 30


def test_h3_sem_par_discordante_e_inconclusivo():
    registros = []
    for c in range(20):
        for arm in ("raw", "enriched"):
            registros.append({"case_id": f"c{c}", "seed": "s", "repetition": 0,
                              "arm": arm, "M7": 0.0})
    r = avaliar_h3_mcnemar(pd.DataFrame.from_records(registros))

    assert r.status == "inconclusiva"
    assert r.detail["motivo"] == "nenhum par discordante"


# --- H4 --------------------------------------------------------------------
def _frame_bc(diferencas):
    registros = []
    for c, d in enumerate(diferencas):
        registros.append({"case_id": f"c{c}", "arm": "B", "M4": 1.0})
        registros.append({"case_id": f"c{c}", "arm": "C", "M4": 1.0 + d})
    return pd.DataFrame.from_records(registros)


def test_h4_sustentada_quando_a_perda_fica_dentro_da_margem():
    r = avaliar_h4_nao_inferioridade(_frame_bc([-0.01] * 30))

    assert r.status == "sustentada"
    assert r.ci_low > -MARGEM_NAO_INFERIORIDADE


def test_h4_refutada_quando_a_perda_excede_a_margem():
    r = avaliar_h4_nao_inferioridade(_frame_bc([-0.20] * 30))

    assert r.status == "refutada"
    assert r.ci_high < -MARGEM_NAO_INFERIORIDADE


def test_h4_ic_largo_e_inconclusivo_nunca_equivalente():
    """O erro mais comum em 'é tão bom quanto': confundir falta de poder com prova.

    A diferença média é ~zero, mas a dispersão é enorme e há poucos casos. Um
    teste de diferença 'não rejeitaria'; não-inferioridade tem que dizer que não
    sabe.
    """
    r = avaliar_h4_nao_inferioridade(_frame_bc([-0.6, 0.6, -0.5, 0.5, -0.55, 0.55]))

    assert r.status == "inconclusiva"
    assert r.ci_low < -MARGEM_NAO_INFERIORIDADE


def test_h4_sem_braco_c_e_nao_executada():
    df = pd.DataFrame({"case_id": ["c0"], "arm": ["B"], "M4": [1.0]})

    assert avaliar_h4_nao_inferioridade(df).status == "nao_executada"


# --- blocos ----------------------------------------------------------------
def test_bootstrap_reamostra_casos_e_e_reprodutivel():
    por_caso = {f"c{i}": v for i, v in enumerate([0.1, 0.2, 0.15, 0.3, 0.05, 0.25])}

    media, baixo, alto = bootstrap_por_caso(por_caso)
    de_novo = bootstrap_por_caso(por_caso)

    assert media == pytest.approx(sum(por_caso.values()) / 6)
    assert baixo < media < alto
    assert (media, baixo, alto) == de_novo


def test_wilson_nao_produz_limite_negativo_com_zero_sucessos():
    """O IC normal daria limite inferior negativo — e H2 mede evento raro."""
    taxa, baixo, alto = intervalo_binomial(0, 25)

    assert taxa == 0.0
    assert baixo == 0.0
    assert 0 < alto < 0.2
