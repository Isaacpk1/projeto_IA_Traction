# 04 — Casos de Uso

## 1. Atores

### Atores primários

| Ator | Descrição | Personas |
| :--- | :--- | :--- |
| **Solicitante** | Pessoa usuária da plataforma que abre o chamado. Ator generalizado; suas permissões variam por perfil. | P01–P07 |
| **Sistema Cliente** | Integração externa que submete tickets por API em nome de um solicitante. | — |
| **Avaliador** | Pesquisador que executa e analisa os experimentos. Não interage com a API industrial. | P08 |

**Especializações do Solicitante** (herança UML — cada uma herda os casos de uso do pai e adiciona
os habilitados por sua permissão):

```
                    ┌──────────────┐
                    │ Solicitante  │  read
                    └──────┬───────┘
          ┌────────────────┼────────────────┐
          │                │                │
   ┌──────▼─────┐   ┌──────▼──────┐  ┌──────▼──────┐
   │ Sol. c/    │   │ Sol. c/     │  │ Sol. c/     │
   │ action_low │   │ action_high │  │ escalate    │
   └────────────┘   └─────────────┘  └─────────────┘
```

### Atores secundários

| Ator | Descrição |
| :--- | :--- |
| **API Industrial TRACTIAN** | Sistema externo. Fonte de toda evidência. Imutável. |
| **Provedor de LLM** | Serviço externo de inferência. Gemini (Google AI Studio) para os papéis de agente. |
| **Modelo Juiz** | LLM de provedor e família distintos (Groq), usado apenas na avaliação — RNF09. |

---

## 2. Diagrama de casos de uso

```
                       SISTEMA DE AGENTES INDUSTRIAIS
   ┌──────────────────────────────────────────────────────────────────┐
   │                                                                  │
   │   ┌────────────────────────┐                                     │
   │   │ UC-01 Contextualizar   │                                     │
   │   │       solicitação      │─ ─ ─include─ ─ ─┐                    │
   │   └────────────────────────┘                 │                   │
   │   ┌────────────────────────┐                 ▼                   │
   │   │ UC-02 Investigar       │       ┌───────────────────┐         │
   │   │       condição do ativo│──────►│ UC-09 Consultar   │         │
   │   └───────────┬────────────┘       │  API via tools    │         │
   │               │ «extend»           └───────────────────┘         │
   │   ┌───────────▼────────────┐                 ▲                   │
   │   │ UC-03 Reconciliar      │                 │                   │
   │   │       evidência        │─ ─ ─ ─ ─ ─ ─ ─ ─┤                   │
   │   │       conflitante      │                 │                   │
   │   └────────────────────────┘                 │                   │
   │   ┌────────────────────────┐                 │                   │
   │   │ UC-04 Decidir          │─ ─ ─include─ ─ ─┘                   │
   │   │       encaminhamento   │                                     │
   │   └───────────┬────────────┘                                     │
   │               │ «extend» (quando decisão = agir)                 │
   │   ┌───────────▼────────────┐      ┌────────────────────┐         │
   │   │ UC-05 Executar ação    │─────►│ UC-10 Validar      │         │
   │   │       de impacto       │inclui│  permissão         │         │
   │   └────────────────────────┘      └────────────────────┘         │
   │                                                                  │
   │   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─        │
   │                    SUBSISTEMA DE AVALIAÇÃO                       │
   │   ┌────────────────────────┐   ┌────────────────────────┐        │
   │   │ UC-06 Executar suíte   │   │ UC-07 Avaliar por      │        │
   │   │       de avaliação     │──►│       rubrica          │        │
   │   └────────────────────────┘   └────────────────────────┘        │
   │   ┌────────────────────────┐                                     │
   │   │ UC-08 Inspecionar      │                                     │
   │   │       trajetória       │                                     │
   │   └────────────────────────┘                                     │
   └──────────────────────────────────────────────────────────────────┘
        ▲                    ▲                          ▲
        │                    │                          │
   Solicitante         API Industrial              Avaliador
                       Provedor LLM                Modelo Juiz
```

---

## 3. Especificação dos casos de uso

> **Convenção.** FP = Fluxo Principal · FA = Fluxo Alternativo · FE = Fluxo de Exceção.
> Os fluxos de exceção mapeiam diretamente os **modos probabilísticos da API**
> (`complete`, `partial`, `inconclusive`, `conflict`, `unavailable`, `stale`, `pending`).
> Nesta solução, tratar exceção **não é** caminho secundário: é o comportamento central avaliado.

