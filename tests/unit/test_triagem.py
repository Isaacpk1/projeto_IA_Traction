"""Triagem — quais atendimentos precisam de humano e por quê.

Tudo aqui é derivado do trace. O que estes testes protegem é a ordem de
gravidade: um caso pode ter várias coisas erradas ao mesmo tempo, e o analista
precisa que o atendimento seja nomeado pela mais grave, não pela primeira.
"""

from __future__ import annotations

import pytest

from src.analysis.triagem import anotar_triagem, classificar


def _exec(**kw):
    base = {
        "id": "e", "case_id": "case_tkt_inv_06", "arm": "A", "error_class": None,
        "stop_reason": "sufficient", "passos": [], "handoffs": [],
        "guard": {"verdict": "pass", "failed": [], "decision": "orientar"},
        "resolucao": {"decision": "orientar", "justification": "j", "unverified": [],
                      "conflicts": [], "evidencias": []},
    }
    base.update(kw)
    return base


def test_atendimento_limpo_nao_precisa_de_humano():
    assert classificar(_exec())["precisa_humano"] is False


def test_acao_bloqueada_vence_as_demais_razoes():
    """Decidiu agir e o guard barrou: é o mais grave, mesmo com outras pendências."""
    t = classificar(_exec(
        resolucao={"decision": "agir", "justification": "j",
                   "unverified": ["falta baseline"], "conflicts": ["a vs b"],
                   "evidencias": [{"tool": "x", "field": "y", "resolve": False}]},
        guard={"verdict": "blocked", "failed": ["V1"], "decision": "escalar"},
    ))

    assert t["motivo"] == "acao_bloqueada"
    assert t["urgencia"] == "alta"
    # A troca de decisão pelo guardrail precisa aparecer: é o que o humano revisa.
    assert any("agir" in b and "escalar" in b for b in t["porque"])
    assert any("falta baseline" in b for b in t["porque"])


def test_execucao_sem_resolucao_e_urgencia_alta():
    t = classificar(_exec(resolucao=None, error_class="behavior", stop_reason="max_steps"))

    assert t["motivo"] == "sem_resolucao"
    assert t["urgencia"] == "alta"
    assert "max_steps" in t["porque"][0]


def test_evidencia_que_nao_resolve_bloqueia_a_entrega():
    t = classificar(_exec(
        resolucao={"decision": "orientar", "justification": "j", "unverified": [], "conflicts": [],
                   "evidencias": [{"tool": "getBaseline", "field": "data.state", "resolve": False},
                                  {"tool": "getAsset", "field": "data.id", "resolve": True}]},
        guard={"verdict": "blocked", "failed": ["V1"], "decision": "escalar"},
    ))

    assert t["motivo"] == "evidencia_nao_resolve"
    assert "1 de 2" in t["porque"][0]
    assert t["evidencia_frouxa"] == ["getBaseline · data.state"]


def test_escalonamento_do_proprio_agente_e_comportamento_esperado():
    t = classificar(_exec(resolucao={"decision": "escalar", "justification": "j",
                                     "unverified": [], "conflicts": [], "evidencias": []}))

    assert t["motivo"] == "agente_escalou"
    assert t["urgencia"] == "baixa"


def test_conflito_declarado_pede_humano_mesmo_sem_bloqueio():
    t = classificar(_exec(resolucao={"decision": "orientar", "justification": "j",
                                     "unverified": [], "conflicts": ["baseline vs espectro"],
                                     "evidencias": []}))

    assert t["motivo"] == "conflito_declarado"


def test_briefing_lista_o_que_foi_efetivamente_lido():
    """O humano precisa saber o que já foi checado para não repetir trabalho."""
    t = classificar(_exec(
        resolucao={"decision": "escalar", "justification": "j", "unverified": [],
                   "conflicts": [], "evidencias": []},
        passos=[{"tool": "getAsset"}, {"tool": "getBaseline"},
                {"tool": "getModel", "erro": "HTTP 404"},
                {"tool": "submit_resolution"}, {"tool": None, "reasoning": "pensando"}],
    ))

    # Tool com erro não conta como verificada; submit_* e raciocínio não são leitura.
    assert t["verificado"] == ["getAsset", "getBaseline"]


@pytest.mark.parametrize("motivo_esperado,kw", [
    ("sem_resolucao", {"resolucao": None}),
    ("agente_escalou", {"resolucao": {"decision": "escalar", "justification": "j",
                                      "unverified": [], "conflicts": [], "evidencias": []}}),
])
def test_todo_atendimento_marcado_diz_o_que_decidir(motivo_esperado, kw):
    t = classificar(_exec(**kw))

    assert t["motivo"] == motivo_esperado
    assert t["decidir"] and t["titulo"]


def test_anotar_preserva_a_execucao_original():
    execucoes = [_exec(id="a"), _exec(id="b", resolucao=None)]

    anotadas = anotar_triagem(execucoes)

    assert [e["id"] for e in anotadas] == ["a", "b"]
    assert all("passos" in e and "triagem" in e for e in anotadas)
    assert execucoes[0].get("triagem") is None
