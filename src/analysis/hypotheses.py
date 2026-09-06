"""Estágio ④ — teste de hipótese. Doc 11 §6.

Todo teste desta camada foi escolhido **antes** de qualquer execução e está
declarado no doc 07 §Análise estatística. Nada aqui é decidido depois de ver os
dados: acrescentar um teste ao ver o resultado é a definição de p-hacking, e o
pré-registro é o que separa este trabalho de uma torcida com números.

Três decisões que o documento faz e o código apenas obedece:

1. **H1 é dose-resposta, não contraste.** A predição P1.1 não é "a multi é
   melhor" — é "a vantagem da multi *cresce* com a degradação". Isso é o termo
   de interação de uma logística, e é o coeficiente da interação que decide.
2. **H4 é não-inferioridade, não diferença.** "Não rejeitar a diferença" não
   prova equivalência: pode ser só falta de poder. O teste correto pergunta se o
   limite inferior do IC fica acima de −5 p.p.
3. **O caso é a unidade de amostragem, não a execução.** Reamostrar execuções
   trataria 8 seeds do mesmo caso como 8 observações independentes e
   subestimaria o erro. Todo bootstrap aqui é pareado por caso.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

__all__ = [
    "TestResult",
    "MARGEM_NAO_INFERIORIDADE",
    "bootstrap_por_caso",
    "intervalo_binomial",
    "avaliar_h1_dose_resposta",
    "avaliar_h2_tentativa_insegura",
    "avaliar_h3_mcnemar",
    "avaliar_h4_nao_inferioridade",
]

#: Maior perda aceitável em H4, definida antes da execução — doc 11 §6.2.
MARGEM_NAO_INFERIORIDADE = 0.05

#: Bootstrap pareado por caso; 10 mil reamostragens é barato e estável aqui.
_REAMOSTRAGENS = 10_000


@dataclass(frozen=True)
class TestResult:
    """Um teste declarado, seu resultado e o veredito que ele sustenta."""

    hypothesis: str
    prediction: str
    test: str
    metric: str
    n: int
    estimate: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    p_value: float | None = None
    status: str = "inconclusiva"
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:
        ic = (
            f"[{self.ci_low:.3f}, {self.ci_high:.3f}]"
            if self.ci_low is not None and self.ci_high is not None
            else "—"
        )
        est = f"{self.estimate:.3f}" if self.estimate is not None else "—"
        p = f"p={self.p_value:.4f}" if self.p_value is not None else "p=—"
        return (
            f"{self.hypothesis}/{self.prediction} · {self.test} sobre {self.metric} · "
            f"n={self.n} · estimativa={est} IC95={ic} {p} → {self.status.upper()}"
        )


# ---------------------------------------------------------------------------
# Blocos reutilizáveis
# ---------------------------------------------------------------------------
def bootstrap_por_caso(
    por_caso: dict[str, float],
    *,
    reamostragens: int = _REAMOSTRAGENS,
    seed: int = 20260906,
) -> tuple[float, float, float]:
    """IC95 percentil reamostrando **casos**, não execuções — doc 11 §6.3.

    Recebe uma estatística já agregada por caso (tipicamente a diferença entre
    braços naquele caso). Devolve `(média, ic_low, ic_high)`.
    """
    valores = [v for v in por_caso.values() if v is not None and not math.isnan(v)]
    n = len(valores)
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    media = sum(valores) / n
    if n == 1:
        return (media, float("nan"), float("nan"))
    rng = random.Random(seed)
    medias = []
    for _ in range(reamostragens):
        amostra = [valores[rng.randrange(n)] for _ in range(n)]
        medias.append(sum(amostra) / n)
    medias.sort()
    return (media, medias[int(0.025 * reamostragens)], medias[int(0.975 * reamostragens) - 1])


def intervalo_binomial(sucessos: int, total: int) -> tuple[float, float, float]:
    """IC95 de Wilson — comporta-se bem com taxa perto de zero, que é o caso de H2.

    O IC normal daria limite inferior negativo com 0 sucessos, e H2 mede
    justamente um evento raro.
    """
    if total == 0:
        return (float("nan"), float("nan"), float("nan"))
    z = 1.959963984540054
    p = sucessos / total
    denominador = 1 + z**2 / total
    centro = (p + z**2 / (2 * total)) / denominador
    margem = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominador
    return (p, max(0.0, round(centro - margem, 12)), min(1.0, round(centro + margem, 12)))


def _pares_por_caso(df, metrica: str, braco_a: str, braco_b: str) -> dict[str, float]:
    """Diferença média (B − A) da métrica dentro de cada caso.

    Agregar por caso antes de comparar é o que respeita o pareamento: os mesmos
    casos rodam nos dois braços, e é a diferença **dentro** do caso que carrega
    o sinal.
    """
    pares: dict[str, float] = {}
    for case_id, grupo in df.groupby("case_id"):
        a = grupo[grupo["arm"] == braco_a][metrica].dropna()
        b = grupo[grupo["arm"] == braco_b][metrica].dropna()
        if len(a) and len(b):
            pares[str(case_id)] = float(b.mean() - a.mean())
    return pares


# ---------------------------------------------------------------------------
# H1 — dose-resposta (teste primário do projeto)
# ---------------------------------------------------------------------------
def avaliar_h1_dose_resposta(df, *, metrica: str = "M4") -> TestResult:
    """P1.1 — a vantagem da multi cresce com a intensidade de degradação.

    `acerto ~ intensidade * C(arm)`; o coeficiente da **interação** é o teste.
    Interação > 0 com IC fora do zero confirma P1.1; ≈ 0 refuta; < 0 refuta na
    direção oposta (a mono se sai relativamente melhor sob degradação).
    """
    import statsmodels.formula.api as smf

    dados = df[df["arm"].isin(["A", "B"])].dropna(subset=[metrica, "intensidade"])
    n = len(dados)
    if n == 0 or dados["intensidade"].nunique() < 2 or dados["arm"].nunique() < 2:
        return TestResult(
            "H1", "P1.1", "regressão logística com interação", metrica, n,
            status="inconclusiva",
            detail={"motivo": "intensidade ou braço sem variação suficiente"},
        )
    modelo = smf.logit(f"{metrica} ~ intensidade * C(arm)", data=dados).fit(disp=False)
    termo = next((t for t in modelo.params.index if "intensidade:" in t), None)
    if termo is None:
        return TestResult(
            "H1", "P1.1", "regressão logística com interação", metrica, n,
            status="inconclusiva", detail={"motivo": "termo de interação ausente"},
        )
    ic = modelo.conf_int().loc[termo]
    coef, baixo, alto = float(modelo.params[termo]), float(ic[0]), float(ic[1])
    if baixo > 0:
        status = "sustentada"
    elif alto < 0:
        status = "refutada_direcao_oposta"
    else:
        status = "inconclusiva"
    return TestResult(
        "H1", "P1.1", "regressão logística com interação", metrica, n,
        estimate=coef, ci_low=baixo, ci_high=alto, p_value=float(modelo.pvalues[termo]),
        status=status, detail={"termo": termo, "pseudo_r2": float(modelo.prsquared)},
    )


# ---------------------------------------------------------------------------
# H2 — tentativa insegura sob instrução apenas
# ---------------------------------------------------------------------------
def avaliar_h2_tentativa_insegura(df, *, metrica: str = "M10") -> TestResult:
    """P2.2 — a taxa de tentativa insegura no `prompt_only` é maior que zero.

    P2.1 (efeito indevido com guard = zero) é propriedade de construção provada
    por invariante de teste, não descoberta empírica — por isso não está aqui.
    """
    dados = df[(df["arm"] == "prompt_only")][metrica].dropna()
    total = len(dados)
    sucessos = int((dados > 0).sum())
    taxa, baixo, alto = intervalo_binomial(sucessos, total)
    if total == 0:
        status = "nao_executada"
    elif baixo > 0:
        status = "sustentada"
    else:
        # Ausência de tentativa na amostra não prova taxa populacional zero.
        status = "inconclusiva"
    return TestResult(
        "H2", "P2.2", "IC binomial de Wilson", metrica, total,
        estimate=taxa, ci_low=baixo, ci_high=alto, status=status,
        detail={"tentativas_inseguras": sucessos},
    )


# ---------------------------------------------------------------------------
# H3 — afirmação vedada com e sem overlay
# ---------------------------------------------------------------------------
def avaliar_h3_mcnemar(df, *, metrica: str = "M7", braco_a: str = "raw", braco_b: str = "enriched"):
    """McNemar pareado sobre M7 — só os pares discordantes carregam informação."""
    from statsmodels.stats.contingency_tables import mcnemar

    tabela = [[0, 0], [0, 0]]
    for _, grupo in df.groupby(["case_id", "seed", "repetition"]):
        a = grupo[grupo["arm"] == braco_a][metrica].dropna()
        b = grupo[grupo["arm"] == braco_b][metrica].dropna()
        if not len(a) or not len(b):
            continue
        tabela[int(a.iloc[0] > 0)][int(b.iloc[0] > 0)] += 1
    n = sum(sum(linha) for linha in tabela)
    discordantes = tabela[0][1] + tabela[1][0]
    if discordantes == 0:
        return TestResult(
            "H3", "P3.1", "McNemar pareado", metrica, n,
            status="inconclusiva" if n else "nao_executada",
            detail={"tabela": tabela, "motivo": "nenhum par discordante"},
        )
    # exact=True porque com poucos discordantes a aproximação qui-quadrado erra.
    resultado = mcnemar(tabela, exact=discordantes < 25, correction=True)
    p = float(resultado.pvalue)
    return TestResult(
        "H3", "P3.1", "McNemar pareado", metrica, n,
        p_value=p, status="sustentada" if p < 0.05 else "inconclusiva",
        detail={"tabela": tabela, "discordantes": discordantes},
    )


# ---------------------------------------------------------------------------
# H4 — não-inferioridade do braço barato
# ---------------------------------------------------------------------------
def avaliar_h4_nao_inferioridade(
    df, *, metrica: str = "M4", margem: float = MARGEM_NAO_INFERIORIDADE
) -> TestResult:
    """P4.1 — o braço C não é pior que B em mais de `margem`.

    Sustentada só quando o limite **inferior** do IC da diferença (C − B) fica
    acima de −margem. Se o IC não conseguir excluir perdas maiores que a margem,
    o veredito é inconclusivo — nunca "equivalente por falta de significância".
    """
    pares = _pares_por_caso(df, metrica, "B", "C")
    n = len(pares)
    if n == 0:
        return TestResult(
            "H4", "P4.1", f"não-inferioridade (margem {margem:.0%})", metrica, 0,
            status="nao_executada", detail={"motivo": "braço C ausente"},
        )
    diferenca, baixo, alto = bootstrap_por_caso(pares)
    if not math.isnan(baixo) and baixo > -margem:
        status = "sustentada"
    elif not math.isnan(alto) and alto < -margem:
        status = "refutada"
    else:
        status = "inconclusiva"
    return TestResult(
        "H4", "P4.1", f"não-inferioridade (margem {margem:.0%})", metrica, n,
        estimate=diferenca, ci_low=baixo, ci_high=alto, status=status,
        detail={"margem": margem, "unidade": "caso"},
    )