---

## UC-01 — Contextualizar solicitação

| | |
| :--- | :--- |
| **Ator primário** | Solicitante |
| **Objetivo** | Obter explicação de conceito, termo ou procedimento, contextualizada ao ativo |
| **Pré-condição** | Chamado recebido com contexto de empresa, usuário e ativo |
| **Pós-condição** | Resolução do tipo `orientar` entregue, com evidência citada |
| **Requisitos** | RF01, RF02, RF07, RF08, RF11 |
| **User Stories** | US01, US02, US03 |
| **Chamados** | TKT-CTX-01, TKT-CTX-02, TKT-CTX-03 |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | O Solicitante submete a mensagem com contexto estruturado |
| 2 | O sistema interpreta a solicitação e classifica a modalidade como **Contextualizar** |
| 3 | O sistema consulta a base de conhecimento pelo termo ou procedimento pertinente |
| 4 | O sistema consulta a configuração técnica do ativo para contextualizar a resposta |
| 5 | O sistema relaciona o conhecimento genérico aos dados específicos do ativo |
| 6 | O sistema compõe a resolução citando os valores concretos consultados |
| 7 | O sistema submete resolução com decisão `orientar` |

### Fluxos alternativos

**FA-01.1 — Termo ausente do glossário**
No passo 3, a busca não retorna o termo.
→ O sistema consulta fontes correlatas (análises, espectro) e responde a partir da evidência
disponível, declarando que a definição formal não foi localizada. Retorna ao passo 6.

**FA-01.2 — Conhecimento genérico conflita com o dado do ativo** ⚠️
No passo 5, a orientação genérica da base contradiz o valor específico do ativo — por exemplo, a
base sugere limiar por classe de máquina enquanto o baseline do ativo indica outro valor.
→ **O dado específico do ativo prevalece.** O sistema declara o conflito explicitamente e explica
por que a fonte específica tem precedência. Retorna ao passo 6.

> Este fluxo é o núcleo de TKT-CTX-03 e o detector primário de contaminação por conhecimento prévio
> do modelo (RF07).

### Fluxos de exceção

**FE-01.1 — Procedimento parcial** (`mode = partial`)
O procedimento retorna com etapas ausentes.
→ O sistema entrega o que está disponível e enumera explicitamente as etapas ausentes. A resolução
permanece `orientar`, com lacuna declarada (RF09).

**FE-01.2 — Base de conhecimento indisponível** (`mode = unavailable`)
→ O sistema declara a indisponibilidade, não responde por conhecimento próprio, e oferece
escalonamento.

---

## UC-02 — Investigar condição do ativo

| | |
| :--- | :--- |
| **Ator primário** | Solicitante |
| **Objetivo** | Determinar a causa de um evento ou da ausência de um evento esperado |
| **Pré-condição** | Chamado recebido; ativo identificado |
| **Pós-condição** | Diagnóstico fundamentado, ou declaração explícita de impossibilidade de concluir |
| **Requisitos** | RF05, RF06, RF08, RF09, RF11, RF16, RF17 |
| **User Stories** | US04, US05, US06, US09, US10, US11, US12 |
| **Chamados** | TKT-INV-04, 05, 06, 09, 10, 11, 11b |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | O Solicitante submete a solicitação de investigação |
| 2 | O sistema classifica a modalidade como **Investigar** e identifica a pergunta raiz |
| 3 | O sistema consulta o cadastro e a configuração técnica do ativo |
| 4 | O sistema consulta as análises existentes do ativo |
| 5 | Para cada análise relevante, o sistema identifica o `detection_mode` |
| 6 | **Se** `detection_mode = baseline` → o sistema consulta o estado do baseline **(obrigatório, RF05)** |
| 7 | O sistema consulta qualidade e frescor dos dados e compara com os requisitos do modelo |
| 8 | O sistema consulta o estado de processamento do modelo |
| 9 | O sistema consulta evidência física — série de RMS e/ou espectro — conforme a hipótese diagnóstica |
| 10 | O sistema avalia a suficiência da evidência acumulada |
| 11 | O sistema compõe o diagnóstico com evidências citadas e lacunas declaradas |
| 12 | O sistema prossegue para UC-04 (decidir encaminhamento) |

> **Invariante de ordem.** O passo 6 precede qualquer afirmação sobre confiabilidade do insight.
> A verificação dessa ordem no trace é a métrica primária da hipótese H1.

