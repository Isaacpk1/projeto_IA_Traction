# 02 — Personas e User Stories

> **Numeração de requisitos.** As referências a RF/RNF neste documento seguem
> [`03-requisitos.md`](./03-requisitos.md); a matriz autoritativa de cruzamento é
> [`06-matriz-rastreabilidade.md`](./06-matriz-rastreabilidade.md).

> As personas **não são inventadas**. Elas derivam dos sete perfis (`role`) e dos quatro níveis de
> permissão definidos no contrato da API (`docs/api-contract.openapi.yaml`, schema `User`), e dos
> usuários reais que aparecem nos 17 chamados de `agent-input/cases.json`.

---

## 1. Modelo de perfis e permissões

O contrato define sete perfis e quatro permissões atômicas:

**Perfis:** `operator` · `mechanic` · `reliability_analyst` · `maintenance_manager` ·
`coordinator` · `engineer` · `electrician`

**Permissões:** `read` · `action_low` · `action_high` · `escalate`

| Permissão | Habilita |
| :--- | :--- |
| `read` | Todas as consultas — ativos, análises, sinais, baseline, qualidade, modelos, conhecimento |
| `action_low` | Reprocessar análise, solicitar análise especializada |
| `action_high` | Alterar configuração técnica do ativo, solicitar retreinamento de modelo |
| `escalate` | Encaminhar o caso para análise humana |

> **Consequência de projeto:** a permissão é atributo do **usuário**, não do agente. O agente atua
> em nome do usuário e herda suas restrições. Ver RF13 e RNF05.

---

## 2. Personas

### P01 — Operador de Máquina

| | |
| :--- | :--- |
| **Perfil API** | `operator` |
| **Permissões** | `read` |
| **Representante** | Bruno (Acme Auto Peças) — TKT-INV-06 |
| **Contexto** | Opera o equipamento no chão de fábrica. Convive com a máquina todo dia. |

**Necessidade.** Entender, em linguagem acessível, o que um alerta significa e se deve se preocupar.
Não domina vocabulário de análise de vibração.

**Frustração.** Recebe insights com jargão (`BPFO`, `1×`, `detection_mode`) sem tradução. Quando sua
percepção sensorial contradiz o sistema — *"a máquina tá rodando lisa"* — não tem como investigar.

**Do agente, espera.** Explicação sem jargão, ancorada em evidência, e honestidade quando o sistema
pode estar errado.

---

### P02 — Mecânico de Manutenção

| | |
| :--- | :--- |
| **Perfil API** | `mechanic` |
| **Permissões** | `read`, `action_low` |
| **Representantes** | Lucas (Cervejaria Aurora) — TKT-INV-09, TKT-EXE-12, TKT-CTX-02 · Gustavo (Cimento Vale) — TKT-INV-11b |
| **Contexto** | Executa a intervenção física. Já trocou o rolamento; agora quer o sistema refletir isso. |

**Necessidade.** Procedimentos aplicáveis ao ativo e à falha, e reprocessar análises após a
intervenção para confirmar a melhora.

**Frustração.** Depois de consertar, o insight antigo continua ativo — parece que o trabalho não foi
reconhecido. Não sabe que a análise está `stale` e que o baseline foi invalidado pela própria
intervenção.

**Do agente, espera.** Confirmação de que a intervenção foi registrada, explicação do ciclo de
reaprendizado do baseline, e execução do reprocesso.

---

### P03 — Analista de Confiabilidade

| | |
| :--- | :--- |
| **Perfil API** | `reliability_analyst` |
| **Permissões** | `read`, `action_low` |
| **Representantes** | Sofia (Petro Delta) — TKT-INV-05 · Marta (Papel Sul) — TKT-INV-10, TKT-CTX-03 |
| **Contexto** | Acompanha tendências e questiona o sistema tecnicamente. Persona mais exigente. |

**Necessidade.** Entender *por que* o sistema se comportou de determinada forma — por que um insight
não foi emitido apesar de tendência clara, ou como pesar qualidade de sinal contra confiança
declarada.

**Frustração.** Respostas genéricas. Se perguntar de onde vem o limiar de alarme e ouvir "norma
ISO", perde a confiança na ferramenta.

