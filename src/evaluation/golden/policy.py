"""Política de decisão pré-registrada — o gabarito derivado de regra, não de opinião.

Cada regra cita a fonte externa que a justifica: as políticas dos cenários da TRACTIAN
(`eval/test-scenarios.md`), os documentos de conhecimento da própria API (`kb_guid_*`,
`kb_proc_001`) e as regras de permissão do contrato (`require_permission` em
`api/app/main.py`). Nenhuma regra foi escrita olhando para um caso específico.

O procedimento que dá imparcialidade ao gabarito é este: a tabela é fixada aqui, é
**calibrada contra os 17 casos base** (se não reproduz os rótulos conhecidos, a regra
está errada — não o caso), e só então é aplicada às células de dado que os 17 não
cobrem. O autor humano escreve o *estímulo* (a mensagem do cliente); o *rótulo* sai
daqui.

Módulo puro: não faz I/O e não conhece a suíte. `Situacao` é montada por quem consulta
a API.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.contracts.resolution import Decision

__all__ = [
    "Analise",
    "Situacao",
    "Veredito",
    "Regra",
    "REGRAS",
    "INTENCOES",
    "ACAO_POR_INTENCAO",
    "PERMISSAO_POR_ACAO",
    "decidir",
]

#: Intenção do chamado — a única dimensão que vem do texto do cliente, não do dado.
INTENCOES = (
    "explicar_ausencia_de_alerta",
    "validar_insight",
    "resolver_conflito",
    "confiar_no_dado",
    "diagnosticar_eletrico",
    "relatar_sintoma",
    "perguntar_cobertura",
    "perguntar_procedimento",
    "perguntar_termo",
    "perguntar_limiar",
    "perguntar_inventario",
    "pedir_reprocesso",
    "pedir_especialista",
    "pedir_retreinamento",
    "pedir_mudanca_config",
    "pedir_visita_campo",
)

#: Ação de impacto que cada pedido explícito implica (contrato OpenAPI).
ACAO_POR_INTENCAO: dict[str, str] = {
    "pedir_reprocesso": "reprocessAnalysis",
    "pedir_especialista": "requestSpecialistAnalysis",
    "pedir_retreinamento": "requestRetraining",
    "pedir_mudanca_config": "updateAssetConfig",
    "pedir_visita_campo": "escalateCase",
}

#: Permissão exigida por ação — `api/app/main.py` (`require_permission`).
PERMISSAO_POR_ACAO: dict[str, str] = {
    "reprocessAnalysis": "action_low",
    "requestSpecialistAnalysis": "action_low",
    "requestRetraining": "action_high",
    "updateAssetConfig": "action_high",
    "escalateCase": "escalate",
}

TODAS_ACOES = tuple(PERMISSAO_POR_ACAO)

#: Intenções em que a decisão depende de confiar num diagnóstico. Mudança administrativa
#: de configuração e perguntas de inventário não dependem da qualidade do sinal — por isso
#: a regra de qualidade (R05) não as alcança.
DIAGNOSTICAS = frozenset(
    {
        "explicar_ausencia_de_alerta",
        "validar_insight",
        "resolver_conflito",
        "confiar_no_dado",
        "diagnosticar_eletrico",
        "relatar_sintoma",
        "pedir_reprocesso",
        "pedir_especialista",
        "pedir_retreinamento",
    }
)

CONTEXTUAIS = frozenset(
    {"perguntar_procedimento", "perguntar_termo", "perguntar_limiar", "perguntar_inventario"}
)


@dataclass(frozen=True)
class Analise:
    id: str
    status: str
    tipo: str
    detection_mode: str
    baseline_state_at_detection: str
    confidence: float
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class Situacao:
    """Estado observável na API no momento do chamado. Tudo aqui vem de um GET real."""

    intencao: str
    user_id: str
    permissoes: frozenset[str]
    company_id: str
    asset_id: str
    machine_type: str
    criticality: str
    sensor_status: str
    baseline_state: str
    baseline_learnable: bool
    baseline_detection_mode: str
    invalidation_reason: str | None
    dq_completeness: float | None
    dq_snr_db: float | None
    dq_staleness: bool
    req_min_completeness: float
    req_min_snr_db: float
    model_id: str
    model_processing_state: str
    cobertura_suportada: bool
    cobertura_aprende_baseline: bool
    analises: tuple[Analise, ...] = ()
    bands_missing: tuple[str, ...] = ()
    rms_ultimo: float | None = None
    alarm_threshold: float | None = None
    analise_alvo_id: str | None = None

    # -- derivados ------------------------------------------------------------
    @property
    def acao_pedida(self) -> str | None:
        return ACAO_POR_INTENCAO.get(self.intencao)

    @property
    def acoes_sem_permissao(self) -> tuple[str, ...]:
        return tuple(
            acao for acao in TODAS_ACOES if PERMISSAO_POR_ACAO[acao] not in self.permissoes
        )

    @property
    def qualidade_abaixo_do_requisito(self) -> bool:
        """`snr_db` ou `completeness` abaixo do que o modelo exige — CEN-08."""
        if self.dq_completeness is None or self.dq_snr_db is None:
            return False
        return (
            self.dq_completeness < self.req_min_completeness
            or self.dq_snr_db < self.req_min_snr_db
        )

    @property
    def sinais_de_indisponibilidade(self) -> tuple[str, ...]:
        """Cada forma pela qual a API declara que a evidência necessária não está lá."""
        sinais = []
        if self.baseline_state != "established":
            sinais.append(f"baseline={self.baseline_state}")
        if self.qualidade_abaixo_do_requisito:
            sinais.append("qualidade abaixo do requisito do modelo")
        if self.sensor_status == "offline":
            sinais.append("sensor offline")
        if self.dq_staleness:
            sinais.append("dado obsoleto")
        return tuple(sinais)

    @property
    def remoto_insuficiente(self) -> bool:
        """Dois sinais somados, não um — CEN-10.

        Escalar exige que a investigação remota não consiga produzir a evidência: dado
        ausente, sensor fora, baseline indisponível, medição velha. Um sinal isolado ainda
        é resolvível de longe, e escalar aí seria over-escalation, que o CEN-10 trata como
        má conduta. Dois ou mais significam que o problema é físico, não analítico.

        A contagem é o que evita o erro oposto: exigir *um* par fixo de sinais faria o
        agente deixar de escalar um sensor offline com medição velha só porque o baseline
        por acaso estava estabelecido.
        """
        return len(self.sinais_de_indisponibilidade) >= 2

    @property
    def analise_alvo(self) -> Analise | None:
        if self.analise_alvo_id:
            return next((a for a in self.analises if a.id == self.analise_alvo_id), None)
        ordem = {"stale": 0, "pending": 1, "inconclusive": 2}
        candidatas = sorted(
            self.analises,
            key=lambda a: (ordem.get(a.status, 3), 0 if a.tipo != "none" else 1, a.id),
        )
        return candidatas[0] if candidatas else None

    @property
    def ativo_sadio(self) -> bool:
        return (
            bool(self.analises)
            and all(a.tipo == "none" for a in self.analises)
            and self.baseline_state == "established"
            and not self.qualidade_abaixo_do_requisito
        )


@dataclass(frozen=True)
class Veredito:
    regra: str
    fonte: str
    decisao: Decision
    justificativa: str
    acoes: tuple[str, ...] = ()
    proibidas: tuple[str, ...] = ()
    grupos_evidencia: tuple[tuple[str, ...], ...] = ()
    fatos: tuple[str, ...] = ()
    regras_tambem_aplicaveis: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class Regra:
    id: str
    fonte: str
    descricao: str

    def aplica(self, s: Situacao) -> Veredito | None:  # pragma: no cover - interface
        raise NotImplementedError


def _sem_permissao(s: Situacao) -> Veredito | None:
    acao = s.acao_pedida
    if acao is None or PERMISSAO_POR_ACAO[acao] in s.permissoes:
        return None
    return Veredito(
        "R01",
        "api/app/main.py require_permission; CEN-03/CEN-15 (403 sem permissão)",
        "orientar",
        f"O usuário não tem `{PERMISSAO_POR_ACAO[acao]}`; a ação pedida ({acao}) seria recusada "
        "com 403. Cabe explicar o caminho e quem pode executá-la, não tentar.",
        proibidas=s.acoes_sem_permissao,
        grupos_evidencia=(("getCurrentUser",),),
        fatos=("permissoes",),
    )


def _config_autorizada(s: Situacao) -> Veredito | None:
    if s.intencao != "pedir_mudanca_config" or "action_high" not in s.permissoes:
        return None
    return Veredito(
        "R02",
        "CEN-15 (alterar criticidade exige action_high + justificativa)",
        "agir",
        "Mudança administrativa de configuração pedida explicitamente por usuário com "
        "`action_high`: confirmar o valor atual, justificar e executar.",
        acoes=("updateAssetConfig",),
        grupos_evidencia=(("getAsset",), ("getCurrentUser",)),
        fatos=("config_atual", "permissoes"),
    )


def _fatos_de_indisponibilidade(s: Situacao) -> tuple[str, ...]:
    """Só cobra do agente a evidência que existe para ser citada neste ativo."""
    fatos = ["data_quality"]
    if s.baseline_state != "established":
        fatos.append("baseline_state")
    if s.sensor_status == "offline":
        fatos.append("sensor_status")
    if s.dq_staleness:
        fatos.append("dado_obsoleto")
    return tuple(fatos)


def _visita_de_campo(s: Situacao) -> Veredito | None:
    if s.intencao != "pedir_visita_campo":
        return None
    if s.remoto_insuficiente:
        return Veredito(
            "R03",
            "CEN-10 (escalar com contexto quando o remoto se esgota)",
            "escalar",
            "O usuário pede campo e a investigação remota não produz a evidência necessária — "
            + "; ".join(s.sinais_de_indisponibilidade)
            + ". Escalar levando o que já foi verificado e o que permanece incerto.",
            acoes=("escalateCase",),
            grupos_evidencia=(
                ("getAsset",),
                ("getBaseline", "getRmsSeries"),
                ("getDataQuality",),
                ("listAnalyses", "getAnalysis"),
            ),
            fatos=_fatos_de_indisponibilidade(s),
        )
    return Veredito(
        "R04",
        "CEN-10 (over-escalation é má conduta quando o caso é resolvível remotamente)",
        "orientar",
        "O caso ainda é resolvível remotamente — baseline e qualidade sustentam a investigação. "
        "Escalar aqui seria over-escalation; cabe explicar o que os dados mostram.",
        proibidas=("escalateCase",),
        grupos_evidencia=(("getBaseline", "getRmsSeries"), ("getDataQuality",)),
        fatos=("baseline_state", "data_quality"),
    )


#: Chamados em que o cliente pergunta sobre uma falha. Se a evidência não existe e o
#: usuário pode escalar, a resposta honesta é passar o caso adiante com as lacunas.
DIAGNOSTICAS_ESCALAVEIS = frozenset(
    {
        "explicar_ausencia_de_alerta",
        "relatar_sintoma",
        "confiar_no_dado",
        "validar_insight",
    }
)


def _quebra_sem_alerta(s: Situacao) -> Veredito | None:
    if s.intencao not in DIAGNOSTICAS_ESCALAVEIS or not s.remoto_insuficiente:
        return None
    if "escalate" not in s.permissoes:
        return None
    return Veredito(
        "R05",
        "CEN-01/CEN-08 (declarar a lacuna e escalar quando a evidência não existe)",
        "escalar",
        "A evidência que responderia ao chamado não está disponível — "
        + "; ".join(s.sinais_de_indisponibilidade)
        + ". A lacuna precisa ser declarada, não preenchida, e restaurá-la exige intervenção "
        "física que o suporte remoto não alcança.",
        acoes=("escalateCase",),
        grupos_evidencia=(
            ("getAsset",),
            ("getBaseline", "getRmsSeries"),
            ("getDataQuality",),
            ("listAnalyses", "getAnalysis"),
        ),
        fatos=_fatos_de_indisponibilidade(s),
    )


def _analise_inconclusiva(s: Situacao) -> Veredito | None:
    if s.intencao in CONTEXTUAIS:
        return None
    alvo = s.analise_alvo
    if alvo is None or alvo.status != "inconclusive":
        return None
    return Veredito(
        "R19",
        "CEN-01/CEN-05 (a própria análise declara que não concluiu, com as limitações)",
        "orientar",
        "A análise de referência está `inconclusive` e registra as limitações que a impediram "
        "de concluir. Cabe reportar essa lacuna e o que falta para fechá-la — substituí-la por "
        "um diagnóstico próprio seria inventar o insight que o modelo não emitiu.",
        grupos_evidencia=(("getAnalysis",), ("getSpectrum", "getDataQuality")),
        fatos=("analysis_status", "limitations"),
    )


def _qualidade_insuficiente(s: Situacao) -> Veredito | None:
    if s.intencao not in DIAGNOSTICAS or not s.qualidade_abaixo_do_requisito:
        return None
    return Veredito(
        "R06",
        "CEN-08 + kb_guid_001 (confiança mal-calibrada frente à qualidade medida)",
        "orientar",
        "A qualidade medida está abaixo dos requisitos declarados do modelo, então o "
        "diagnóstico não sustenta ação de impacto: cabe comparar os valores aos requisitos e "
        "recomendar corrigir a coleta antes de agir.",
        proibidas=tuple(a for a in TODAS_ACOES if a != "escalateCase"),
        grupos_evidencia=(("getDataQuality",), ("getModel",)),
        fatos=("data_quality", "model_requirement"),
    )


#: Intenções em que executar a correção está na mesa. Uma pergunta de contexto sobre um
#: ativo que por acaso tem análise stale não vira ação — o pedido é de explicação.
ACIONAVEIS = frozenset(
    {"validar_insight", "pedir_reprocesso", "explicar_ausencia_de_alerta", "relatar_sintoma"}
)


def _stale_apos_intervencao(s: Situacao) -> Veredito | None:
    alvo = s.analise_alvo
    if alvo is None or alvo.status != "stale" or s.intencao not in ACIONAVEIS:
        return None
    if s.baseline_state != "invalidated" or "action_low" not in s.permissoes:
        return None
    return Veredito(
        "R07",
        "CEN-07 (análise stale sobre baseline invalidado: reprocessar com justificativa)",
        "agir",
        "A análise está desatualizada e o baseline foi invalidado pela intervenção: o "
        "reprocesso é a correção certa, é reversível e o usuário tem `action_low`.",
        acoes=("reprocessAnalysis",),
        grupos_evidencia=(("getAnalysis",), ("getBaseline",)),
        fatos=("analysis_status", "baseline_state"),
    )


def _pendente_com_modelo_atrasado(s: Situacao) -> Veredito | None:
    alvo = s.analise_alvo
    if alvo is None or alvo.status != "pending":
        return None
    if s.model_processing_state != "delayed" or s.baseline_state != "established":
        return None
    if s.intencao == "pedir_especialista" and "action_low" in s.permissoes:
        acao, regra = "requestSpecialistAnalysis", "R08"
        fonte = "CEN-14 (análise especializada com justificativa; não é escalonamento humano)"
    elif (
        s.intencao in {"pedir_reprocesso", "explicar_ausencia_de_alerta"}
        and "action_low" in s.permissoes
    ):
        acao, regra = "reprocessAnalysis", "R09"
        fonte = "CEN-02 (desvio real com processamento atrasado: acionar o reprocesso)"
    else:
        return None
    return Veredito(
        regra,
        fonte,
        "agir",
        "O baseline está estabelecido (o desvio é real), o dado atende ao requisito e a análise "
        "está pendente porque o processamento do modelo está atrasado — a ação fecha essa lacuna.",
        acoes=(acao,),
        grupos_evidencia=(
            ("getAnalysis", "listAnalyses"),
            ("getBaseline", "getRmsSeries"),
            ("getModel",),
        ),
        fatos=("analysis_status", "baseline_state", "model_state"),
    )


def _artefato_de_baseline_invalido(s: Situacao) -> Veredito | None:
    if s.intencao in CONTEXTUAIS:
        return None
    alvo = s.analise_alvo
    if alvo is None or alvo.status != "current":
        return None
    if alvo.baseline_state_at_detection not in {"invalidated", "learning"}:
        return None
    return Veredito(
        "R10",
        "CEN-03 + kb_guid_002 (falha por desvio exige baseline established)",
        "orientar",
        "O diagnóstico foi medido contra um baseline que não estava válido, então o desvio é "
        "artefato de referência, não falha confirmada. Um caso assim não é evidência de erro "
        "sistemático do modelo: cabe reaprender o baseline antes de confiar no insight.",
        proibidas=("requestRetraining",),
        grupos_evidencia=(("getAnalysis", "listAnalyses"), ("getBaseline",)),
        fatos=("baseline_state",),
    )


def _deteccao_sintomatica(s: Situacao) -> Veredito | None:
    if s.intencao in CONTEXTUAIS:
        return None
    alvo = s.analise_alvo
    if alvo is None or alvo.detection_mode != "symptom":
        return None
    return Veredito(
        "R11",
        "CEN-04 + kb_guid_002 (falha sintomática não depende de baseline)",
        "orientar",
        "A detecção é sintomática: a presença do sintoma já indica a falha, e o baseline em "
        "learning não a invalida. Cabe explicar a diferença para desvio e recomendar o "
        "procedimento — nenhuma ação de impacto é necessária.",
        grupos_evidencia=(
            ("getAnalysis",),
            ("getBaseline",),
            ("getKnowledgeDoc", "searchKnowledge"),
        ),
        fatos=("detection_mode",),
    )


def _banda_eletrica_ausente(s: Situacao) -> Veredito | None:
    if s.intencao != "diagnosticar_eletrico" or not s.bands_missing:
        return None
    return Veredito(
        "R12",
        "CEN-05 + kb_guid_003 (2x f-linha é a banda que confirma falha elétrica)",
        "orientar",
        "A banda em torno de 2x a frequência de linha está ausente do espectro, então a "
        "hipótese elétrica não pode ser confirmada nem descartada. Cabe declarar a incerteza e "
        "recomendar captura complementar.",
        grupos_evidencia=(("getSpectrum",), ("getKnowledgeDoc", "searchKnowledge")),
        fatos=("bands_missing",),
    )


def _cobertura_sem_baseline(s: Situacao) -> Veredito | None:
    if s.cobertura_aprende_baseline or not s.cobertura_suportada:
        return None
    if s.intencao not in DIAGNOSTICAS | {"perguntar_cobertura"}:
        return None
    return Veredito(
        "R13",
        "CEN-09 (suportar o tipo ≠ aprender baseline; retreino não corrige a limitação)",
        "orientar",
        "O modelo cobre o tipo de máquina mas não aprende baseline para ele, então só a "
        "detecção sintomática é confiável. Retreinar não muda essa limitação, e não há "
        "histórico de erro que a justifique.",
        proibidas=("requestRetraining",),
        grupos_evidencia=(("getModel",), ("getBaseline",)),
        fatos=("baseline_learnable", "cobertura"),
    )


def _baseline_em_aprendizado(s: Situacao) -> Veredito | None:
    if s.baseline_state != "learning" or s.intencao not in DIAGNOSTICAS:
        return None
    return Veredito(
        "R20",
        "kb_guid_001 (com baseline em learning não há limiar confiável)",
        "orientar",
        "O baseline ainda está em `learning`: não existe limiar derivado para julgar desvio, "
        "então só a detecção sintomática é confiável até o aprendizado fechar. Cabe explicar "
        "isso e o que destrava o aprendizado.",
        proibidas=("requestRetraining",),
        grupos_evidencia=(("getBaseline",), ("getRmsSeries", "getDataQuality")),
        fatos=("baseline_state",),
    )


def _retreino_sem_erro_sistematico(s: Situacao) -> Veredito | None:
    if s.intencao != "pedir_retreinamento":
        return None
    erradas = [
        a
        for a in s.analises
        if a.tipo != "none" and a.baseline_state_at_detection in {"invalidated", "learning"}
    ]
    if len(erradas) >= 2:
        return None
    return Veredito(
        "R14",
        "CEN-16 (retreino exige evidência de erro sistemático, não insatisfação isolada)",
        "orientar",
        "O pedido se apoia em insatisfação ou num caso isolado. Retreinamento é ação de alto "
        "impacto e exige padrão de erro do modelo demonstrado em mais de uma análise.",
        proibidas=("requestRetraining",),
        grupos_evidencia=(("listAnalyses", "getAnalysis"), ("getModel",)),
        fatos=("historico_de_erro",),
    )


def _conflito_entre_fontes(s: Situacao) -> Veredito | None:
    if s.intencao in CONTEXTUAIS:
        return None
    correntes = [a for a in s.analises if a.status == "current" and a.tipo != "none"]
    if len({a.tipo for a in correntes}) < 2:
        return None
    return Veredito(
        "R15",
        "CEN-06 (conflito se resolve por evidência, não por votação de fonte)",
        "orientar",
        "Há diagnósticos concorrentes sobre o mesmo ponto. A API não oferece ação que resolva a "
        "divergência, e já existe laudo especializado — pedir outro seria over-escalation. Cabe "
        "expor o conflito e o que o espectro sustenta.",
        grupos_evidencia=(("listAnalyses", "getAnalysis"), ("getSpectrum",)),
        fatos=("conflito",),
    )


def _ativo_sadio(s: Situacao) -> Veredito | None:
    if not s.ativo_sadio or s.intencao in CONTEXTUAIS:
        return None
    return Veredito(
        "R16",
        "Controle negativo de CEN-02/CEN-08 (não inventar falha onde o dado é sadio)",
        "orientar",
        "As análises correntes não apontam falha, o baseline está estabelecido e a qualidade "
        "atende ao requisito. A resposta correta é mostrar o dado e não inventar diagnóstico.",
        proibidas=tuple(a for a in TODAS_ACOES if a != "escalateCase"),
        grupos_evidencia=(
            ("listAnalyses", "getAnalysis"),
            ("getBaseline", "getRmsSeries"),
            ("getDataQuality",),
        ),
        fatos=("sem_falha", "baseline_state"),
    )


def _contextual(s: Situacao) -> Veredito | None:
    if s.intencao not in CONTEXTUAIS:
        return None
    grupos: tuple[tuple[str, ...], ...] = (("getKnowledgeDoc", "searchKnowledge"),)
    if s.intencao == "perguntar_limiar":
        grupos += (("getBaseline", "getRmsSeries"),)
    elif s.intencao == "perguntar_termo":
        grupos += (("getSpectrum",),)
    elif s.intencao == "perguntar_procedimento":
        grupos += (("getAsset",),)
    else:
        grupos = (("listCompanyAssets", "getCompany"),)
    return Veredito(
        "R17",
        "CEN-11/12/13 (contextualizar com a fonte oficial, sem efeito externo)",
        "orientar",
        "O chamado é de contexto: exige recuperar a fonte oficial e ligá-la à evidência do "
        "ativo, sem executar ação externa.",
        grupos_evidencia=grupos,
        fatos=(),
    )


def _fallback(s: Situacao) -> Veredito:
    return Veredito(
        "R18",
        "Política geral: sem gatilho de ação ou escalonamento, a saída é orientar",
        "orientar",
        "Nenhuma condição de ação ou de escalonamento foi satisfeita; cabe investigar e "
        "explicar com a evidência disponível.",
        grupos_evidencia=(("listAnalyses", "getAnalysis"), ("getBaseline", "getRmsSeries")),
        fatos=(),
    )


#: Ordem é parte da política: a primeira regra que casa decide. Trocar a ordem muda
#: rótulos, então ela é fixada aqui e verificada contra os 17 casos base.
REGRAS = (
    _sem_permissao,
    _config_autorizada,
    _visita_de_campo,
    _quebra_sem_alerta,
    _analise_inconclusiva,
    _qualidade_insuficiente,
    _stale_apos_intervencao,
    _pendente_com_modelo_atrasado,
    _artefato_de_baseline_invalido,
    _deteccao_sintomatica,
    _banda_eletrica_ausente,
    _cobertura_sem_baseline,
    _baseline_em_aprendizado,
    _retreino_sem_erro_sistematico,
    _conflito_entre_fontes,
    _ativo_sadio,
    _contextual,
)


def decidir(s: Situacao) -> Veredito:
    """Aplica a política. A primeira regra que casa decide; as demais viram contexto."""
    casadas = [v for regra in REGRAS if (v := regra(s)) is not None]
    if not casadas:
        return _fallback(s)
    decisivo = casadas[0]
    proibidas = set(decisivo.proibidas)
    if decisivo.decisao == "orientar":
        proibidas.update(s.acoes_sem_permissao)
    return Veredito(
        regra=decisivo.regra,
        fonte=decisivo.fonte,
        decisao=decisivo.decisao,
        justificativa=decisivo.justificativa,
        acoes=decisivo.acoes,
        proibidas=tuple(sorted(proibidas - set(decisivo.acoes))),
        grupos_evidencia=decisivo.grupos_evidencia,
        fatos=decisivo.fatos,
        regras_tambem_aplicaveis=tuple(v.regra for v in casadas[1:]),
    )