### Fluxos alternativos

**FA-02.1 — Detecção sintomática** ⚠️
No passo 5, `detection_mode = symptom`.
→ O passo 6 **é dispensado**: a validade do insight não depende do estado do baseline. O sistema
segue para o passo 7. Ao explicar, contrasta explicitamente com detecção por desvio.

> Espelho de FA-02.2. Aplicar a regra de pré-condição aqui seria erro. Base de TKT-INV-11b (US12).

**FA-02.2 — Baseline em `learning` com detecção por desvio**
No passo 6, o baseline está em `learning`.
→ O sistema conclui que não há limiar confiável e que detecção por desvio era tecnicamente
impossível. Segue para o passo 7 para confirmar se houve também indisponibilidade de dados. Base de
TKT-INV-04 (US04).

**FA-02.3 — Baseline `invalidated`**
No passo 6, o baseline está em `invalidated`.
→ O sistema verifica `invalidation_reason` e a data. Se a análise é anterior à invalidação, ela é
marcada como potencialmente inválida. O sistema busca evidência física independente (passo 9) antes
de qualquer conclusão. Base de TKT-INV-06 e TKT-INV-09.

**FA-02.4 — Modelo com processamento pendente ou atrasado**
No passo 8, `processing_state ∈ {pending, delayed, failed}`.
→ O sistema distingue **"não detectou"** de **"não processou"** e atribui a ausência de insight ao
estado do modelo, não à ausência de falha. Base de TKT-INV-05 (US05).

**FA-02.5 — Qualidade abaixo dos requisitos do modelo**
No passo 7, `completeness < min_completeness` ou `snr_db < min_snr_db`.
→ O sistema qualifica toda conclusão subsequente com essa limitação, mesmo que a análise declare
confiança alta. A tensão é explicitada, não resolvida silenciosamente. Base de TKT-INV-10 (US10).

**FA-02.6 — Cobertura parcial do modelo**
No passo 8, o tipo do ativo é suportado mas `can_learn_baseline = false`.
→ O sistema explica que só há detecção sintomática para aquele subtipo. Base de TKT-INV-11 (US11).

### Fluxos de exceção

**FE-02.1 — Retorno parcial** (`mode = partial`)
Espectro com `bands_missing` não-vazio, ou série incompleta.
→ O sistema registra as bandas ausentes em `unverified` e **não infere** sobre a faixa ausente. Se a
banda ausente é justamente a diagnóstica, a conclusão é declarada indeterminada. Base de TKT-INV-07.

**FE-02.2 — Retorno inconclusivo** (`mode = inconclusive`)
→ O sistema não substitui a inconclusividade por inferência própria. Registra e prossegue por outra
via de evidência; esgotadas as vias, encaminha para escalonamento.

**FE-02.3 — Recurso indisponível** (`mode = unavailable`)
→ O sistema registra a indisponibilidade como fato relevante da investigação — a ausência de dado é
frequentemente a própria resposta (sensor mudo antes da quebra). Base de TKT-INV-04.

**FE-02.4 — Análise `stale`**
→ O sistema verifica se houve invalidação de baseline entre a data da análise e o momento atual, e
explica que o desvio permanece medido contra o estado anterior. Base de TKT-INV-09.

**FE-02.5 — Limite de passos atingido** (RF16)
→ O sistema encerra, registra `stop_reason = max_steps`, e compõe resolução com a evidência parcial
acumulada, declarando que a investigação não foi concluída. Nunca produz conclusão como se fosse
completa.

**FE-02.6 — Falha de comunicação com a API**
→ Nova tentativa com recuo exponencial (RNF04). Esgotadas as tentativas, a falha é registrada como
erro de infraestrutura, **distinta** de falha de comportamento do agente.

---

## UC-03 — Reconciliar evidência conflitante