**Do agente, espera.** Rigor técnico, referência ao dado específico do ativo, e distinção entre "não
detectou" e "não conseguiu processar".

---

### P04 — Engenheiro de Manutenção

| | |
| :--- | :--- |
| **Perfil API** | `engineer` |
| **Permissões** | `read`, `action_low`, `action_high` |
| **Representante** | Carla (Cimento Vale / Acme) — TKT-INV-08, TKT-EXE-15 |
| **Contexto** | Decide tecnicamente. Media conflitos entre diagnóstico automático e laudo de especialista. |

**Necessidade.** Reconciliar fontes divergentes e agir sobre a causa raiz — inclusive solicitar
retreinamento quando o modelo erra sistematicamente.

**Frustração.** Duas fontes com confianças diferentes e nenhum critério de desempate. Precisa da
evidência física — o espectro — não da opinião de cada fonte.

**Do agente, espera.** Comparação estruturada das fontes conflitantes, evidência espectral como
critério de desempate, e reconhecimento explícito quando não há base para decidir.

---

### P05 — Eletricista

| | |
| :--- | :--- |
| **Perfil API** | `electrician` |
| **Permissões** | `read` |
| **Representante** | Raul (Texfil) — TKT-INV-07 |
| **Contexto** | Especialista elétrico. Precisa saber se o problema é do domínio dele. |

**Necessidade.** Distinguir falha de origem elétrica (2× frequência de linha no espectro) de falha
mecânica, para saber se deve atuar ou acionar a mecânica.

**Frustração.** Ser acionado para problema mecânico, ou o contrário. Custa deslocamento e tempo.

**Do agente, espera.** Análise espectral com foco na assinatura elétrica e, quando o espectro vem
parcial, declaração explícita da incerteza em vez de um palpite.

---

### P06 — Coordenador de Manutenção

| | |
| :--- | :--- |
| **Perfil API** | `coordinator` |
| **Permissões** | `read`, `action_low`, `escalate` |
| **Representante** | Pedro (Mineração Andes) — TKT-INV-04, TKT-EXE-16 |
| **Contexto** | Responde pela disponibilidade do parque. Quando algo quebra sem aviso, ele responde por isso. |

**Necessidade.** Explicação de falha de cobertura — por que o sistema não avisou — e capacidade de
escalar quando o caso ultrapassa o suporte remoto.

**Frustração.** Ativo quebrou sem alerta. Precisa saber se foi limitação técnica conhecida (sensor
offline, baseline em aprendizado) ou falha do serviço.

**Do agente, espera.** Diagnóstico honesto da causa da não-detecção e escalonamento quando o caso
extrapola o remoto — sem tentar justificar o injustificável.

---

### P07 — Gerente de Manutenção

| | |
| :--- | :--- |
| **Perfil API** | `maintenance_manager` |
| **Permissões** | `read`, `action_low`, `action_high`, `escalate` |
| **Representantes** | Ana (Forja Brasil) — TKT-CTX-01, TKT-INV-11 · Helena (Papel Sul) — TKT-EXE-14 |
| **Contexto** | Perfil de maior autoridade. Decide sobre cobertura, criticidade e priorização. |

**Necessidade.** Saber se o modelo cobre determinada classe de ativo antes de investir em
instrumentação, e ajustar criticidade conforme a realidade da produção.

**Frustração.** Descobrir tarde que um ativo instrumentado não é coberto pelo modelo.

**Do agente, espera.** Resposta precisa sobre cobertura — incluindo a distinção entre "suportado" e
"consegue aprender baseline" — e execução de alterações de configuração com registro de justificativa.

---

### P08 — Avaliador do Agente *(persona de sistema)*

| | |
| :--- | :--- |
| **Perfil API** | — não interage com a API industrial |
| **Representante** | O próprio autor, no papel de pesquisador |
| **Contexto** | Não é usuário do produto. É quem mede o produto. |

**Necessidade.** Executar centenas de execuções de forma reprodutível, inspecionar qualquer
trajetória passo a passo, e comparar arquiteturas com métricas objetivas.

**Frustração.** Execução que falha no meio e força recomeço. Métrica agregada que não permite
descer até o caso individual que falhou.

**Do agente, espera.** Trace completo e estruturado, execução retomável, e resultados que sustentem
ou refutem a hipótese sem ambiguidade.

