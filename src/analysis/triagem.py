"""Triagem: quais atendimentos precisam de um humano, e por quê.

O sistema já sabia **que** algo deu errado — o trace registra decisão, veredito
do guardrail e classe de erro. O que faltava era transformar isso na pergunta que
um analista faz ao abrir a fila: *o que exige a minha atenção agora, e o que eu
preciso decidir?*

Tudo aqui é derivado do trace. Nenhum motivo é inventado, nenhum texto é gerado
por modelo: se a razão não estiver nos campos persistidos, ela não aparece no
briefing. É o que mantém a triagem auditável contra o mesmo artefato que a
originou.
"""

from __future__ import annotations

from typing import Any

__all__ = ["MOTIVOS", "URGENCIAS", "classificar", "anotar_triagem"]

#: Ordem importa: o primeiro motivo que se aplica é o que nomeia o atendimento.
#: Um caso pode ter várias coisas erradas, e o analista precisa da mais grave.
MOTIVOS = (
    "acao_bloqueada",
    "sem_resolucao",
    "evidencia_nao_resolve",
    "conflito_declarado",
    "agente_escalou",
)
URGENCIAS = ("alta", "media", "baixa")


def _tools_lidas(execucao: dict) -> list[str]:
    vistos: list[str] = []
    for passo in execucao.get("passos", []):
        tool = passo.get("tool")
        if tool and not passo.get("erro") and not tool.startswith("submit_") and tool not in vistos:
            vistos.append(tool)
    return vistos


def classificar(execucao: dict) -> dict[str, Any]:
    """Decide se o atendimento precisa de humano e monta o briefing."""
    resolucao = execucao.get("resolucao") or {}
    guard = execucao.get("guard") or {}
    decisao = resolucao.get("decision")
    bloqueado = guard.get("verdict") == "blocked"
    checagens = list(guard.get("failed") or [])
    evidencias = list(resolucao.get("evidencias") or [])
    nao_resolvem = [e for e in evidencias if not e.get("resolve")]
    lacunas = list(resolucao.get("unverified") or [])
    conflitos = list(resolucao.get("conflicts") or [])
    # `tool` é None nos passos de raciocínio, então o default do get não basta.
    tentou_acao = any(
        (passo.get("tool") or "").startswith(("update", "reprocess", "request", "escalate"))
        for passo in execucao.get("passos", [])
    )

    porque: list[str] = []
    motivo = None
    urgencia = "baixa"

    if decisao == "agir" and bloqueado:
        motivo, urgencia = "acao_bloqueada", "alta"
        porque.append(
            "O agente decidiu **agir** sobre o ativo e o guardrail determinístico barrou a entrega "
            f"({', '.join(checagens)}). Nenhum efeito externo foi emitido."
        )
    elif not resolucao:
        motivo, urgencia = "sem_resolucao", "alta"
        classe = execucao.get("error_class") or "sem classe"
        porque.append(
            f"O atendimento terminou sem resolução ({execucao.get('stop_reason')}, {classe}). "
            "Não há decisão registrada para revisar — o chamado segue em aberto."
        )
    elif bloqueado and "V1" in checagens:
        motivo, urgencia = "evidencia_nao_resolve", "media"
        porque.append(
            f"O guardrail bloqueou a entrega: {len(nao_resolvem)} de {len(evidencias)} referências "
            "de evidência não resolvem contra o trace. A conclusão pode estar certa, mas não está "
            "verificável — e o que não é verificável não é entregue."
        )
    elif conflitos:
        motivo, urgencia = "conflito_declarado", "media"
        porque.append("O agente declarou evidência conflitante e não a resolveu sozinho.")
    elif decisao == "escalar":
        motivo, urgencia = "agente_escalou", "media" if tentou_acao else "baixa"
        porque.append(
            "O próprio agente concluiu que não devia decidir sozinho e escalou. "
            "É o comportamento esperado quando a evidência não sustenta ação."
        )

    if motivo is None:
        return {"precisa_humano": False}

    if bloqueado and guard.get("decision") and decisao and guard["decision"] != decisao:
        porque.append(
            f"A decisão do agente era **{decisao}**; o guardrail entregou "
            f"**{guard['decision']}** no lugar."
        )
    if lacunas:
        porque.append("Lacunas declaradas pelo próprio agente: " + "; ".join(lacunas) + ".")

    decidir = {
        "acao_bloqueada":
            "Autorizar ou recusar a ação sobre o ativo, com base na evidência abaixo.",
        "sem_resolucao": "Atender o chamado manualmente — não há conclusão do agente para revisar.",
        "evidencia_nao_resolve":
            "Confirmar se a conclusão se sustenta nos dados antes de repassá-la.",
        "conflito_declarado": "Resolver o conflito de evidência e definir a orientação ao cliente.",
        "agente_escalou": "Decidir a orientação ao cliente com o contexto que o agente reuniu.",
    }[motivo]

    return {
        "precisa_humano": True,
        "motivo": motivo,
        "urgencia": urgencia,
        "titulo": {
            "acao_bloqueada": "Ação sobre o ativo bloqueada pelo guardrail",
            "sem_resolucao": "Atendimento terminou sem resolução",
            "evidencia_nao_resolve": "Conclusão não verificável contra o trace",
            "conflito_declarado": "Evidência conflitante não resolvida",
            "agente_escalou": "O agente escalou por decisão própria",
        }[motivo],
        "porque": porque,
        "verificado": _tools_lidas(execucao),
        "lacunas": lacunas,
        "conflitos": conflitos,
        "evidencia_frouxa": [f"{e['tool']} · {e['field']}" for e in nao_resolvem][:6],
        "decidir": decidir,
        "decisao_agente": decisao,
        "decisao_entregue": guard.get("decision"),
    }


def anotar_triagem(execucoes: list[dict]) -> list[dict]:
    """Acrescenta a triagem a cada execução, preservando o resto intacto."""
    return [{**execucao, "triagem": classificar(execucao)} for execucao in execucoes]