| | |
| :--- | :--- |
| **Ator primário** | Solicitante |
| **Tipo** | «extend» de UC-02 |
| **Objetivo** | Resolver ou declarar irresolvível a divergência entre fontes |
| **Pré-condição** | Duas ou mais fontes com conclusões incompatíveis sobre o mesmo ativo |
| **Pós-condição** | Conflito resolvido com critério explícito, ou declarado não resolvido |
| **Requisitos** | RF08, RF10, RF11 |
| **User Stories** | US06, US07, US08 |
| **Chamados** | TKT-INV-06, TKT-INV-07, TKT-INV-08, TKT-CTX-03 |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | O sistema identifica a divergência entre fontes |
| 2 | O sistema caracteriza cada fonte: origem (automática/especializada), confiança, data, limitações |
| 3 | O sistema verifica as condições de geração de cada fonte — em especial o estado do baseline à época |
| 4 | O sistema busca evidência física independente para desempate (espectro, série temporal) |
| 5 | O sistema confronta a evidência física com cada hipótese em disputa |
| 6 | **Se** a evidência sustenta uma das hipóteses → o sistema conclui, explicitando o critério |
| 7 | O sistema registra o conflito e a resolução na resolução final |

### Fluxos alternativos

**FA-03.1 — Uma fonte tem pré-condição inválida**
No passo 3, uma das fontes foi gerada com baseline `invalidated`.
→ O peso dessa fonte é reduzido explicitamente, **mas ela não é descartada** — a evidência física do
passo 4 permanece decisiva. Base de TKT-INV-06.

**FA-03.2 — Evidência física sustenta a fonte especializada**
No passo 5, o espectro corrobora o laudo humano contra o diagnóstico automático.
→ O sistema conclui pela fonte especializada, citando o achado espectral concreto (ex.: presença de
subharmônicos indicando folga). Base de TKT-INV-08.

### Fluxos de exceção

**FE-03.1 — Evidência física não desempata** ⚠️
No passo 6, a evidência é compatível com ambas as hipóteses ou insuficiente.
→ O sistema **declara o conflito como não resolvido**, apresenta ambas as hipóteses com suas
evidências, e encaminha para UC-04 com tendência a escalonamento.

> **Este é o comportamento correto, não uma falha.** Escolher arbitrariamente uma hipótese para
> parecer conclusivo é o modo de falha que a avaliação penaliza.

**FE-03.2 — Espectro parcial na banda diagnóstica**
A banda de frequência que distinguiria as hipóteses está ausente.
→ O sistema declara qual banda faltou e por que ela seria decisiva. Não infere. Base de TKT-INV-07.

---

## UC-04 — Decidir encaminhamento

| | |
| :--- | :--- |
| **Ator primário** | Solicitante |
| **Objetivo** | Classificar a resolução em orientar, agir ou escalar |
| **Pré-condição** | Investigação concluída ou encerrada por política de parada |
| **Pós-condição** | Resolução estruturada submetida, com decisão, justificativa e evidências |
| **Requisitos** | RF11, RF15, RF16, RF17 |
| **User Stories** | US04, US06, US17 |
| **Chamados** | todos |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | O sistema avalia a suficiência da evidência acumulada |
| 2 | O sistema avalia se a solicitação original demanda ação na plataforma |
| 3 | O sistema avalia se o caso ultrapassa o escopo do atendimento remoto |
| 4 | O sistema classifica a decisão |
| 5 | O sistema compõe justificativa referenciando evidência coletada |
| 6 | O sistema submete a resolução estruturada (tool terminal) |

### Critérios de decisão

| Decisão | Critério |
| :--- | :--- |
| **Orientar** | A evidência sustenta uma explicação e nenhuma ação na plataforma foi solicitada nem se faz necessária |
| **Agir** | Ação foi solicitada ou é claramente indicada, o usuário possui a permissão, e existe justificativa fundamentada em evidência |
| **Escalar** | A evidência é insuficiente, o conflito é irresolvível, o caso exige inspeção física, ou o usuário solicitou atendimento humano |

### Fluxos alternativos

**FA-04.1 — Evidência insuficiente após investigação completa**
→ Decisão = `escalar`. A justificativa enumera **o que foi verificado** e **o que permaneceu
incerto** — o escalonamento carrega o trabalho já feito, não recomeça do zero.

**FA-04.2 — Ação indicada mas usuário sem permissão**
No passo 2, a ação é pertinente mas o perfil não a habilita.
→ Decisão = `orientar`, explicando qual ação seria indicada e qual perfil poderia executá-la. **A
ação não é tentada** (RF13).

**FA-04.3 — Solicitação de ação sem fundamento em evidência**
O cliente pede uma ação que a investigação não sustenta.
→ Decisão = `orientar`. O sistema explica por que a ação não se justifica. Não executa por
deferência ao pedido.

> **Modo de falha crítico.** Executar uma ação apenas porque foi pedida, sem fundamento, é o "falso
> agir" — o erro de maior custo do sistema e métrica de segurança primária.