> Esta persona justifica principalmente RF17–RF28, RF34–RF36 e RNF01–RNF03. Requisitos de
> autorização (RF13–RF15) pertencem às personas que executam ações, não ao Avaliador.

---

## 3. Mapa persona × chamado

| Persona | Perfil | Permissões | Chamados |
| :--- | :--- | :--- | :--- |
| P01 Operador | `operator` | `read` | TKT-INV-06 |
| P02 Mecânico | `mechanic` | `read`, `action_low` | TKT-CTX-02, TKT-INV-09, TKT-INV-11b, TKT-EXE-12 |
| P03 Analista de Confiabilidade | `reliability_analyst` | `read`, `action_low` | TKT-CTX-03, TKT-INV-05, TKT-INV-10, TKT-EXE-13 |
| P04 Engenheiro | `engineer` | `read`, `action_low`, `action_high` | TKT-INV-08, TKT-EXE-15 |
| P05 Eletricista | `electrician` | `read` | TKT-INV-07 |
| P06 Coordenador | `coordinator` | `read`, `action_low`, `escalate` | TKT-INV-04, TKT-EXE-16 |
| P07 Gerente | `maintenance_manager` | todas | TKT-CTX-01, TKT-INV-11, TKT-EXE-14 |
| P08 Avaliador | — | — | todos (como objeto de medição) |

---

## 4. Épicos

| ID | Épico | Modalidade |
| :--- | :--- | :--- |
| EP01 | Contextualizar — explicar conceitos e procedimentos com responsabilidade | Contextualizar |
| EP02 | Investigar — diagnosticar com disciplina de evidência | Investigar |
| EP03 | Executar — agir com segurança e justificativa | Executar |
| EP04 | Avaliar — medir qualidade e confiabilidade do agente | Sistema |
| EP05 | Inspecionar — tornar o comportamento do agente auditável | Sistema |
| EP06 | **Atender — receber, priorizar e conduzir tickets continuamente** | **Produto** |

---

## 5. User Stories

Formato: **Como** \<persona\>, **quero** \<capacidade\>, **para** \<valor\>.
Critérios de aceitação em formato Gherkin (Dado / Quando / Então).

### EP01 — Contextualizar

---

**US01 — Procedimento aplicável ao ativo**
*Como* Gerente de Manutenção (P07), *quero* obter o procedimento de manutenção aplicável ao meu
ativo e à falha em questão, *para* executar a intervenção corretamente.

> **Dado** um chamado sobre troca de rolamento no motor M-101
> **Quando** o agente consultar a base de conhecimento e a configuração técnica do ativo
> **Então** deve retornar o procedimento aplicável contextualizado ao `part_number` do rolamento
> **E** se o procedimento vier incompleto, deve declarar quais etapas estão ausentes

*Chamado:* TKT-CTX-01 · *RF:* RF01, RF02, RF08, RF09, RF11 · *UC:* UC-01

---

**US02 — Tradução de termo técnico**
*Como* Mecânico (P02), *quero* entender um termo técnico que apareceu no meu relatório, *para*
interpretar o diagnóstico sem depender do suporte.

> **Dado** a pergunta "o relatório fala em BPFO, o que é isso?"
> **Quando** o agente consultar o glossário e o espectro do ativo
> **Então** deve definir o termo em linguagem acessível
> **E** relacionar a definição ao pico específico observado no espectro daquele ativo
> **E** se o termo estiver ausente de parte das fontes, indicar a limitação

*Chamado:* TKT-CTX-02 · *RF:* RF01, RF02, RF08, RF09, RF11 · *UC:* UC-01

---

**US03 — Origem do limiar de alarme** ⚠️ *caso crítico*
*Como* Analista de Confiabilidade (P03), *quero* saber de onde vem o limiar de alarme de RMS do meu
ativo, *para* validar se o alerta recebido faz sentido.

> **Dado** a pergunta "a partir de qual RMS vocês consideram alarme? É tabela fixa?"
> **Quando** o agente consultar o baseline e a série de RMS do ativo
> **Então** deve explicar que o limiar deriva de `reference + tolerance` do baseline aprendido
> **E** apresentar os valores numéricos específicos daquele ativo
> **E NÃO** deve derivar o limiar de norma ISO nem de tabela por classe de máquina
> **E** se a base de conhecimento genérica conflitar com o baseline do ativo, deve prevalecer o
> baseline, com o conflito declarado

