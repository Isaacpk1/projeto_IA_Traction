"""Intensidade de degradação por par caso–seed — doc 07 §3.1.

É a variável explicativa do teste primário de H1. P1.1 não afirma "a multi é
melhor": afirma que **a vantagem da multi cresce conforme a evidência piora**.
Sem um número para "quanto piorou", essa frase não é testável.

Duas propriedades que o documento exige e que este módulo garante:

1. **É exógena.** Depende só de `(caso, seed)`, nunca do que o agente decidiu
   chamar. Se fosse calculada sobre as tools efetivamente chamadas, a
   arquitetura alteraria a própria variável explicativa e a regressão mediria
   o próprio agente.
2. **É calculada sobre um conjunto fixo.** Os `degradation_probes` do golden
   definem, por caso, quais recursos importam. Eles são os mesmos nos dois
   braços e em todos os seeds.

O módulo é puro: recebe os modos já observados e devolve o número. Quem fala com
a API é o composition root, porque `evaluation/` não conhece `tools/`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

__all__ = [
    "PESO_POR_MODO",
    "VERSAO_ESCALA",
    "intensidade",
    "IntensityTable",
    "salvar_intensidade",
    "carregar_intensidade",
]

#: Severidade de cada modo do envelope `{mode, notes, data}`, de 0 (evidência
#: completa) a 1 (nenhuma evidência).
#:
#: **Esta escala é uma decisão analítica, não um dado.** Ela está declarada aqui,
#: antes de olhar o resultado de H1, justamente para não ser ajustada depois —
#: escolher a escala depois de ver o coeficiente seria escolher o resultado.
#:
#: A ordenação segue quanto cada modo impede uma conclusão fundamentada:
#:   complete      evidência íntegra
#:   partial       faltam campos, mas dá para concluir declarando a lacuna
#:   inconclusive  o próprio recurso declara que não conclui
#:   conflict      há evidência, e ela se contradiz — concluir exige resolver
#:                 a contradição, que é o modo de falha central do domínio
#:   unavailable   não há evidência alguma
#:
#: `conflict` e `inconclusive` recebem o mesmo peso de propósito: não há base
#: empírica para ordená-los entre si, e inventar uma diferença seria fabricar
#: precisão. A análise reporta a sensibilidade a essa escolha.
PESO_POR_MODO: Mapping[str, float] = {
    "complete": 0.00,
    "partial": 0.50,
    "inconclusive": 0.75,
    "conflict": 0.75,
    "unavailable": 1.00,
}

#: Muda junto com PESO_POR_MODO. Uma tabela gravada com escala diferente não é
#: comparável com outra, e a versão é o que torna isso detectável.
VERSAO_ESCALA = "1.0.0"

#: `(case_id, seed) -> intensidade`.
IntensityTable = dict[tuple[str, str], float]


def intensidade(modos: Iterable[str]) -> float:
    """Média das severidades dos recursos sondados.

    Média, e não máximo: um caso com um recurso indisponível entre quatro
    completos é menos degradado que um com os quatro indisponíveis, e o máximo
    apagaria essa diferença — que é exatamente a variação que a dose-resposta
    precisa enxergar.

    Modo desconhecido conta como `complete`: é o valor conservador. Inflar a
    intensidade por um rótulo que não sabemos ler produziria dose falsa.
    """
    pesos = [PESO_POR_MODO.get(modo, 0.0) for modo in modos]
    if not pesos:
        raise ValueError("intensidade exige ao menos um recurso sondado")
    return sum(pesos) / len(pesos)


def salvar_intensidade(
    caminho: str | Path,
    tabela: IntensityTable,
    *,
    detalhe: Mapping[tuple[str, str], list[str]] | None = None,
) -> int:
    """Grava a tabela versionada ao lado do dataset — doc 07 §3.1.

    Guarda também os modos observados: sem eles, um número entre 0 e 1 é
    inauditável, e a promessa de reprodutibilidade fica só na palavra.
    """
    registros = []
    for (case_id, seed), valor in sorted(tabela.items()):
        registro = {"case_id": case_id, "seed": seed, "intensity": round(valor, 6)}
        if detalhe is not None:
            registro["modes"] = detalhe.get((case_id, seed), [])
        registros.append(registro)
    documento = {
        "scale_version": VERSAO_ESCALA,
        "weights": dict(PESO_POR_MODO),
        "entries": registros,
    }
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(documento, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return len(registros)


def carregar_intensidade(caminho: str | Path) -> IntensityTable:
    documento = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {
        (item["case_id"], item["seed"]): float(item["intensity"])
        for item in documento.get("entries", [])
    }