### Fluxos de exceção

**FE-04.1 — Investigação encerrada por limite de passos**
→ Decisão = `escalar`, com registro explícito de que a investigação foi truncada.

**FE-04.2 — Falha na submissão da resolução**
→ Nova tentativa; persistindo, a execução é marcada como falha de infraestrutura, não como decisão
do agente.

---

## UC-05 — Executar ação de impacto

| | |
| :--- | :--- |
| **Ator primário** | Solicitante com permissão de ação |
| **Tipo** | «extend» de UC-04 (quando decisão = agir) |
| **Objetivo** | Executar ação na plataforma com segurança e rastreabilidade |
| **Pré-condição** | Decisão = `agir`; justificativa fundamentada disponível |
| **Pós-condição** | Ação executada e registrada, ou recusada com motivo |
| **Requisitos** | RF12, RF13, RF14, RF15, RF17 |
| **User Stories** | US13, US14, US15, US16, US17 |
| **Chamados** | TKT-EXE-12 a TKT-EXE-16 |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | O sistema identifica a ação pretendida e seu `tier` no overlay |
| 2 | O sistema consulta o perfil do usuário e suas permissões **(inclui UC-10)** |
| 3 | O sistema verifica que a permissão requerida está presente |
| 4 | O sistema compõe os parâmetros da ação e a justificativa fundamentada em evidência |
| 5 | **Se** `requires_confirmation` → o sistema apresenta ação, justificativa e consequência, e aguarda confirmação explícita |
| 6 | O Solicitante confirma |
| 7 | O `PreActionGuard` revalida permissão, confirmação vinculada e evidência ancorada |
| 8 | Somente após aprovação do gateway, o sistema executa a ação pela tool correspondente |
| 9 | O sistema registra o resultado e confirma ao Solicitante |

> **Duas propriedades diferentes.** Na arquitetura multi-agente, a execução ocorre exclusivamente no
> Executor, único portador de tools `tier: impact` (RF12, RNF05). A garantia de que uma ação indevida
> não produz efeito vem do `PreActionGuard` no gateway, aplicado também à arquitetura mono.

### Fluxos alternativos

**FA-05.1 — Permissão ausente**
No passo 3, o perfil não possui a permissão requerida.
→ A ação **não é tentada**. O sistema informa a restrição e qual perfil poderia executá-la. Retorna
a UC-04 com decisão `orientar`.

**FA-05.2 — Confirmação recusada**
No passo 6, o Solicitante recusa.
→ A ação é cancelada. A recusa é registrada no trace. O sistema oferece alternativas.

**FA-05.3 — Ação com consequência sobre o baseline**
A ação altera configuração técnica e portanto invalidará o baseline.
→ O sistema **deve** informar essa consequência no passo 5, antes da confirmação. Base de
TKT-EXE-14.

### Fluxos de exceção

**FE-05.1 — Parâmetros inválidos**
A API rejeita por parâmetro malformado.
→ O sistema registra o erro, corrige se puder determinar a correção a partir da mensagem, e tenta
novamente **uma vez**. Persistindo, escala.

**FE-05.2 — Justificativa recusada pela API**
→ O sistema não reformula a justificativa apenas para obter aceitação. Registra a recusa e escala.

> Reescrever a justificativa até ser aceita é contornar o controle, não atendê-lo.

**FE-05.3 — Falha na execução**
→ O sistema **não presume sucesso**. Registra a falha e informa o Solicitante de que a ação não foi
efetivada.

**FE-05.4 — `PreActionGuard` bloqueia a ação**
→ Nenhuma chamada externa é emitida. O trace registra a tentativa, a pré-condição ausente e a ação
efetivamente bloqueada; o caso é escalado para análise humana.

---

## UC-06 — Executar suíte de avaliação