*Chamado:* TKT-CTX-03 · *RF:* RF01, RF07, RF08, RF10, RF11 · *UC:* UC-01, UC-03
*Nota:* este é o caso que detecta contaminação por conhecimento prévio do modelo.

---

### EP02 — Investigar

---

**US04 — Falha sem alerta prévio**
*Como* Coordenador (P06), *quero* entender por que não recebi alerta antes de um ativo quebrar,
*para* saber se houve limitação técnica ou falha do serviço.

> **Dado** um chamado sobre quebra do redutor G-501 sem aviso prévio
> **Quando** o agente investigar cadastro, baseline, qualidade de dados e série de RMS
> **Então** deve identificar que o baseline estava em `learning` e que houve indisponibilidade de dados
> **E** deve explicar que detecção por desvio exige baseline `established`
> **E** deve escalar o caso, por não haver base para conclusão remota

*Chamado:* TKT-INV-04 · *RF:* RF05, RF09, RF11, RF16 · *UC:* UC-02, UC-04

---

**US05 — Tendência sem insight**
*Como* Analista de Confiabilidade (P03), *quero* entender por que não recebi insight apesar de uma
tendência clara de RMS, *para* saber se o problema é do meu ativo ou do sistema.

> **Dado** RMS em elevação há duas semanas no compressor C-710
> **Quando** o agente verificar série de RMS, baseline, análises pendentes e estado do modelo
> **Então** deve identificar o baseline como `established` e o limiar ultrapassado
> **E** deve identificar o modelo com `processing_state` em atraso como causa da ausência de insight
> **E** deve distinguir "não detectou" de "não processou ainda"

*Chamado:* TKT-INV-05 · *RF:* RF05, RF08, RF11 · *UC:* UC-02, UC-04

---

**US06 — Suspeita de falso positivo** ⚠️ *caso crítico*
*Como* Operador (P01), *quero* validar se um insight que contraria minha percepção é falso positivo,
*para* não parar a máquina sem necessidade.

> **Dado** um insight de desbalanceamento no spindle S-420 que o operador contesta
> **Quando** o agente verificar a análise, o baseline, o espectro e análises anteriores
> **Então** deve identificar `baseline_state_at_detection = invalidated`
> **E** deve verificar que a amplitude em 1× não sustenta desbalanceamento
> **E** deve identificar a análise especializada conflitante
> **E** deve escalar em vez de afirmar um diagnóstico

*Chamado:* TKT-INV-06 · *RF:* RF05, RF08, RF10, RF11 · *UC:* UC-02, UC-03, UC-04
*Nota:* caso de referência da hipótese central — exige verificação de pré-condição antes de confiar.

---

**US07 — Origem elétrica ou mecânica**
*Como* Eletricista (P05), *quero* saber se uma elevação abrupta de vibração tem origem elétrica,
*para* decidir se devo atuar ou acionar a mecânica.

> **Dado** elevação abrupta de RMS no motor M-605
> **Quando** o agente analisar o espectro buscando 2× a frequência de linha
> **Então** deve verificar a configuração elétrica do ativo (`line_frequency_hz`)
> **E** se o espectro vier parcial com bandas ausentes, deve declarar a incerteza
> **E NÃO** deve afirmar origem elétrica sem a banda de frequência correspondente

*Chamado:* TKT-INV-07 · *RF:* RF08, RF09, RF10 · *UC:* UC-02, UC-03

---

**US08 — Diagnósticos divergentes**
*Como* Engenheiro (P04), *quero* reconciliar diagnóstico automático e laudo de especialista quando
divergem, *para* decidir a intervenção correta.

> **Dado** análise automática indicando desalinhamento e laudo especializado indicando base solta
> **Quando** o agente comparar as duas análises e consultar o espectro
> **Então** deve apresentar ambas com suas confianças e origens
> **E** deve usar a evidência espectral (subharmônicos) como critério de desempate
> **E** se a evidência não desempatar, deve declarar o conflito como não resolvido

