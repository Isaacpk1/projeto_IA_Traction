"""Verifica a suíte de expansão: invariantes do loader + pré-condições contra a API viva.

O erro que esta verificação existe para pegar é o do `case_tkt_ctx_03`, cujo caminho
`data.features.rms_mm_s.reference` nunca resolve porque `features` é lista. Um gabarito
que exige um fato inalcançável reprova o agente por um bug da curadoria.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.situacao_api import MODELO, get
from src.core.contracts.golden import GoldenCase
from src.core.evidence import resolve_field
from src.evaluation.golden.loader import _IMPACT_TOOLS, _validate_curated_cases

RAIZ = Path(__file__).resolve().parents[1]
doc = json.loads((RAIZ / "src/evaluation/golden/expansion_cases.json").read_text())
casos = doc["cases"]

PERMISSAO = {
    "reprocessAnalysis": "action_low", "requestSpecialistAnalysis": "action_low",
    "requestRetraining": "action_high", "updateAssetConfig": "action_high",
    "escalateCase": "escalate",
}
ROTA = {
    "getAsset": lambda c, a: f"/assets/{c['asset_id']}",
    "getBaseline": lambda c, a: f"/assets/{c['asset_id']}/baseline",
    "getRmsSeries": lambda c, a: f"/assets/{c['asset_id']}/rms",
    "getSpectrum": lambda c, a: f"/assets/{c['asset_id']}/spectrum",
    "getDataQuality": lambda c, a: f"/assets/{c['asset_id']}/data-quality",
    "listAnalyses": lambda c, a: f"/assets/{c['asset_id']}/analyses",
    "getAnalysis": lambda c, a: f"/analyses/{a}" if a else None,
    "getModel": lambda c, a: f"/models/{MODELO}",
    "getCurrentUser": lambda c, a: "/users/me",
    "getCompany": lambda c, a: f"/companies/{c['company_id']}",
    "listCompanyAssets": lambda c, a: f"/companies/{c['company_id']}/assets",
    "searchKnowledge": lambda c, a: None,
    "getKnowledgeDoc": lambda c, a: None,
}

problemas: list[str] = []

# ---- 1. contrato + invariantes de curadoria do loader ------------------------
objetos = [
    GoldenCase.model_validate({k: v for k, v in c.items() if not k.startswith("_")})
    for c in casos
]
try:
    _validate_curated_cases(objetos)
    print(f"[OK ] {len(objetos)} casos passam no contrato GoldenCase e nas invariantes do loader")
except Exception as exc:
    print(f"[ERRO] invariantes do loader: {exc}")
    problemas.append("invariantes")

# ---- 2. coerência de identidade e permissão ---------------------------------
usuarios = {}
for c in casos:
    u = c["user_id"]
    if u not in usuarios:
        usuarios[u] = get("/users/me", user_id=u, seed=None)
    ativo = get(f"/assets/{c['asset_id']}").get("data", {})
    if ativo.get("company_id") != c["company_id"]:
        problemas.append(f"{c['case_id']}: empresa do caso != empresa do ativo")
    if usuarios[u].get("company_id") != c["company_id"]:
        problemas.append(f"{c['case_id']}: usuário {u} não pertence a {c['company_id']}")
    perms = set(usuarios[u].get("permissions") or [])
    for acao in c["expected_actions"]:
        if PERMISSAO[acao] not in perms:
            problemas.append(
                f"{c['case_id']}: ação {acao} exige {PERMISSAO[acao]}, que {u} não tem"
            )
    if set(c["expected_actions"]) & set(c["forbidden_actions"]):
        problemas.append(f"{c['case_id']}: ação esperada e proibida ao mesmo tempo")
print(f"[{'OK ' if not problemas else 'ERRO'}] identidade, tenancy e permissão")

# ---- 3. toda pré-condição resolve de verdade --------------------------------
inalcancaveis, checadas = [], 0
for c in casos:
    alvo = next((p["args_contains"].get("analysisId") for p in c["expected_path"]
                 if p["tool"] == "getAnalysis"), None)
    for fato in c["required_preconditions"]:
        checadas += 1
        achou = False
        for tool in fato["sources"]:
            rota = ROTA[tool](c, alvo)
            if rota is None:
                continue
            env = get(rota, user_id=c["user_id"] if tool == "getCurrentUser" else None,
                      seed=None if tool == "getCurrentUser" else "complete")
            for caminho in fato["field_paths"]:
                try:
                    valor = resolve_field(env, caminho)
                except KeyError:
                    continue
                texto = (
                    valor
                    if isinstance(valor, str)
                    else json.dumps(valor, ensure_ascii=False, sort_keys=True)
                )
                esperados = [v.casefold() for v in fato.get("expected_values", [])]
                if esperados and texto.casefold() not in esperados:
                    continue
                achou = True
        if not achou:
            inalcancaveis.append(
                f"{c['case_id']}:{fato['fact_id']} "
                f"({fato['sources']} {fato['field_paths']})"
            )
print(
    f"[{'OK ' if not inalcancaveis else 'ERRO'}] "
    f"{checadas} pré-condições verificadas contra a API"
)
for item in inalcancaveis:
    print(f"       INALCANÇÁVEL {item}")

# ---- 4. grupos de evidência alcançáveis na trajetória ------------------------
for c in casos:
    disponiveis = {t for p in c["expected_path"] for t in (p["tool"], *p.get("alternatives", []))}
    for grupo in c["required_evidence_groups"]:
        if not disponiveis & set(grupo):
            problemas.append(f"{c['case_id']}: grupo {grupo} fora da trajetória")
    acoes_caminho = {p["tool"] for p in c["expected_path"]} & _IMPACT_TOOLS
    if acoes_caminho != set(c["expected_actions"]):
        problemas.append(f"{c['case_id']}: ações da trajetória != expected_actions")


print("\n" + "=" * 70)
print(f"decisões:  {dict(Counter(c['expected_decision'] for c in casos))}")
print(f"ações:     {dict(Counter(a for c in casos for a in c['expected_actions']))}")
regras_distintas = len(Counter(c["_geracao"]["regra_decisiva"] for c in casos))
print(f"regras:    {regras_distintas} distintas acionadas")
print(f"ativos:    {len({c['asset_id'] for c in casos})} distintos")
print(f"usuários:  {len({c['user_id'] for c in casos})} distintos")
print("=" * 70)
if problemas or inalcancaveis:
    print(f"\n{len(problemas) + len(inalcancaveis)} PROBLEMA(S):")
    for p in problemas:
        print("  -", p)
    sys.exit(1)
print("\nsuíte de expansão íntegra")
