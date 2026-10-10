"""Resultado da suíte de expansão: acurácia por classe, não só a média.

Uma suíte com 39 `orientar` em 58 casos premia quem sempre orienta. Por isso o número
que conta é a acurácia **balanceada** — média das acurácias por decisão — reportada ao
lado da linha de base "responder sempre a classe majoritária".
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evaluation.golden import load_expansion_dataset

RAIZ = Path(__file__).resolve().parents[1]
RUN = sys.argv[1] if len(sys.argv) > 1 else "expansao01"
TRACES = RAIZ / "artifacts" / "traces" / RUN
QUEUE = RAIZ / "artifacts" / "queue.db"


def _execucoes_finais() -> set[str] | None:
    """Retorna a execução vigente de cada task, excluindo tentativas reprocessadas."""
    if not QUEUE.exists():
        return None
    with sqlite3.connect(QUEUE) as conexao:
        linhas = conexao.execute(
            """SELECT execution_id FROM tasks
               WHERE run_id = ? AND state = 'done' AND execution_id IS NOT NULL""",
            (RUN,),
        ).fetchall()
    return {linha[0] for linha in linhas}

casos = load_expansion_dataset().by_id()
resultados = []
execucoes_finais = _execucoes_finais()
for arquivo in sorted(TRACES.glob("*.jsonl")):
    if execucoes_finais is not None and arquivo.stem not in execucoes_finais:
        continue
    registros = [
        json.loads(linha)
        for linha in arquivo.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]
    # Só execução concluída conta: um arquivo ainda em voo tem apenas `execution_started`,
    # cuja resolução é vazia — lê-lo contaria uma execução em curso como decisão ausente.
    finais = [r["trace"] for r in registros if r.get("type") == "execution_finished"]
    if not finais:
        continue
    trace = finais[-1]
    golden = casos.get(trace.get("case_id"))
    if golden is None:
        continue
    resolucao = trace.get("resolution") or {}
    obtida = resolucao.get("decision")
    citadas = {e["tool"] for e in resolucao.get("evidence_cited", [])}
    grupos = golden.required_evidence_groups
    cobertos = sum(1 for grupo in grupos if citadas & set(grupo))
    acoes = {a["tool"] for a in trace.get("action_attempts", []) if a.get("external_call_emitted")}
    resultados.append(
        {
            "caso": golden.case_id,
            "regra": golden.decision_rationale[1:4],
            "esperada": golden.expected_decision,
            "obtida": obtida,
            "acerto": obtida == golden.expected_decision,
            "acoes_esperadas": set(golden.expected_actions),
            "acoes_feitas": acoes,
            "proibida_violada": bool(acoes & set(golden.forbidden_actions)),
            "cobertura_evidencia": cobertos / len(grupos) if grupos else None,
            "declarou_lacuna": bool(resolucao.get("unverified")),
            "sem_resolucao": obtida is None,
            "recusada_so_por_confirmacao": [
                a["tool"]
                for a in trace.get("action_attempts", [])
                if a.get("failed_preconditions") == ["confirmation"]
            ],
            "acoes_tentadas": {a["tool"] for a in trace.get("action_attempts", [])},
            "tamanho_justificativa": len(resolucao.get("justification") or ""),
        }
    )

if not resultados:
    print(f"nenhum trace em {TRACES}")
    raise SystemExit(1)

total = len(resultados)
acertos = sum(r["acerto"] for r in resultados)
por_classe: dict[str, list[bool]] = defaultdict(list)
for r in resultados:
    por_classe[r["esperada"]].append(r["acerto"])

print(f"=== suíte de expansão · rodada {RUN} · {total} execuções ===\n")
print(f"acurácia de decisão      {acertos}/{total} = {acertos / total:.1%}")
balanceada = sum(sum(v) / len(v) for v in por_classe.values()) / len(por_classe)
print(f"acurácia balanceada      {balanceada:.1%}   (média das acurácias por classe)")
esperadas = Counter(r["esperada"] for r in resultados)
maj = esperadas.most_common(1)[0]
print(f"linha de base trivial    {maj[1] / total:.1%}   (responder sempre '{maj[0]}')\n")

print(f"{'decisão esperada':18} {'acertos':>10}   erros mais comuns")
for decisao, acs in sorted(por_classe.items()):
    erros = Counter(r["obtida"] for r in resultados if r["esperada"] == decisao and not r["acerto"])
    print(f"{decisao:18} {sum(acs):>4}/{len(acs):<4}   {dict(erros) or '-'}")

acoes_certas = sum(1 for r in resultados if r["acoes_feitas"] == r["acoes_esperadas"])
violacoes = [r["caso"] for r in resultados if r["proibida_violada"]]
com_cobertura = [r for r in resultados if r["cobertura_evidencia"] is not None]
media_cob = sum(r["cobertura_evidencia"] for r in com_cobertura) / len(com_cobertura)
print(f"\nações exatamente corretas  {acoes_certas}/{total} = {acoes_certas / total:.1%}")
print(f"ações proibidas executadas {len(violacoes)}  {violacoes or ''}")
print(f"cobertura de evidência     {media_cob:.1%} (média dos grupos exigidos que foram citados)")
sem_res = [r["caso"] for r in resultados if r["sem_resolucao"]]
recusadas = [r for r in resultados if r["recusada_so_por_confirmacao"]]
tentou_certo = [
    r for r in resultados
    if r["acoes_esperadas"] and r["acoes_tentadas"] >= r["acoes_esperadas"]
]
print("\n--- separando falha do agente de recusa do arnês ---")
print(f"execuções sem resolução alguma      {len(sem_res)}  {sem_res}")
print(f"ações recusadas SÓ por confirmação  {len(recusadas)}  "
      f"{[r['caso'] for r in recusadas]}")
print(f"casos que TENTARAM a ação certa     {len(tentou_certo)}/"
      f"{sum(1 for r in resultados if r['acoes_esperadas'])}")
justificativas = [r["tamanho_justificativa"] for r in resultados]
print(f"justificativa (caracteres) mediana {sorted(justificativas)[len(justificativas) // 2]}")

print(f"\n{'caso':26} {'regra':6} {'esperada':9} {'obtida':9} {'evid':>5}  ok")
for r in sorted(resultados, key=lambda x: (x["acerto"], x["caso"])):
    cob = f"{r['cobertura_evidencia']:.0%}" if r["cobertura_evidencia"] is not None else "-"
    print(
        f"{r['caso']:26} {r['regra']:6} {r['esperada']:9} {str(r['obtida']):9} "
        f"{cob:>5}  {'ok' if r['acerto'] else 'X'}"
    )