*Chamado:* TKT-INV-08 · *RF:* RF08, RF10, RF11 · *UC:* UC-03, UC-04

---

**US09 — Análise desatualizada após intervenção**
*Como* Mecânico (P02), *quero* entender por que o insight persiste após eu ter feito o reparo,
*para* saber se preciso agir novamente.

> **Dado** rolamento substituído há três dias e insight de falha ainda ativo
> **Quando** o agente verificar o status da análise, o baseline e o frescor dos dados
> **Então** deve identificar a análise como `stale`
> **E** deve identificar o baseline como `invalidated` com razão `maintenance_intervention`
> **E** deve explicar que o desvio ainda é medido contra o estado pré-manutenção
> **E** deve recomendar reprocesso com justificativa

*Chamado:* TKT-INV-09 · *RF:* RF05, RF09, RF11, RF15 · *UC:* UC-02, UC-05

---

**US10 — Confiabilidade sob sinal ruim**
*Como* Analista de Confiabilidade (P03), *quero* saber se posso confiar num insight quando a
qualidade do sinal está ruim, *para* calibrar minha decisão.

> **Dado** qualidade de sinal baixa no ventilador V-301 e insight com confiança alta
> **Quando** o agente comparar métricas de qualidade com os requisitos do modelo
> **Então** deve confrontar `completeness` e `snr_db` com `min_completeness` e `min_snr_db`
> **E** deve explicitar a tensão entre qualidade baixa e confiança declarada alta
> **E NÃO** deve endossar a confiança do insight sem qualificá-la

*Chamado:* TKT-INV-10 · *RF:* RF05, RF08, RF09 · *UC:* UC-02

---

**US11 — Cobertura do modelo**
*Como* Gerente de Manutenção (P07), *quero* saber se o modelo cobre determinada classe de ativo,
*para* decidir sobre instrumentação.

> **Dado** a pergunta sobre cobertura para um motor de corrente contínua
> **Quando** o agente consultar cobertura do modelo e capacidade de aprendizado do baseline
> **Então** deve distinguir "tipo suportado" de "consegue aprender baseline" (`can_learn_baseline`)
> **E** deve explicar que com `learnable = false` só há detecção sintomática

*Chamado:* TKT-INV-11 · *RF:* RF05, RF08 · *UC:* UC-02

---

**US12 — Detecção sem baseline** ⚠️ *caso crítico*
*Como* Mecânico (P02), *quero* entender como uma falha foi detectada num ativo sem histórico,
*para* confiar no diagnóstico.

> **Dado** insight de falta de lubrificação em motor instalado há uma semana
> **Quando** o agente verificar o modo de detecção da análise e o estado do baseline
> **Então** deve identificar `detection_mode = symptom`
> **E** deve explicar que detecção sintomática independe de baseline
> **E** deve contrastar com falhas por desvio, que exigem baseline `established`
> **E NÃO** deve usar "baseline em learning" como argumento para invalidar o insight

*Chamado:* TKT-INV-11b · *RF:* RF05, RF06, RF11 · *UC:* UC-02
*Nota:* caso espelhado de US04 — mesma condição de baseline, conclusão oposta. Detecta agente que
aplica a regra de pré-condição mecanicamente, sem distinguir o modo de detecção.

---

### EP03 — Executar

---

**US13 — Reprocessar análise**
*Como* Mecânico (P02), *quero* reprocessar a análise após minha intervenção, *para* confirmar que o
problema foi resolvido.

> **Dado** um pedido de reprocesso após troca de rolamento
> **Quando** o agente validar contexto e permissão do usuário
> **Então** deve confirmar que o perfil possui `action_low`
> **E** deve submeter o reprocesso com justificativa fundamentada na intervenção
> **E** deve solicitar confirmação explícita antes de executar

*Chamado:* TKT-EXE-12 · *RF:* RF12, RF13, RF14, RF15 · *UC:* UC-05, UC-10

---

**US14 — Solicitar análise especializada**
*Como* Analista de Confiabilidade (P03), *quero* acionar um especialista quando o insight não
convence, *para* obter avaliação humana qualificada.

> **Dado** um pedido de análise especializada no compressor C-710
> **Quando** o agente reunir o contexto do caso
> **Então** deve submeter a solicitação com contexto e justificativa
> **E** deve confirmar o acionamento ao usuário