| | |
| :--- | :--- |
| **Ator primário** | Avaliador |
| **Objetivo** | Executar o golden dataset sobre uma ou mais arquiteturas e produzir métricas |
| **Pré-condição** | Golden dataset disponível; arquiteturas configuradas; API no ar |
| **Pós-condição** | Traces persistidos e métricas calculadas |
| **Requisitos** | RF20, RF22, RF23, RF24, RF25, RF28 · RNF01, RNF02, RNF03, RNF15 |
| **User Stories** | US18, US19, US21 |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | O Avaliador configura a execução: dataset, arquiteturas, modelo, repetições, regime de seed |
| 2 | O sistema **valida o isolamento do gabarito** e aborta se houver violação **(RNF02)** |
| 3 | O sistema registra os metadados da configuração **(RNF15)** |
| 4 | O sistema verifica checkpoint existente e determina os casos pendentes |
| 5 | O sistema executa os casos pendentes com concorrência limitada |
| 6 | Ao concluir cada caso, o sistema persiste o trace imediatamente |
| 7 | O sistema aplica as métricas determinísticas sobre cada trace **(RF24)** |
| 8 | O sistema aplica a verificação de ancoragem de evidência **(RF25)** |
| 9 | O sistema agrega os resultados por arquitetura, modelo e regime |
| 10 | O sistema emite o relatório comparativo |

### Fluxos alternativos

**FA-06.1 — Retomada de execução**
No passo 4, existe checkpoint parcial.
→ Casos concluídos são pulados; a execução prossegue dos pendentes (RF23).

**FA-06.2 — Regime de seed variável**
O Avaliador configura execução sem `seed` fixo.
→ O sistema registra o regime como variável experimental. Métricas de estabilidade passam a
capturar variância combinada de modelo e API, e o relatório sinaliza essa combinação.

### Fluxos de exceção

**FE-06.1 — Violação de isolamento detectada** 🛑
No passo 2, um caminho de gabarito é acessível ao agente.
→ **A execução é abortada.** Nenhum resultado é produzido. Falha de build.

**FE-06.2 — Rate limit do provedor**
→ Recuo exponencial (RNF04). Persistindo além do limite de tentativas, o caso é marcado como falha
de infraestrutura e o checkpoint preserva os concluídos (RNF03).

**FE-06.3 — Coincidência entre modelo do agente e do juiz** 🛑
→ A suíte aborta na inicialização (RNF09).

---

## UC-07 — Avaliar por rubrica

| | |
| :--- | :--- |
| **Ator primário** | Avaliador |
| **Ator secundário** | Modelo Juiz |
| **Objetivo** | Avaliar critérios subjetivos com rubrica binária auditável |
| **Pré-condição** | Traces disponíveis; rubrica definida; modelo juiz distinto do agente |
| **Pós-condição** | Vetor de vereditos por critério, com justificativa |
| **Requisitos** | RF26, RF27 · RNF09, RNF10 |
| **User Stories** | US20 |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | O sistema verifica que o modelo juiz difere do modelo avaliado **(RNF09)** |
| 2 | O sistema carrega a rubrica de critérios binários |
| 3 | Para cada resolução, o sistema submete ao juiz a resolução e o trace |
| 4 | O juiz emite veredito booleano e justificativa por critério |
| 5 | O sistema valida a estrutura da resposta do juiz |
| 6 | O sistema agrega os vereditos por critério e por arquitetura |

### Fluxos alternativos

**FA-07.1 — Meta-avaliação**
O Avaliador possui rotulação humana para uma amostra.
→ O sistema compara vereditos do juiz com os rótulos humanos e reporta acurácia e kappa por critério
(RF27). Concordância baixa em um critério indica rubrica ambígua e demanda reescrita.

**FA-07.2 — Comparação pareada**
A avaliação compara duas resoluções do mesmo caso.
→ A comparação é executada nas duas ordens e o resultado é a média; a assimetria é reportada como
medida de viés de posição (RNF10).

### Fluxos de exceção

**FE-07.1 — Resposta do juiz malformada**
→ Nova tentativa com instrução de formato reforçada. Persistindo, o critério é marcado como
`indeterminado` — nunca preenchido por suposição.

**FE-07.2 — Juiz indisponível**
→ A avaliação determinística é preservada e reportada; os critérios subjetivos ficam pendentes. O
relatório indica cobertura parcial.

---

## UC-08 — Inspecionar trajetória

| | |
| :--- | :--- |
| **Ator primário** | Avaliador |
| **Objetivo** | Examinar o comportamento do agente passo a passo |
| **Pré-condição** | Execução registrada, ou em curso |
| **Pós-condição** | Trajetória visualizada com todos os campos acessíveis |
| **Requisitos** | RF17, RF18, RF19, RF29, RF30, RF31, RF32 · RNF08 |
| **User Stories** | US22, US23, US24 |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | O Avaliador seleciona uma execução |
| 2 | O sistema apresenta o resumo: caso, arquitetura, modelo, decisão, duração, passos |
| 3 | O sistema apresenta a trajetória ordenada |
| 4 | Para cada passo: agente responsável, raciocínio, tool, argumentos, retorno, latência |
| 5 | O sistema destaca as pré-condições verificadas e os pontos de handoff |
| 6 | O sistema apresenta a resolução com as evidências citadas ancoradas nos passos de origem |

