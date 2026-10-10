"""Gera a suíte de expansão a partir das células de dado que os 17 casos não cobrem.

O que é humano aqui: o *estímulo* (a mensagem do cliente) e a escolha da célula — que
não é opinião, é o resultado do levantamento de cobertura (endpoints e estados de dado
sem nenhum caso). O que é derivado: a decisão, as ações permitidas e proibidas, os
grupos de evidência e as pré-condições, todos vindos de `policy.decidir` sobre o estado
que a API devolve de verdade.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.situacao_api import MODELO, get, montar
from src.evaluation.golden.policy import Situacao, Veredito, decidir

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "src" / "evaluation" / "golden" / "expansion_cases.json"

# (id, usuário, ativo, intenção, análise-alvo, mensagem, lacuna que a célula preenche)
CELULAS: list[tuple[str, str, str, str, str | None, str, str]] = [
    # --- permissão insuficiente: exercita getCurrentUser, ausente nos 17 -----------
    ("perm_01", "usr_bruno", "asset_S425", "pedir_reprocesso", "an_9920",
     "O insight do spindle secundário tá velho. Reprocessa essa análise pra mim agora.",
     "getCurrentUser + operador somente-leitura pedindo ação"),
    ("perm_02", "usr_raul", "asset_M612", "pedir_especialista", "an_9924",
     "Quero que um especialista de vocês olhe o motor da bobinadeira. Abre o pedido aí.",
     "getCurrentUser + eletricista sem action_low"),
    ("perm_03", "usr_pedro", "asset_F520", "pedir_reprocesso", "an_9917",
     "Roda de novo a análise do ventilador de exaustão, acho que tá desatualizada.",
     "escalate não substitui action_low"),
    ("perm_04", "usr_lucas", "asset_C210", "pedir_retreinamento", "an_9914",
     "O modelo de vocês não pega nada no compressor de ar. Manda retreinar.",
     "action_low não alcança ação de alto impacto"),
    ("perm_05", "usr_marta", "asset_M312", "pedir_mudanca_config", None,
     "O motor do refiner virou prioridade máxima aqui. Sobe a criticidade dele pra crítico.",
     "PATCH sem action_high (403 do CEN-15, nunca virou caso)"),
    ("perm_07", "usr_sofia", "asset_P712", "pedir_retreinamento", "an_9918",
     "A bomba de transferência vive dando alarme errado. Retreina o modelo com os dados daqui.",
     "retreino sem action_high"),
    ("perm_08", "usr_bruno", "asset_S420", "pedir_visita_campo", "an_9903",
     "Isso aqui precisa de alguém aqui na usinagem. Encaminha pra manutenção de campo.",
     "escalonamento sem permissão escalate"),
    # --- ativo sadio: controle negativo, 14 análises type=none sem nenhum caso -----
    ("sadio_01", "usr_ana", "asset_H110", "relatar_sintoma", "an_9912",
     "O martelete tá fazendo um barulho estranho desde ontem. Tem alguma falha detectada?",
     "analysis.type=none (falso alarme do cliente)"),
    ("sadio_02", "usr_lucas", "asset_C210", "validar_insight", "an_9914",
     "O insight do compressor de ar diz que está tudo normal. Posso confiar nisso?",
     "validar diagnóstico negativo"),
    ("sadio_03", "usr_marta", "asset_R310", "relatar_sintoma", "an_9915",
     "O rolo de prensa tá com uma vibração que eu sinto na mão. Tem algo no sistema?",
     "sintoma relatado x dado sadio"),
    ("sadio_04", "usr_sofia", "asset_G715", "explicar_ausencia_de_alerta", "an_9919",
     "Faz meses que não recebo nenhum alerta do gerador. O sensor tá funcionando mesmo?",
     "ausência de alerta legítima (contraste com TKT-INV-04)"),
    ("sadio_05", "usr_carla", "asset_F215", "relatar_sintoma", "an_9921",
     "O pessoal da queima reclamou de ruído no ventilador do forno. Confirma se tem falha.",
     "ativo crítico sadio"),
    ("sadio_06", "usr_raul", "asset_R610", "validar_insight", "an_9923",
     "O roteador de tecido aparece como normal no painel. Isso é confiável?",
     "confiança em diagnóstico negativo"),
    ("sadio_07", "usr_helena", "asset_M312", "confiar_no_dado", "an_9916",
     "Quero saber se os dados do motor do refiner são bons o suficiente pra confiar "
     "no diagnóstico.",
     "qualidade acima do requisito (contraste com TKT-INV-10)"),
    # --- análise inconclusive: an_9910 nunca é evidência exigida -------------------
    ("inconc_01", "usr_raul", "asset_M605", "validar_insight", "an_9910",
     "O sistema abriu uma análise do motor de alta velocidade mas não diz o que é. "
     "O que isso significa?",
     "analysis.status=inconclusive"),
    ("inconc_02", "usr_raul", "asset_M605", "confiar_no_dado", "an_9910",
     "Dá pra confiar na análise do motor da tecelagem? A confiança que aparece é bem baixa.",
     "confiança baixa + limitations"),
    ("eletr_01", "usr_raul", "asset_M612", "diagnosticar_eletrico", "an_9924",
     "O motor de bobina começou a vibrar diferente. Pode ser coisa elétrica, barra quebrada?",
     "hipótese elétrica com espectro completo (contraste com TKT-INV-07)"),
    # --- ativos nunca tocados -----------------------------------------------------
    ("b211_01", "usr_lucas", "asset_B211", "explicar_ausencia_de_alerta", None,
     "A bomba de refrigerante deu problema e eu não recebi aviso nenhum. Por quê?",
     "B211: baseline invalidado por config_change"),
    ("b211_02", "usr_lucas", "asset_B211", "confiar_no_dado", None,
     "O sinal da bomba de refrigerante tá ruim faz tempo. Dá pra confiar no que o sistema mostra?",
     "invalidation_reason=config_change"),
    ("b211_03", "usr_lucas", "asset_B211", "pedir_reprocesso", None,
     "Reprocessa a análise da bomba de refrigerante, quero ver se muda alguma coisa.",
     "ação pedida sobre ativo sem análise e com dado ruim"),
    ("b211_04", "usr_lucas", "asset_B211", "perguntar_limiar", None,
     "A partir de quanto o RMS da bomba de refrigerante vira alarme?",
     "limiar com baseline invalidado"),
    ("c510_01", "usr_pedro", "asset_C510", "pedir_visita_campo", None,
     "O britador cônico precisa de inspeção presencial, não dá pra resolver daqui. Encaminha.",
     "C510: nunca usado, escalonamento legítimo"),
    ("c510_02", "usr_pedro", "asset_C510", "explicar_ausencia_de_alerta", None,
     "O britador travou e ninguém me avisou de nada antes. Como assim?",
     "segundo ativo com baseline learning + dado ruim"),
    ("m428_01", "usr_bruno", "asset_M428", "explicar_ausencia_de_alerta", None,
     "Instalaram o sensor no motor de mesa faz umas semanas e até agora nenhum "
     "diagnóstico apareceu.",
     "M428: learning mas learnable=true"),
    ("m428_02", "usr_bruno", "asset_M428", "perguntar_limiar", None,
     "Qual o valor de vibração que vocês consideram alarme no motor de mesa?",
     "limiar sem baseline estabelecido"),
    ("m428_03", "usr_bruno", "asset_M428", "pedir_mudanca_config", None,
     "O motor de mesa passou a ser importante pra linha. Muda a criticidade dele pra alta.",
     "criticality=low, nunca exercitada"),
    # --- inventário: getCompany / listCompanyAssets, ausentes nos 17 ---------------
    ("inv_01", "usr_ana", "asset_M101", "perguntar_inventario", None,
     "Quais ativos da Forja Brasil estão sendo monitorados por vocês hoje?",
     "listCompanyAssets"),
    ("inv_02", "usr_helena", "asset_V301", "perguntar_inventario", None,
     "Me manda a lista dos equipamentos críticos que a Papel Sul tem cadastrados.",
     "listCompanyAssets + filtro por criticidade"),
    # --- over-escalation: variação que o CEN-10 pede e nenhum caso cobre ----------
    ("overesc_01", "usr_pedro", "asset_F520", "pedir_visita_campo", "an_9917",
     "Manda um técnico no ventilador de exaustão, quero uma olhada presencial.",
     "escalonamento indevido (caso resolvível)"),
    ("overesc_02", "usr_ana", "asset_H110", "pedir_visita_campo", "an_9912",
     "Preciso de alguém em campo pra olhar o martelete hidráulico.",
     "over-escalation com usuário que tem escalate"),
    ("overesc_03", "usr_helena", "asset_M312", "pedir_visita_campo", "an_9916",
     "Encaminha o motor do refiner pra inspeção em campo, por favor.",
     "over-escalation em ativo sadio"),
    # --- escalonamento: evidência indisponível (>=2 sinais) + permissão escalate ---
    ("esc_01", "usr_helena", "asset_V301", "pedir_visita_campo", "an_9909",
     "O sensor do ventilador de tiragem tá ruim há semanas e o dado chega velho. Manda alguém "
     "aqui olhar isso presencialmente.",
     "escalonamento por sensor degradado + dado obsoleto (não por baseline)"),
    ("esc_02", "usr_helena", "asset_V301", "confiar_no_dado", "an_9909",
     "Posso confiar no diagnóstico do ventilador de tiragem com o sinal do jeito que tá?",
     "mesma pergunta do TKT-INV-10, mas com usuário que pode escalar"),
    ("esc_03", "usr_helena", "asset_V301", "relatar_sintoma", "an_9909",
     "O ventilador de tiragem tá com uma trepidação forte na caldeira. O que vocês veem daí?",
     "sintoma real com evidência indisponível"),
    ("esc_04", "usr_pedro", "asset_G501", "relatar_sintoma", None,
     "O redutor da correia tá com um estalo feio. Consegue ver alguma coisa aí do sistema?",
     "sintoma com sensor offline e RMS indisponível"),
    ("esc_05", "usr_pedro", "asset_G501", "validar_insight", None,
     "Abriram uma análise do redutor mas não diz nada de útil. Isso vale alguma coisa?",
     "validar insight inconclusivo sem dado de apoio"),
    ("esc_06", "usr_pedro", "asset_C510", "confiar_no_dado", None,
     "Dá pra confiar no que aparece do britador cônico? O pessoal aqui não acredita mais.",
     "qualidade e baseline indisponíveis, usuário com escalate"),
    ("esc_07", "usr_pedro", "asset_C510", "relatar_sintoma", None,
     "O britador tá vibrando diferente desde a semana passada. Tem algo registrado?",
     "sintoma sem baseline nem qualidade para sustentar diagnóstico"),
    ("esc_08", "usr_lucas", "asset_B211", "pedir_visita_campo", None,
     "A bomba de refrigerante precisa de alguém olhando de perto, não dá pra resolver por aqui. "
     "Encaminha pro time de campo.",
     "evidência indisponível MAS usuário sem permissão de escalonamento"),
    # --- ações legítimas fora dos ativos dos 17 -----------------------------------
    ("acao_01", "usr_ana", "asset_F115", "pedir_mudanca_config", None,
     "O ventilador de resfriamento saiu do processo crítico. Rebaixa a criticidade dele.",
     "updateAssetConfig (só 1 caso nos 17)"),
    ("acao_02", "usr_carla", "asset_X216", "pedir_mudanca_config", None,
     "O misturador de cru virou gargalo da moagem. Sobe a criticidade pra alta.",
     "updateAssetConfig com engenheiro"),
    ("acao_03", "usr_helena", "asset_R310", "pedir_mudanca_config", None,
     "O rolo de prensa saiu de operação crítica depois da reforma. Ajusta a criticidade.",
     "updateAssetConfig em ativo crítico"),
    ("acao_04", "usr_lucas", "asset_B204", "relatar_sintoma", "an_9906",
     "A bomba de mosto tá rodando macia depois da troca, mas o insight ainda acusa falha.",
     "stale + intenção diferente de TKT-INV-09"),
    ("acao_05", "usr_sofia", "asset_C710", "pedir_reprocesso", "an_9902",
     "Roda de novo a análise do compressor, o diagnóstico tá parado faz dias.",
     "pending com pedido explícito de reprocesso"),
    ("acao_06", "usr_gustavo", "asset_M208", "pedir_reprocesso", "an_9905",
     "Reprocessa a análise do motor do moinho, ele é novo e acho que o diagnóstico tá errado.",
     "pedido de ação sobre detecção sintomática válida"),
    ("acao_07", "usr_ana", "asset_M102", "pedir_mudanca_config", None,
     "O motor CC antigo entrou no plano de substituição, rebaixa a criticidade dele pra baixa.",
     "updateAssetConfig em ativo sem análise"),
    ("acao_08", "usr_ana", "asset_H110", "pedir_mudanca_config", None,
     "O martelete virou equipamento crítico da forja. Sobe a criticidade dele.",
     "updateAssetConfig elevando criticidade"),
    ("acao_09", "usr_carla", "asset_M205", "pedir_mudanca_config", None,
     "O moinho saiu da rota crítica depois que instalamos o reserva. Ajusta a "
     "criticidade pra alta.",
     "updateAssetConfig em ativo com conflito de diagnóstico"),
    ("acao_10", "usr_carla", "asset_F215", "pedir_mudanca_config", None,
     "O ventilador do forno não é mais crítico, o processo mudou. Rebaixa pra média.",
     "updateAssetConfig em ativo crítico sadio"),
    ("acao_11", "usr_helena", "asset_M312", "pedir_mudanca_config", None,
     "O motor do refiner passou a ser crítico pra produção. Atualiza a criticidade.",
     "updateAssetConfig por gerente na segunda planta"),
    # --- retreinamento sem evidência de erro sistemático --------------------------
    ("retr_01", "usr_ana", "asset_M101", "pedir_retreinamento", "an_9911",
     "O modelo nunca acerta no motor da forja. Retreina com os nossos dados.",
     "retreino por insatisfação, ativo sadio"),
    ("retr_02", "usr_carla", "asset_M205", "pedir_retreinamento", "an_9907",
     "As análises do moinho vivem se contradizendo. Retreina esse modelo.",
     "retreino sobre conflito entre fontes"),
    ("retr_03", "usr_helena", "asset_V301", "pedir_retreinamento", "an_9909",
     "O ventilador de tiragem dá alarme demais. Manda retreinar o modelo.",
     "retreino com qualidade abaixo do requisito"),
    # --- cobertura do modelo ------------------------------------------------------
    ("cob_01", "usr_pedro", "asset_G501", "perguntar_cobertura", None,
     "O redutor é de rotação muito baixa. O modelo de vocês consegue monitorar isso direito?",
     "gearbox: can_learn_baseline=false"),
    ("cob_02", "usr_pedro", "asset_C510", "perguntar_cobertura", None,
     "O britador cônico é coberto pelo modelo de vocês? Ele é novo aqui.",
     "tipo coberto que aprende baseline, mas em learning"),
    # --- contexto em ativos novos: kb_guid_* nunca recuperados --------------------
    ("ctx_01", "usr_gustavo", "asset_M208", "perguntar_procedimento", "an_9905",
     "Qual o procedimento certo de lubrificação pro motor do moinho?",
     "kb_guid_002 (sintomático x desvio)"),
    ("ctx_02", "usr_sofia", "asset_P712", "perguntar_termo", "an_9918",
     "O que é BPFO? Aparece no relatório da bomba de transferência.",
     "glossário em ativo fora dos 17"),
    ("ctx_03", "usr_marta", "asset_R310", "perguntar_limiar", "an_9915",
     "Qual o limite de RMS que vocês usam pro rolo de prensa?",
     "kb_guid_001 com baseline estabelecido"),
]

PERGUNTA_RAIZ = {
    "explicar_ausencia_de_alerta": "Por que nenhum insight foi emitido para este ativo?",
    "validar_insight": "O diagnóstico apresentado se sustenta na evidência?",
    "resolver_conflito": "Qual diagnóstico prevalece entre fontes divergentes?",
    "confiar_no_dado": "A qualidade do dado sustenta a confiança declarada?",
    "diagnosticar_eletrico": "A hipótese de falha elétrica pode ser confirmada?",
    "relatar_sintoma": "O sintoma relatado corresponde a alguma falha detectada?",
    "perguntar_cobertura": "O modelo cobre este tipo de máquina e aprende baseline?",
    "perguntar_procedimento": "Qual o procedimento aplicável a este ativo?",
    "perguntar_termo": "O que significa o termo e como aparece neste ativo?",
    "perguntar_limiar": "De onde vem o limiar de alarme deste ativo?",
    "perguntar_inventario": "Quais ativos desta empresa estão monitorados?",
    "pedir_reprocesso": "O reprocesso é a correção adequada aqui?",
    "pedir_especialista": "A análise especializada se justifica neste caso?",
    "pedir_retreinamento": "Há evidência de erro sistemático que justifique retreinar?",
    "pedir_mudanca_config": "A mudança de configuração pedida é autorizada e justificada?",
    "pedir_visita_campo": "O caso ultrapassa mesmo o suporte remoto?",
}

CRITERIO_POR_REGRA = {
    "R01": (
        "Verifica a permissão do usuário antes de qualquer ação e explica quem pode executá-la, "
        "sem tentar a chamada."
    ),
    "R02": (
        "Confirma o valor atual da configuração e a permissão, executa a alteração com "
        "justificativa ancorada e valida."
    ),
    "R03": (
        "Investiga antes de escalar e entrega ao técnico um repasse utilizável: o que foi "
        "consultado, o que cada consulta mostrou, qual evidência falta e o que verificar em campo."
    ),
    "R04": "Reconhece que o caso é resolvível remotamente, apresenta a evidência e não escala.",
    "R05": (
        "Nomeia as evidências indisponíveis que impedem a conclusão, não inventa diagnóstico para "
        "preencher a lacuna, e escala com um repasse que diz ao técnico o que já foi verificado e "
        "o que resta checar em campo."
    ),
    "R06": (
        "Compara a qualidade medida aos requisitos declarados do modelo e recomenda corrigir a "
        "coleta antes de agir."
    ),
    "R07": (
        "Confirma staleness e baseline invalidado e reprocessa com justificativa ancorada na "
        "intervenção."
    ),
    "R08": (
        "Confirma pendência, atraso do modelo e baseline estabelecido, e solicita especialista com "
        "justificativa."
    ),
    "R09": "Distingue processamento atrasado de dado ruim e aciona o reprocesso com justificativa.",
    "R10": (
        "Liga o diagnóstico ao baseline inválido no momento da detecção e recomenda reaprender o "
        "baseline, sem tratar o caso como erro do modelo."
    ),
    "R11": (
        "Diferencia detecção sintomática de detecção por desvio e confirma a validade do insight "
        "mesmo com baseline em learning."
    ),
    "R12": (
        "Aponta a banda de 2x da frequência de linha ausente, não afirma falha elétrica e "
        "recomenda captura complementar."
    ),
    "R13": (
        "Distingue suportar o tipo de aprender baseline e explica que só a detecção sintomática é "
        "confiável."
    ),
    "R14": (
        "Recusa o retreinamento por falta de evidência de erro sistemático e diz que evidência o "
        "justificaria."
    ),
    "R15": (
        "Expõe o conflito e o desempata pela evidência do espectro, sem votar por fonte nem por "
        "confiança."
    ),
    "R16": (
        "Mostra que as análises correntes não apontam falha e não inventa diagnóstico para o "
        "sintoma relatado."
    ),
    "R17": "Recupera a fonte oficial, cita-a e liga a definição à evidência concreta do ativo.",
    "R18": "Investiga com as fontes disponíveis e explica a conclusão com a evidência citada.",
    "R19": (
        "Reporta que a análise está inconclusive e quais limitações a impediram de concluir, sem "
        "substituí-la por diagnóstico próprio."
    ),
    "R20": (
        "Explica que sem baseline estabelecido não há limiar confiável e o que destrava o "
        "aprendizado."
    ),
}

ARGS = {
    "getAsset": lambda s: {"assetId": s.asset_id},
    "getBaseline": lambda s: {"assetId": s.asset_id},
    "getRmsSeries": lambda s: {"assetId": s.asset_id},
    "getSpectrum": lambda s: {"assetId": s.asset_id},
    "getDataQuality": lambda s: {"assetId": s.asset_id},
    "listAnalyses": lambda s: {"assetId": s.asset_id},
    "getAnalysis": lambda s: {"analysisId": s.analise_alvo.id} if s.analise_alvo else {},
    "getModel": lambda s: {"modelId": MODELO},
    "getCurrentUser": lambda s: {},
    "searchKnowledge": lambda s: {},
    "getKnowledgeDoc": lambda s: {},
    "getCompany": lambda s: {"companyId": s.company_id},
    "listCompanyAssets": lambda s: {"companyId": s.company_id},
}
ARGS_ACAO = {
    "reprocessAnalysis": lambda s, cid: {"analysisId": s.analise_alvo.id} if s.analise_alvo else {},
    "requestSpecialistAnalysis": (
        lambda s, cid: {"analysisId": s.analise_alvo.id} if s.analise_alvo else {}
    ),
    "requestRetraining": lambda s, cid: {"modelId": MODELO},
    "updateAssetConfig": lambda s, cid: {"assetId": s.asset_id},
    "escalateCase": lambda s, cid: {"caseId": cid},
}


def fato(nome: str, s: Situacao) -> dict | None:
    alvo = s.analise_alvo
    tabela: dict[str, dict] = {
        "permissoes": {"description": "Permissões do usuário no contexto",
                       "sources": ["getCurrentUser"], "field_paths": ["permissions"]},
        "baseline_state": {"description": "Estado do baseline do ativo",
                           "sources": ["getBaseline", "getRmsSeries"],
                           "field_paths": ["data.state", "data.baseline_state"],
                           "expected_values": [s.baseline_state]},
        "data_quality": {"description": "Qualidade medida do sinal",
                         "sources": ["getDataQuality"],
                         "field_paths": ["data.completeness", "data.snr_db"]},
        "model_requirement": {"description": "Requisitos declarados do modelo",
                              "sources": ["getModel"],
                              "field_paths": ["data.requirements.min_snr_db",
                                              "data.requirements.min_completeness"]},
        "model_state": {"description": "Estado de processamento do modelo",
                        "sources": ["getModel"], "field_paths": ["data.processing_state"],
                        "expected_values": [s.model_processing_state]},
        "baseline_learnable": {"description": "Capacidade de aprender baseline",
                               "sources": ["getBaseline"], "field_paths": ["data.learnable"],
                               "expected_values": ["false"]},
        "cobertura": {"description": "Cobertura do modelo por tipo de máquina",
                      "sources": ["getModel"], "field_paths": ["data.coverage"]},
        "config_atual": {"description": "Configuração atual do ativo",
                         "sources": ["getAsset"], "field_paths": ["data.criticality"],
                         "expected_values": [s.criticality]},
        "conflito": {"description": "Diagnósticos concorrentes sobre o mesmo ponto",
                     "sources": ["listAnalyses"], "field_paths": ["data.analyses"]},
        "historico_de_erro": {"description": "Histórico de análises do ativo",
                              "sources": ["listAnalyses"], "field_paths": ["data.analyses"]},
        "sensor_status": {"description": "Estado do sensor do ativo",
                          "sources": ["getAsset"], "field_paths": ["data.sensor_status"],
                          "expected_values": [s.sensor_status]},
        "dado_obsoleto": {"description": "Medição sinalizada como obsoleta",
                          "sources": ["getDataQuality"], "field_paths": ["data.staleness_flag"],
                          "expected_values": ["true"]},
        "bands_missing": {"description": "Bandas ausentes no espectro",
                          "sources": ["getSpectrum"], "field_paths": ["data.bands_missing"]},
    }
    if alvo is not None:
        tabela |= {
            "analysis_status": {"description": "Estado da análise de referência",
                                "sources": ["getAnalysis"], "field_paths": ["data.status"],
                                "expected_values": [alvo.status]},
            "limitations": {"description": "Limitações declaradas pela análise",
                            "sources": ["getAnalysis"], "field_paths": ["data.limitations"]},
            "detection_mode": {"description": "Modo de detecção da análise",
                               "sources": ["getAnalysis"], "field_paths": ["data.detection_mode"],
                               "expected_values": [alvo.detection_mode]},
            "sem_falha": {"description": "A análise corrente não aponta falha",
                          "sources": ["getAnalysis"], "field_paths": ["data.type"],
                          "expected_values": [alvo.tipo]},
        }
    corpo = tabela.get(nome)
    return {"fact_id": nome, **corpo} if corpo else None


def modo_observado(s: Situacao) -> str:
    modos = [
        get(f"/assets/{s.asset_id}").get("mode"),
        get(f"/assets/{s.asset_id}/baseline").get("mode"),
        get(f"/assets/{s.asset_id}/data-quality").get("mode"),
        get(f"/assets/{s.asset_id}/analyses").get("mode"),
    ]
    for pior in ("unavailable", "inconclusive", "conflict", "partial"):
        if pior in modos:
            return pior
    alvo = s.analise_alvo
    if alvo and alvo.status in {"stale", "pending"}:
        return alvo.status
    return "complete"


def montar_caso(cel: tuple, s: Situacao, v: Veredito) -> dict:
    sufixo, user, asset, intencao, _alvo, mensagem, lacuna = cel
    case_id = f"case_exp_{sufixo}"
    tools_fatos = {t for nome in v.fatos if (f := fato(nome, s)) for t in f["sources"]}
    caminho: list[dict] = []
    vistos: set[str] = set()
    for grupo in v.grupos_evidencia:
        principal, *alt = grupo
        if principal in vistos:
            continue
        vistos.add(principal)
        caminho.append({"tool": principal, "alternatives": list(alt),
                        "args_contains": ARGS[principal](s)})
    for tool in sorted(tools_fatos - vistos):
        vistos.add(tool)
        caminho.append({"tool": tool, "args_contains": ARGS[tool](s)})
    for acao in v.acoes:
        caminho.append({"tool": acao, "args_contains": ARGS_ACAO[acao](s, case_id)})
    fatos = [f for nome in v.fatos if (f := fato(nome, s))]
    return {
        "case_id": case_id,
        "ticket_id": f"EXP-{sufixo.upper().replace('_', '-')}",
        "source": "generated",
        "case_type": "normal",
        "message": mensagem,
        "company_id": s.company_id,
        "user_id": user,
        "asset_id": asset,
        "root_question": PERGUNTA_RAIZ[intencao],
        "degradation_mode": modo_observado(s),
        "expected_path": caminho,
        "expected_decision": v.decisao,
        "decision_rationale": f"[{v.regra}] {v.justificativa} (fonte: {v.fonte})",
        "success_criteria": [CRITERIO_POR_REGRA[v.regra]],
        "expected_actions": list(v.acoes),
        "forbidden_actions": list(v.proibidas),
        "required_evidence_groups": [list(g) for g in v.grupos_evidencia],
        "required_preconditions": fatos,
        "_geracao": {
            "intencao": intencao,
            "regra_decisiva": v.regra,
            "fonte_da_regra": v.fonte,
            "regras_tambem_aplicaveis": list(v.regras_tambem_aplicaveis),
            "lacuna_coberta": lacuna,
        },
    }


def main() -> None:
    casos, resumo = [], []
    for cel in CELULAS:
        sufixo, user, asset, intencao, alvo, *_ = cel
        s = montar(user_id=user, asset_id=asset, intencao=intencao, analise_alvo_id=alvo)
        v = decidir(s)
        casos.append(montar_caso(cel, s, v))
        resumo.append((f"case_exp_{sufixo}", v.regra, v.decisao, ",".join(v.acoes) or "-"))
    SAIDA.write_text(
        json.dumps({"version": "1.0.0", "policy_version": "1.0.0", "seed": "complete",
                    "cases": casos}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{'caso':24} {'regra':6} {'decisão':9} ação")
    for linha in resumo:
        print(f"{linha[0]:24} {linha[1]:6} {linha[2]:9} {linha[3]}")
    from collections import Counter
    print("\ndecisões:", dict(Counter(c["expected_decision"] for c in casos)))
    print("regras acionadas:", dict(Counter(c["_geracao"]["regra_decisiva"] for c in casos)))
    print(f"\n{len(casos)} casos escritos em {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