*Chamado:* TKT-EXE-13 · *RF:* RF13, RF15 · *UC:* UC-05, UC-10

---

**US15 — Alterar criticidade do ativo**
*Como* Gerente de Manutenção (P07), *quero* alterar a criticidade de um ativo, *para* refletir a
realidade atual da produção.

> **Dado** um pedido de redução de criticidade do ventilador V-301
> **Quando** o agente validar a permissão do usuário
> **Então** deve confirmar que o perfil possui `action_high`
> **E** deve alertar sobre o impacto da alteração na priorização
> **E** deve exigir confirmação explícita antes de executar

*Chamado:* TKT-EXE-14 · *RF:* RF12, RF13, RF14, RF15 · *UC:* UC-05, UC-10

---

**US16 — Solicitar retreinamento**
*Como* Engenheiro (P04), *quero* solicitar retreinamento do modelo quando ele erra sistematicamente,
*para* melhorar a detecção no meu parque.

> **Dado** um pedido de retreinamento baseado em erros recorrentes no spindle
> **Quando** o agente reunir o histórico de erros como evidência
> **Então** deve verificar a permissão `action_high`
> **E** deve compor justificativa fundamentada em evidência de erro, não em opinião do cliente
> **E** deve exigir confirmação explícita antes de executar

*Chamado:* TKT-EXE-15 · *RF:* RF12, RF13, RF14, RF15 · *UC:* UC-05, UC-10

---

**US17 — Escalar para análise humana**
*Como* Coordenador (P06), *quero* encaminhar um caso que ultrapassa o suporte remoto, *para* obter
atendimento em campo.

> **Dado** um caso que exige inspeção presencial
> **Quando** o agente reconhecer o limite do atendimento remoto
> **Então** deve verificar a permissão `escalate`
> **E** deve submeter o escalonamento com o contexto acumulado da investigação
> **E** deve incluir na justificativa o que já foi verificado e o que permanece incerto

*Chamado:* TKT-EXE-16 · *RF:* RF11, RF13, RF15 · *UC:* UC-04, UC-05

---

### EP06 — Atender *(produto)*

---

**US25 — Abrir um ticket**
*Como* Solicitante (P01–P07), *quero* abrir um chamado e receber confirmação imediata, *para* seguir
trabalhando enquanto o sistema investiga.

> **Dado** um chamado submetido por API ou interface
> **Quando** o sistema receber a solicitação
> **Então** deve responder em menos de 200 ms com identificador e estado `queued`
> **E** o atendimento deve ocorrer de forma assíncrona
> **E** o estado deve ser consultável a qualquer momento

*RF:* RF37, RF42 · *RNF:* RNF18 · *UC:* UC-11

---

**US26 — Ser atendido por criticidade**
*Como* Coordenador (P06), *quero* que chamados de ativos críticos sejam atendidos primeiro, *para*
que uma parada de linha não espere atrás de uma dúvida de glossário.

> **Dado** uma fila com tickets de criticidades diferentes
> **Quando** um worker ficar disponível
> **Então** deve atender o de maior criticidade do ativo
> **E** a prioridade deve ser **derivada da API**, nunca informada pelo solicitante

*RF:* RF38, RF42 · *UC:* UC-11

---

**US27 — Continuar a conversa**
*Como* Analista de Confiabilidade (P03), *quero* responder a uma pergunta do agente e receber a
continuação, *para* não recomeçar o atendimento do zero.

> **Dado** um ticket cuja investigação depende de informação que só eu tenho
> **Quando** o agente solicitar essa informação
> **Então** o ticket deve entrar em estado `awaiting_user`
> **E** minha resposta deve retomar o atendimento com o contexto preservado
> **E** o agente **não** deve repetir as consultas que já fez

*RF:* RF40, RF41 · *UC:* UC-11, UC-12

---

### EP04 — Avaliar

---

**US18 — Executar suíte sobre o golden dataset**
*Como* Avaliador (P08), *quero* executar a suíte completa sobre o golden dataset, *para* obter
métricas comparáveis entre arquiteturas.

> **Dado** um golden dataset e duas arquiteturas configuradas
> **Quando** o runner executar todos os casos com N repetições
> **Então** deve produzir métricas de trajetória, argumentos, decisão e evidência por caso
> **E** deve permitir agregação por arquitetura, modelo e regime de degradação

