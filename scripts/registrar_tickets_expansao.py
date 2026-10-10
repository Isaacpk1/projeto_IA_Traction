"""Registra os casos da expansão como tickets na API industrial.

`POST /cases/{caseId}/escalate` valida o caso contra a tabela `cases` e devolve 404 se ele
não existir. Os 17 chamados da TRACTIAN estão lá; os da expansão não estavam — então todo
escalonamento da suíte nova falhava, e o gabarito exigia uma ação impossível.

Um caso da suíte **é** um ticket: o mesmo worker o processa pelo mesmo caminho de código
que um chamado de cliente (RF39). Se ele existe para o agente, precisa existir para a API.

Os campos de curadoria da tabela (`root_question`, `expected_path`) ficam vazios de
propósito: são gabarito, e o lugar deles é a camada de avaliação (RNF02). O escalonamento
só consulta a existência do caso.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PARQUET = RAIZ / "inteli-tractian-project" / "data" / "cases.parquet"
PY_API = RAIZ / "inteli-tractian-project" / "api" / ".venv" / "bin" / "python"

SUITE = RAIZ / "src/evaluation/golden/expansion_cases.json"
casos = json.loads(SUITE.read_text("utf-8"))["cases"]
novos = [
    {
        "id": c["case_id"],
        "ticket_id": c["ticket_id"],
        "company_id": c["company_id"],
        "user_id": c["user_id"],
        "asset_id": c["asset_id"],
        "message": c["message"],
        "root_question": "",
        "mode": c.get("degradation_mode", "complete"),
        "expected_path": "[]",
    }
    for c in casos
]

temporario = RAIZ / "artifacts" / "tickets_expansao.json"
temporario.parent.mkdir(parents=True, exist_ok=True)
temporario.write_text(json.dumps(novos, ensure_ascii=False), encoding="utf-8")

script = f"""
import json, pandas as pd
alvo = {str(PARQUET)!r}
novos = json.loads(open({str(temporario)!r}, encoding="utf-8").read())
d = pd.read_parquet(alvo)
existentes = set(d["id"])
faltando = [n for n in novos if n["id"] not in existentes]
if faltando:
    d = pd.concat([d, pd.DataFrame(faltando)], ignore_index=True)
    d.to_parquet(alvo, index=False)
print(f"tabela cases: {{len(existentes)}} -> {{len(d)}} (adicionados {{len(faltando)}})")
"""
sys.exit(subprocess.run([str(PY_API), "-c", script], check=False).returncode)