### Fluxos alternativos

**FA-08.1 — Acompanhamento em tempo real**
A execução está em curso.
→ Os eventos são transmitidos conforme ocorrem, com atraso ≤ 1s (RNF08).

**FA-08.2 — Comparação lado a lado**
O Avaliador seleciona duas execuções do mesmo caso.
→ As trajetórias são exibidas em paralelo, com divergências de decisão e de evidência destacadas
(RF32).

### Fluxos de exceção

**FE-08.1 — Conexão de streaming interrompida**
→ Reconexão automática; ao reconectar, o histórico de eventos perdidos é recuperado do trace
persistido.

---

## UC-11 — Receber e enfileirar ticket

| | |
| :--- | :--- |
| **Ator primário** | Solicitante · **Sistema Cliente** (integração) |
| **Objetivo** | Aceitar um chamado, priorizá-lo e devolvê-lo à fila para atendimento assíncrono |
| **Pré-condição** | Ativo e usuário identificáveis |
| **Pós-condição** | Ticket enfileirado com prioridade; identificador devolvido |
| **Requisitos** | RF37, RF38, RF39, RF42 · RNF18, RNF19 |
| **User Stories** | US25, US26 |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | O Solicitante submete a mensagem com contexto (empresa, usuário, ativo) |
| 2 | O sistema valida o contrato de entrada |
| 3 | O sistema consulta a criticidade do ativo com deadline compatível com RNF18 e **deriva a prioridade** |
| 4 | O sistema enfileira a tarefa com `kind = ticket` |
| 5 | O sistema responde `202` com `ticket_id` e estado `queued` |
| 6 | Um worker disponível faz o *lease* da tarefa de maior prioridade |
| 7 | O atendimento prossegue por UC-01, UC-02 ou UC-05 conforme a modalidade |

> **Passo 6 é o mesmo `lease` usado pelas tarefas do experimento.** Ticket e caso de suíte percorrem
> o mesmo caminho de código (RF39) — é o que torna a suíte uma regressão do produto, e não um teste
> paralelo.

### Fluxos alternativos

**FA-11.1 — Criticidade indisponível**
No passo 3, a consulta ao ativo falha ou não retorna criticidade.
→ Prioridade padrão média. O ticket **não** é recusado por isso.

Timeout da consulta é tratado pelo mesmo fluxo. A ingestão nunca espera indefinidamente pela API;
criticidade conhecida pode ser obtida de cache com TTL registrado, e o fallback é observável.

**FA-11.2 — Fila acima da capacidade**
A entrada excede a vazão de processamento.
→ O ticket é aceito normalmente. A fila cresce, a profundidade fica visível no console, e o
atendimento segue por prioridade (RNF19). **Nada é descartado.**

### Fluxos de exceção

**FE-11.1 — Contrato de entrada inválido**
→ `400` com o campo em falta. Nada é enfileirado.

**FE-11.2 — Cota diária esgotada**
→ O ticket é **aceito e enfileirado**; o atendimento retoma no ciclo seguinte (RNF16). O estado
reflete a espera. Recusar a entrada por limitação interna transferiria ao cliente um problema que
não é dele.

---

## UC-12 — Continuar atendimento multi-turno

| | |
| :--- | :--- |
| **Ator primário** | Solicitante |
| **Objetivo** | Prosseguir um atendimento que aguardava informação adicional |
| **Pré-condição** | Ticket em estado `awaiting_user` |
| **Pós-condição** | Atendimento retomado com contexto preservado |
| **Requisitos** | RF40, RF41, RF43 · RF17 |
| **User Stories** | US27 |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | Durante a investigação, o agente identifica informação que só o solicitante possui |
| 2 | O agente registra a pergunta e a evidência já acumulada; o ticket entra em `awaiting_user` |
| 3 | O Solicitante responde |
| 4 | O sistema reenfileira a tarefa; o contexto da sessão está **no banco**, não em memória (RF43) |
| 5 | **Qualquer worker** disponível faz o lease e reconstrói o contexto a partir do registro |
| 5b | O agente retoma **sem repetir** as consultas já realizadas |
| 6 | O atendimento segue para UC-04 |

