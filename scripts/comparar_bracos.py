"""Compara os braços da suíte estratificada — determinístico, sem juiz.

O contraste é **pareado por caso**: cada caso roda nos três braços, então a diferença
entre eles não carrega variação de dificuldade. É o mesmo desenho do E2.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evaluation.golden import load_expansion_dataset

RAIZ = Path(__file__).resolve().parents[1]
RUN = sys.argv[1] if len(sys.argv) > 1 else "estrato01"
TRACES = RAIZ / "artifacts" / "traces" / RUN

casos = load_expansion_dataset().by_id()
vigentes = {
    linha[0]
    for linha in sqlite3.connect(RAIZ / "artifacts" / "queue.db").execute(
        "SELECT execution_id FROM tasks WHERE run_id = ? AND state = 'done' "
        "AND execution_id IS NOT NULL",
        (RUN,),
    )
}

por_braco: dict[str, dict[str, dict]] = defaultdict(dict)
for arquivo in sorted(TRACES.glob("*.jsonl")):
    if arquivo.stem not in vigentes:
        continue
    registros = [
        json.loads(linha)
        for linha in arquivo.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]
    finais = [r["trace"] for r in registros if r.get("type") == "execution_finished"]
    if not finais:
        continue
    trace = finais[-1]
    golden = casos.get(trace.get("case_id"))
    if golden is None:
        continue
    resolucao = trace.get("resolution") or {}
    passos = [s for s in trace.get("steps", []) if s.get("tool") != "submit_resolution"]
    escalou_de_fato = any(
        s.get("tool") == "escalateCase" and not s.get("error") for s in trace.get("steps", [])
    )
    por_braco[trace["arm"]][golden.case_id] = {
        "esperada": golden.expected_decision,
        "obtida": resolucao.get("decision"),
        "acerto": resolucao.get("decision") == golden.expected_decision,
        "consultas": len(passos),
        "recusas_do_portao": sum(
            1
            for s in trace.get("steps", [])
            if s.get("tool") == "submit_resolution" and s.get("error")
        ),
        "escalou_de_fato": escalou_de_fato,
    }

bracos = sorted(por_braco)
if not bracos:
    print(f"nenhum trace concluído em {TRACES}")
    raise SystemExit(1)

print(f"=== {RUN} · estrato de {len(casos)} casos · sem juiz ===\n")
print(
    f"{'braço':20} {'n':>3} {'acertos':>9} {'escalou certo':>14} "
    f"{'consultas':>10} {'recusas':>8}"
)
for braco in bracos:
    linhas = por_braco[braco].values()
    n = len(linhas)
    acertos = sum(x["acerto"] for x in linhas)
    consultas = sum(x["consultas"] for x in linhas) / n if n else 0
    recusas = sum(x["recusas_do_portao"] for x in linhas)
    escalou_certo = sum(
        1 for x in linhas if x["escalou_de_fato"] and x["esperada"] == "escalar"
    )
    print(
        f"{braco:20} {n:>3} {acertos:>4}/{n:<4} {escalou_certo:>14} "
        f"{consultas:>10.1f} {recusas:>8}"
    )

comuns = set.intersection(*(set(por_braco[b]) for b in bracos)) if len(bracos) > 1 else set()
if len(bracos) > 1 and comuns:
    base = bracos[0]
    print(f"\n--- pareado contra `{base}` ({len(comuns)} casos em comum) ---")
    for braco in bracos[1:]:
        virou_certo = [
            c
            for c in comuns
            if not por_braco[base][c]["acerto"] and por_braco[braco][c]["acerto"]
        ]
        virou_errado = [
            c
            for c in comuns
            if por_braco[base][c]["acerto"] and not por_braco[braco][c]["acerto"]
        ]
        print(f"{braco}: consertou {len(virou_certo)} · quebrou {len(virou_errado)}")
        for c in virou_certo:
            print(f"   + {c}: {por_braco[base][c]['obtida']} -> {por_braco[braco][c]['obtida']}")
        for c in virou_errado:
            print(f"   - {c}: {por_braco[base][c]['obtida']} -> {por_braco[braco][c]['obtida']}")