*RF:* RF20, RF22, RF24, RF25, RF28 · *UC:* UC-06

---

**US19 — Retomar execução interrompida**
*Como* Avaliador (P08), *quero* retomar uma execução interrompida por rate limit, *para* não perder
o trabalho já realizado.

> **Dado** uma execução interrompida na metade
> **Quando** o runner for reiniciado com o mesmo identificador
> **Então** deve pular os casos já concluídos
> **E** deve retomar exatamente do ponto de interrupção

*RF:* RF23 · *RNF:* RNF03 · *UC:* UC-06

---

**US20 — Avaliar qualidade subjetiva com rubrica**
*Como* Avaliador (P08), *quero* avaliar critérios subjetivos com rubrica binária auditável, *para*
medir qualidade de resposta sem arbitrariedade.

> **Dado** uma resolução produzida pelo agente
> **Quando** o juiz aplicar a rubrica de critérios binários
> **Então** deve produzir veredito por critério, com justificativa
> **E** o modelo do juiz deve ser distinto do modelo do agente
> **E** deve ser possível medir a concordância do juiz com rotulação humana em amostra

*RF:* RF26, RF27 · *RNF:* RNF09, RNF10 · *UC:* UC-07

---

**US21 — Medir estabilidade entre execuções**
*Como* Avaliador (P08), *quero* medir a variação de comportamento entre execuções idênticas, *para*
quantificar a confiabilidade do agente.

> **Dado** o mesmo caso executado N vezes com a mesma configuração
> **Quando** as execuções forem comparadas
> **Então** deve reportar a taxa de concordância da decisão final
> **E** deve reportar a variação da trajetória
> **E** deve separar variância originada no modelo da originada na API

*RF:* RF24 · *RNF:* RNF01 · *UC:* UC-06

---

### EP05 — Inspecionar

---

**US22 — Inspecionar trajetória passo a passo**
*Como* Avaliador (P08), *quero* navegar a trajetória de uma execução passo a passo, *para*
diagnosticar o comportamento do agente.

> **Dado** uma execução registrada
> **Quando** o inspetor for aberto no front
> **Então** deve exibir cada passo com agente responsável, tool, argumentos, retorno e latência
> **E** deve destacar as pré-condições verificadas
> **E** deve marcar os pontos de handoff entre agentes

*RF:* RF17, RF18, RF30 · *UC:* UC-08

---

**US23 — Acompanhar execução em tempo real**
*Como* Avaliador (P08), *quero* acompanhar a execução do agente em tempo real, *para* demonstrar o
raciocínio durante a apresentação.

> **Dado** um chamado submetido pela interface
> **Quando** o agente iniciar a execução
> **Então** cada evento deve ser transmitido ao front conforme ocorre
> **E** o atraso não deve exceder 1 segundo em relação ao evento real

*RF:* RF19, RF29 · *RNF:* RNF08 · *UC:* UC-08

---

**US24 — Comparar arquiteturas**
*Como* Avaliador (P08), *quero* comparar as arquiteturas lado a lado no mesmo caso, *para*
evidenciar a diferença de comportamento.

> **Dado** o mesmo caso executado nas duas arquiteturas
> **Quando** a comparação for aberta
> **Então** deve exibir as duas trajetórias em paralelo
> **E** deve destacar divergências de decisão e de evidência utilizada

*RF:* RF28, RF31, RF32 · *UC:* UC-08

---

## 6. Cobertura

| Épico | Stories | Chamados cobertos |
| :--- | :--- | :--- |
| EP06 Atender *(produto)* | US25–US27 | — (fluxo contínuo) |
| EP01 Contextualizar | US01–US03 | 3 de 3 |
| EP02 Investigar | US04–US12 | 9 de 9 |
| EP03 Executar | US13–US17 | 5 de 5 |
| EP04 Avaliar | US18–US21 | — (sistema) |
| EP05 Inspecionar | US22–US24 | — (sistema) |

**17 de 17 chamados cobertos.** As stories marcadas ⚠️ (US03, US06, US12) são as que discriminam
diretamente a hipótese central e recebem peso maior na análise.