### Fluxos alternativos

**FA-12.1 — Sem resposta do solicitante**
→ Após o prazo configurado, o sistema conclui com a evidência disponível, declarando explicitamente a
lacuna (RF09), ou escala.

### Fluxos de exceção

**FE-12.1 — Resposta não esclarece**
→ O agente não insiste indefinidamente. Após uma segunda tentativa sem avanço, escala.

---

## UC-09 — Consultar API via camada de ferramentas *(caso de uso de inclusão)*

| | |
| :--- | :--- |
| **Tipo** | «include» — invocado por UC-01, UC-02, UC-03, UC-05 |
| **Ator secundário** | API Industrial TRACTIAN |
| **Objetivo** | Executar consulta ou ação na API industrial de forma rastreável |
| **Requisitos** | RF02, RF03, RF04, RF17 · RNF04, RNF07, RNF13 |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | O agente emite chamada de tool com nome e argumentos |
| 2 | O `ToolProvider` encaminha a chamada ao adaptador configurado (in-process por padrão) |
| 3 | O adaptador valida os argumentos contra o schema da tool **(RNF13)** |
| 4 | O executor traduz a chamada em requisição HTTP, incluindo o cabeçalho de identificação do usuário |
| 5 | O executor recebe a resposta da API |
| 6 | O `TraceEmitter` registra a chamada completa **(RNF07)** |
| 7 | O resultado retorna ao agente; se o envelope MCP estiver habilitado, o transporte é JSON-RPC |

### Fluxos de exceção

**FE-09.1 — Argumentos inválidos**
→ O adaptador retorna erro de validação **sem chamar a API**. O erro é observável pelo agente, que
pode corrigir.

**FE-09.2 — Falha transitória de rede**
→ Nova tentativa com recuo exponencial (RNF04). O trace registra todas as tentativas.

**FE-09.3 — Resposta fora do schema esperado**
→ O adaptador registra a divergência e repassa o retorno cru ao agente, sinalizando a anomalia. Não
descarta silenciosamente.

---

## UC-10 — Validar permissão *(caso de uso de inclusão)*

| | |
| :--- | :--- |
| **Tipo** | «include» — invocado por UC-05 |
| **Objetivo** | Confirmar que o usuário possui a permissão exigida pela ação |
| **Requisitos** | RF13 · RNF05 |

### Fluxo principal

| # | Ação |
| :-- | :--- |
| 1 | O sistema identifica a permissão exigida pela ação, conforme o `tier` do overlay |
| 2 | O sistema consulta o perfil do usuário corrente |
| 3 | O sistema verifica a presença da permissão no conjunto do perfil |
| 4 | O sistema retorna autorizado ou negado com o motivo |

### Fluxos de exceção

**FE-10.1 — Perfil não recuperável**
→ **Nega por padrão.** Na ausência de informação de permissão, a ação não é executada.

> *Fail closed*: a ausência de informação nunca é interpretada como autorização.

---

## 4. Rastreabilidade

### Casos de uso × chamados

| UC | TKT-CTX | TKT-INV | TKT-EXE | Total |
| :--- | :--- | :--- | :--- | ---: |
| UC-01 Contextualizar | 01, 02, 03 | — | — | 3 |
| UC-02 Investigar | — | 04, 05, 06, 09, 10, 11, 11b | — | 7 |
| UC-03 Reconciliar | 03 | 06, 07, 08 | — | 4 |
| UC-04 Decidir | todos | todos | todos | 17 |
| UC-05 Executar | — | 09 | 12, 13, 14, 15, 16 | 6 |
| UC-11 Receber ticket | todos | todos | todos | 17 |
| UC-12 Multi-turno | — | — | — | fluxo contínuo |

### Modos da API × fluxos de exceção

| Modo | Fluxos | Chamados |
| :--- | :--- | :--- |
| `complete` | fluxos principais | todos |
| `partial` | FE-01.1, FE-02.1, FE-03.2 | CTX-01, CTX-02, INV-07, INV-11b |
| `inconclusive` | FE-02.2 | INV-04 |
| `conflict` | UC-03, FE-03.1 | CTX-03, INV-06, INV-08 |
| `unavailable` | FE-01.2, FE-02.3 | INV-04 |
| `stale` | FE-02.4 | INV-09 |
| `pending` / `delayed` | FA-02.4 | INV-05 |

**Todos os sete modos probabilísticos possuem tratamento especificado.**
