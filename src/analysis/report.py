"""Agrega execuções num relatório consumível por qualquer apresentação — doc 11 §7.

Puro e sem I/O de rede: recebe o quadro, devolve um dicionário serializável. O
front é uma view disso, não uma segunda implementação da análise — se o número
da tela divergir do número do teste, é bug, não interpretação.
"""

from __future__ import annotations

import math
from typing import Any

from src.analysis.hypotheses import (
    avaliar_h1_dose_resposta,
    avaliar_h2_tentativa_insegura,
    bootstrap_por_caso,
)

__all__ = ["METRICAS_NOMES", "montar_relatorio"]

#: Só o que o front precisa rotular. A definição canônica está em doc 07 §Métricas.
METRICAS_NOMES: dict[str, str] = {
    "M1": "Precisão de trajetória",
    "M2": "Cobertura do caminho esperado",
    "M3": "Ordem correta dos passos",
    "M4": "Acerto de decisão",
    "M5a": "Pré-condição verificada",
    "M5b": "Pré-condição verificada antes de concluir",
    "M6": "Evidência resolvível",
    "M7": "Afirmação vedada",
    "M8": "Alucinação de evidência",
    "M9": "Lacuna declarada",
    "M10": "Tentativa de ação insegura",
    "M11": "Ação executada com pré-condição",
    "M12": "Estabilidade de decisão",
    "M13": "Estabilidade de trajetória",
    "M14": "Perda de evidência no handoff",
    "M15": "Custo em tokens",
    "M16": "Escalonamento apropriado",
}

#: Onde valor MAIOR é pior. Sem isso o front pintaria de verde a métrica errada.
MENOR_E_MELHOR = frozenset({"M7", "M8", "M10", "M15"})


def _num(valor: Any) -> float | None:
    if valor is None:
        return None
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _media(serie) -> float | None:
    valores = [v for v in (_num(x) for x in serie) if v is not None]
    return sum(valores) / len(valores) if valores else None


def montar_relatorio(df, *, run_id: str = "", e2_df=None) -> dict:
    """Tudo que a apresentação precisa, calculado uma vez e em um lugar só."""
    braços = sorted({str(a) for a in df["arm"].dropna().unique()}) if len(df) else []
    por_braco = {}
    for arm in braços:
        g = df[df["arm"] == arm]
        concluidas = g[g["error_class"].isna()]
        por_braco[arm] = {
            "n": int(len(g)),
            "concluidas": int(len(concluidas)),
            "erro_comportamento": int((g["error_class"] == "behavior").sum()),
            "erro_contrato": int((g["error_class"] == "contract").sum()),
            "erro_infra": int((g["error_class"] == "infra").sum()),
            "conformidade": (len(concluidas) / len(g)) if len(g) else None,
            "llm_calls": _media(g["llm_calls"]),
            "tokens_in": _media(g["tokens_in"]),
            "duracao_s": (_media(g["duration_ms"]) or 0) / 1000,
        }

    metricas: list[dict[str, Any]] = []
    for mid in [m for m in METRICAS_NOMES if m in df.columns]:
        por_metrica: dict[str, float | None] = {
            a: _media(df[df["arm"] == a][mid]) for a in braços
        }
        linha: dict[str, Any] = {
            "id": mid,
            "nome": METRICAS_NOMES[mid],
            "menor_e_melhor": mid in MENOR_E_MELHOR,
            "por_braco": por_metrica,
            "aplicavel": {a: int(df[df["arm"] == a][mid].notna().sum()) for a in braços},
        }
        if "A" in braços and "B" in braços:
            a, b = por_metrica.get("A"), por_metrica.get("B")
            linha["diferenca"] = (b - a) if (a is not None and b is not None) else None
        metricas.append(linha)

    # Curva dose-resposta: M4 por nível de intensidade, em cada braço.
    dose: list[dict] = []
    if "intensidade" in df.columns:
        for seed in sorted({str(s) for s in df["seed"].dropna().unique()}):
            g = df[df["seed"] == seed]
            intensidade = _media(g["intensidade"])
            if intensidade is None:
                continue
            dose.append({
                "seed": seed,
                "intensidade": intensidade,
                "por_braco": {a: _media(g[g["arm"] == a]["M4"]) for a in braços},
                "n": {a: int((g["arm"] == a).sum()) for a in braços},
            })
        dose.sort(key=lambda d: d["intensidade"])

    # Diferença pareada por caso, reamostrando casos — a unidade correta.
    pareado = None
    if "A" in braços and "B" in braços and "M4" in df.columns:
        por_caso: dict[str, float] = {}
        for case_id, g in df.groupby("case_id"):
            mono = [v for v in (_num(x) for x in g[g["arm"] == "A"]["M4"]) if v is not None]
            multi = [v for v in (_num(x) for x in g[g["arm"] == "B"]["M4"]) if v is not None]
            if mono and multi:
                por_caso[str(case_id)] = sum(multi) / len(multi) - sum(mono) / len(mono)
        if por_caso:
            media, baixo, alto = bootstrap_por_caso(por_caso)
            pareado = {
                "diferenca_media": media,
                "ic_low": None if math.isnan(baixo) else baixo,
                "ic_high": None if math.isnan(alto) else alto,
                "n_casos": len(por_caso),
                "por_caso": dict(sorted(por_caso.items(), key=lambda kv: kv[1])),
            }

    h1 = avaliar_h1_dose_resposta(df) if len(df) else None
    h2 = avaliar_h2_tentativa_insegura(e2_df) if e2_df is not None and len(e2_df) else None

    return {
        "run_id": run_id,
        "execucoes": int(len(df)),
        "bracos": por_braco,
        "metricas": metricas,
        "dose_resposta": dose,
        "pareado_por_caso": pareado,
        "hipoteses": [
            {
                "id": r.hypothesis, "predicao": r.prediction, "teste": r.test,
                "metrica": r.metric, "n": r.n, "estimativa": r.estimate,
                "ic_low": r.ci_low, "ic_high": r.ci_high, "p": r.p_value,
                "status": r.status, "detalhe": r.detail,
            }
            for r in (h1, h2) if r is not None
        ],
    }
