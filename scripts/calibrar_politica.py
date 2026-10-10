"""Calibra a política contra os 17 casos base: a regra tem que reproduzir o rótulo conhecido.

A intenção de cada caso vem do `root_question` da TRACTIAN (`eval/expected-paths.json`),
não da minha leitura da mensagem; a análise-alvo vem do id que aparece na trajetória
esperada deles. Assim o único insumo humano é o mapeamento pergunta->intenção, que fica
explícito aqui e é auditável.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.situacao_api import montar
from src.evaluation.golden.policy import decidir

RAIZ = Path(__file__).resolve().parents[1]
CASOS_JSON = RAIZ / "inteli-tractian-project/agent-input/cases.json"
PATHS_JSON = RAIZ / "inteli-tractian-project/eval/expected-paths.json"
casos = {c["id"]: c for c in json.loads(CASOS_JSON.read_text())}
trajs = {p["id"]: p for p in json.loads(PATHS_JSON.read_text())}
ann = json.loads((RAIZ / "src/evaluation/golden/annotations.json").read_text())["cases"]

#: root_question (texto da TRACTIAN) -> intenção da política.
INTENCAO_POR_CASO = {
    "case_tkt_inv_04": "explicar_ausencia_de_alerta",
    "case_tkt_inv_05": "explicar_ausencia_de_alerta",
    "case_tkt_inv_06": "validar_insight",
    "case_tkt_inv_07": "diagnosticar_eletrico",
    "case_tkt_inv_08": "resolver_conflito",
    "case_tkt_inv_09": "validar_insight",
    "case_tkt_inv_10": "confiar_no_dado",
    "case_tkt_inv_11": "perguntar_cobertura",
    "case_tkt_inv_11b": "validar_insight",
    "case_tkt_exe_12": "pedir_reprocesso",
    "case_tkt_exe_16": "pedir_visita_campo",
    "case_tkt_ctx_01": "perguntar_procedimento",
    "case_tkt_ctx_02": "perguntar_termo",
    "case_tkt_ctx_03": "perguntar_limiar",
    "case_tkt_exe_13": "pedir_especialista",
    "case_tkt_exe_14": "pedir_mudanca_config",
    "case_tkt_exe_15": "pedir_retreinamento",
}


def alvo_da_trajetoria(cid: str) -> str | None:
    ids = [m for s in trajs[cid]["expected_path"] for m in re.findall(r"an_\d+", s["step"])]
    return ids[0] if ids else None


acertos = 0
print(
    f"{'caso':20} {'intenção':30} {'regra':5} {'política':9} "
    f"{'gabarito':9} {'ação política':26} veredito"
)
print("-" * 130)
for cid, caso in casos.items():
    s = montar(
        user_id=caso["user_id"],
        asset_id=caso["asset_id"],
        intencao=INTENCAO_POR_CASO[cid],
        analise_alvo_id=alvo_da_trajetoria(cid),
    )
    v = decidir(s)
    esperado = ann[cid]["expected_decision"]
    acoes_gab = tuple(ann[cid].get("expected_actions", ()))
    bate = v.decisao == esperado and tuple(v.acoes) == acoes_gab
    acertos += bate
    print(
        f"{cid:20} {INTENCAO_POR_CASO[cid]:30} {v.regra:5} {v.decisao:9} {esperado:9} "
        f"{str(list(v.acoes)):26} "
        f"{'OK' if bate else 'DIVERGE (gabarito=' + str(list(acoes_gab)) + ')'}"
    )
print("-" * 130)
print(f"política reproduz {acertos}/17 rótulos dos casos base")
