# 03 — Requisitos

## Convenções

| Campo | Significado |
| :--- | :--- |
| **ID** | `RF##` funcional · `RNF##` não-funcional |
| **Prioridade** | `MUST` obrigatório · `SHOULD` importante · `COULD` desejável |
| **Verificação** | Como o cumprimento é comprovado |

> Todo RNF possui **critério de aceitação mensurável**. Requisito não-funcional sem número não é
> requisito — é intenção.

---

# Parte I — Requisitos Funcionais

## Bloco A — Interpretação e integração

### RF01 — Interpretar solicitação em linguagem natural
**Prioridade:** MUST

O sistema deve receber a mensagem do cliente em linguagem natural acompanhada do contexto
estruturado (`company_id`, `user_id`, `asset_id`) e determinar a intenção do chamado.

**Verificação:** os 17 chamados de `agent-input/cases.json` são processados sem erro de
interpretação.
**Origem:** US01–US17

---

### RF02 — Consultar a API industrial por camada MCP
**Prioridade:** MUST

O sistema deve acessar os 18 endpoints da API exclusivamente por tools expostas por um servidor MCP.
Nenhum componente do agente pode emitir requisição HTTP direta à API industrial.

**Verificação:** inspeção de código; toda chamada registrada no trace tem origem em `tools/call`.
**Origem:** US01–US17 · **Relacionado:** RNF06

---

### RF03 — Gerar tools a partir do contrato OpenAPI
**Prioridade:** MUST

O servidor MCP deve derivar nome, parâmetros e schema de cada tool a partir de
`api-contract.openapi.yaml`, sem definição manual por endpoint.

**Verificação:** o conjunto de tools expostas corresponde 1:1 aos `operationId` do contrato;
alteração no contrato reflete nas tools sem edição de código.
**Origem:** requisito de arquitetura · **Relacionado:** RNF06

---

### RF04 — Enriquecer tools com semântica de domínio por overlay
**Prioridade:** MUST

O sistema deve aplicar, sobre o contrato base, um arquivo de *overlay* declarativo contendo
descrição enriquecida, nível de impacto (`tier`) e política de uso de cada tool — sem modificar o
contrato original.

**Verificação:** o contrato base permanece byte-idêntico ao fornecido; as descrições efetivas das
tools contêm a semântica do overlay.
**Origem:** requisito de arquitetura · **Relacionado:** RF11, RNF06

---

### RF37 — Receber tickets por ponto de entrada contínuo
**Prioridade:** MUST

O sistema deve aceitar tickets de forma contínua por `POST /tickets`, respondendo imediatamente com
identificador e estado `queued`, sem bloquear até a conclusão do atendimento.

**Verificação:** submissão retorna em menos de 200 ms com `ticket_id`; o atendimento ocorre de forma
assíncrona.
**Origem:** US25 · **Relacionado:** RF38, RF39

---

### RF38 — Priorizar a fila por criticidade do ativo
**Prioridade:** MUST

Tickets devem ser atendidos em ordem de prioridade derivada da criticidade do ativo referenciado, e
não apenas por ordem de chegada.

**Verificação:** com fila não vazia, um ticket de ativo `critical` submetido depois é atendido antes
de um de ativo `low` submetido antes.
**Origem:** US26 · **Relacionado:** RF22

> A prioridade é **derivada**, não informada pelo cliente: vem do campo de criticidade do ativo na
> API. Deixar o solicitante escolher a própria prioridade faria todos escolherem a máxima.

---

### RF39 — Processar ticket e caso de suíte pelo mesmo caminho
**Prioridade:** MUST

Tarefas de tipo `ticket` e de tipo `experiment` devem ser processadas pelo **mesmo worker**, pelo
**mesmo código de agente** e produzir traces de **mesmo schema**, diferindo apenas na origem.

**Verificação:** teste automatizado confirma que o caminho de execução é idêntico; auditoria de
código não encontra ramo condicional por `kind` dentro do agente.
**Origem:** integridade experimental · **Relacionado:** RNF02

> **Este é o requisito que sustenta o enquadramento do projeto.** Se o caso da suíte percorresse um
> caminho diferente do ticket real, a avaliação mediria um sistema paralelo — e não o produto. É o
> que torna os 17 chamados uma suíte de regressão legítima.

---

### RF40 — Manter sessão multi-turno por ticket
**Prioridade:** SHOULD

Um ticket deve poder receber mensagens adicionais do solicitante. O agente retoma o atendimento com o
contexto da investigação anterior, sem reinvestigar o que já verificou.

**Verificação:** segunda mensagem no mesmo ticket produz trace que referencia evidências da primeira
sem repetir as chamadas correspondentes.
**Origem:** US27 · **Relacionado:** RF17

---

### RF41 — Solicitar informação adicional ao solicitante
**Prioridade:** SHOULD

Quando a investigação depender de informação que só o solicitante possui, o agente deve poder
suspender o atendimento, registrar a pergunta e retomar quando houver resposta.

**Verificação:** ticket entra em estado `awaiting_user`; a resposta reativa o atendimento.
**Origem:** US27 · **Relacionado:** RF40

> Cobre o modo **Contextualizar** do TAP — *"solicitar informações adicionais"* — que até aqui não
> tinha requisito próprio.

---

### RF43 — Manter o agente sem estado entre turnos
**Prioridade:** MUST

O agente **não** pode reter estado de sessão em memória entre turnos de um mesmo ticket. Todo contexto
— evidências já coletadas, pergunta pendente, decisão parcial — deve ser persistido. Ao retomar,
**qualquer worker** deve reconstruir o contexto a partir do registro de sessão.

**Verificação:** um ticket suspenso em `awaiting_user` é retomado por um worker **diferente** do que o
atendeu originalmente, com o contexto íntegro e sem repetir as consultas já feitas.
**Origem:** US27 · **Relacionado:** RF40, RF41, RNF19

> **Por que é MUST e não detalhe de implementação.** Um ticket pode ficar **horas** aguardando
> resposta do cliente. Se o agente segurasse o contexto no processo, o worker ficaria preso durante a
> espera — e com 5 workers e 5 tickets aguardando, o sistema inteiro travaria sem estar fazendo nada.
>
> É o tipo de erro que só aparece depois de implementado, e que obriga a reescrever o loop.

---

### RF42 — Expor console de atendimento
**Prioridade:** SHOULD

A interface deve apresentar a fila de tickets com estado, prioridade, tempo de espera e resolução,
permitindo abrir qualquer ticket e acompanhar ou inspecionar seu atendimento.

**Verificação:** todo estado de ticket é visível e navegável até o trace.
**Origem:** US25, US26 · **Relacionado:** RF30

---

## Bloco B — Disciplina de evidência

### RF05 — Verificar pré-condições antes de afirmar diagnóstico
**Prioridade:** MUST

Antes de emitir conclusão sobre um insight de `detection_mode = baseline`, o sistema deve **obter e
utilizar** o estado do baseline, a qualidade dos dados e o estado do modelo.

**Verificação:** a informação de pré-condição consta de algum retorno registrado no trace **antes**
da afirmação diagnóstica, e é referenciada em `evidence_cited`. A verificação é sobre a
**informação**, não sobre a tool chamada.
**Origem:** US05, US06, US09, US10 · **Relacionado:** hipótese H1, métricas M5a/M5b

> ⚠️ **A verificação não pode exigir chamada a `getBaseline`.** O endpoint `/assets/{id}/rms`
> já retorna `baseline_state`, `baseline_reference` e `alarm_threshold` no seu payload. Um agente
> que obtém a informação por essa via e raciocina corretamente está cumprindo o requisito. Exigir a
> tool específica mediria conformidade de trajetória, não disciplina de evidência.

---

### RF06 — Distinguir modo de detecção
**Prioridade:** MUST

O sistema deve tratar `detection_mode = symptom` de forma distinta de `detection_mode = baseline`,
não exigindo baseline `established` para validar detecção sintomática.

**Verificação:** TKT-INV-11b não é classificado como não-confiável por baseline em `learning`.
**Origem:** US12 · **Relacionado:** RF05

---

### RF07 — Derivar limiar de alarme exclusivamente do baseline
**Prioridade:** MUST

Ao explicar ou aplicar limiar de alarme de RMS, o sistema deve derivá-lo de
`baseline.features[].reference + tolerance` do ativo específico. É **vedado** derivar limiar de
norma ISO, tabela por classe de máquina ou conhecimento prévio do modelo.

**Verificação:** ausência de referência a norma genérica nas respostas; presença dos valores
numéricos do ativo. Verificado por assert programático sobre o texto da resolução.
**Origem:** US03 · **Relacionado:** RF10

---

### RF08 — Fundamentar toda afirmação técnica em evidência rastreável
**Prioridade:** MUST

Cada afirmação técnica na resolução deve referenciar um valor obtido de um retorno da API,
identificado por tool de origem e campo.

**Verificação:** toda entrada de `evidence_cited` corresponde a um valor presente em alguma
observação do trace (*grounding check* determinístico).
**Origem:** US03, US06, US08 · **Relacionado:** RF12

---

### RF09 — Declarar explicitamente informação não verificada
**Prioridade:** MUST

Quando um retorno for parcial, inconclusivo ou indisponível, o sistema deve registrar a lacuna em
campo próprio e refleti-la na resolução, sem preenchê-la por inferência.

**Verificação:** nos casos de modo `partial`, `inconclusive` e `unavailable`, o campo `unverified`
é não-vazio e a resolução menciona a limitação.
**Origem:** US04, US07, US10

---

### RF10 — Reconciliar fontes conflitantes
**Prioridade:** MUST

Diante de fontes divergentes, o sistema deve apresentar ambas com origem e confiança, buscar
evidência física de desempate e, na ausência dela, declarar o conflito como não resolvido.

**Verificação:** nos casos de modo `conflict`, ambas as fontes aparecem em `evidence_cited` e o
campo `conflicts` é não-vazio.
**Origem:** US03, US06, US08

---

## Bloco C — Decisão e ação

### RF11 — Classificar a resolução em orientar / agir / escalar
**Prioridade:** MUST

Toda execução deve terminar com uma resolução estruturada contendo decisão, justificativa e
evidências citadas, submetida por tool terminal dedicada.

**Verificação:** 100% das execuções concluídas produzem objeto de resolução válido segundo o schema.
**Origem:** US04, US06, US17 · **Relacionado:** RF08

---

### RF12 — Restringir ferramentas por nível de autoridade
**Prioridade:** MUST

Na arquitetura multi-agente, agentes de investigação devem receber exclusivamente tools de
`tier: read`. Tools de `tier: impact` devem ser expostas apenas ao agente executor.

**Verificação:** teste automatizado confirma que o conjunto de tools do agente investigador não
intersecta o conjunto `tier: impact`.
**Origem:** requisito de segurança · **Relacionado:** RNF05, hipótese H2

---

### RF13 — Validar permissão do usuário antes de ação
**Prioridade:** MUST

Antes de executar ação de impacto, o sistema deve verificar que o perfil do usuário possui a
permissão correspondente (`action_low`, `action_high` ou `escalate`).

**Verificação:** o trace contém consulta ao perfil precedendo toda tentativa de ação; ações sem
permissão não são tentadas.
**Origem:** US13, US15, US16, US17

---

### RF14 — Exigir confirmação explícita em ação de impacto
**Prioridade:** MUST

Ações marcadas `requires_confirmation` no overlay devem ser precedidas de confirmação explícita,
apresentando ação pretendida, justificativa e consequência.

**Verificação:** nenhuma tool `tier: impact` é executada sem evento de confirmação registrado
imediatamente antes no trace.
**Origem:** US13, US15, US16

---

### RF15 — Compor justificativa fundamentada em evidência
**Prioridade:** MUST

A justificativa de uma ação deve referenciar evidência coletada durante a investigação, não a
solicitação do cliente isoladamente.

**Verificação:** o campo de justificativa contém ao menos uma referência presente em
`evidence_cited`.
**Origem:** US16, US17

---

### RF16 — Aplicar política de parada
**Prioridade:** MUST

O sistema deve encerrar a execução ao atingir suficiência de evidência, **8 passos por agente** ou
orçamento de chamadas esgotado — registrando o motivo do encerramento.

**Verificação:** toda execução registra `stop_reason`; nenhuma excede o limite configurado.
**Origem:** requisito de robustez · **Relacionado:** RNF16

> ⚠️ **O valor 8 é decisão de orçamento, não de robustez.** O loop ReAct reenvia a conversa a cada
> passo, então o custo em tokens é quadrático: 12 passos custam ~94% mais que 8. Ver
> [`09-system-design.md`](./09-system-design.md), §2.1.

---

### RF33 — Manter homogeneidade de modelo entre papéis de agente
**Prioridade:** MUST

**Quando a arquitetura é a variável manipulada** (E1 e E2), todos os papéis de agente —
orquestrador, contextualizador, investigador e executor — devem usar o mesmo modelo, na mesma
configuração.

Heterogeneidade de modelo entre papéis só é admitida em comparação na qual a **arquitetura permanece
constante** (E4 / hipótese H4: braço B multi uniforme vs braço C multi heterogêneo).

**Verificação:** a configuração declara o braço; o runner valida que a combinação
(arquitetura, atribuição de modelo) corresponde a um braço previsto e aborta caso contrário. O
modelo efetivo de cada papel é registrado no trace.
**Origem:** validade experimental · **Relacionado:** RNF09, RNF15, hipóteses H1 e H4

> **Por quê.** A arquitetura mono tem um agente só — não há papéis a diferenciar, logo "mono
> heterogêneo" não existe. Comparar mono uniforme (A) com multi heterogêneo (C) mudaria arquitetura
> **e** modelo simultaneamente, e nenhuma análise posterior separaria os efeitos.
>
> | | Uniforme | Por papel |
> | :--- | :--- | :--- |
> | Mono | **A** | — não existe |
> | Multi | **B** | **C** |
>
> Comparações válidas: **A vs B** isola arquitetura · **B vs C** isola heterogeneidade.
> **A vs C** é ininterpretável e fica vedada.
>
> O **juiz** é exceção legítima: não integra o sistema medido, e ser distinto é exigência do RNF09.

---

## Bloco D — Rastreabilidade

### RF17 — Registrar trace estruturado completo
**Prioridade:** MUST

Cada execução deve produzir trace contendo, por passo: agente responsável, raciocínio, tool
invocada, argumentos, retorno, erro, latência e timestamp relativo.

**Verificação:** o número de entradas de trace corresponde ao número de chamadas efetuadas; schema
validado.
**Origem:** US22 · **Relacionado:** RNF07

---

### RF18 — Registrar handoffs entre agentes
**Prioridade:** MUST

Na arquitetura multi-agente, cada transferência entre agentes deve ser registrada com agente de
origem, destino e o objeto estruturado transferido.

**Verificação:** todo handoff no trace contém objeto válido segundo o schema de relatório.
**Origem:** US22 · **Relacionado:** hipótese H1

---

### RF19 — Transmitir eventos de execução em tempo real
**Prioridade:** SHOULD

O backend deve transmitir os eventos da execução ao front conforme ocorrem, permitindo
acompanhamento passo a passo.

**Verificação:** eventos chegam ao cliente em até 1s do evento real (RNF08).
**Origem:** US23

---

## Bloco E — Avaliação

### RF20 — Manter golden dataset versionado
**Prioridade:** MUST

O sistema deve manter um golden dataset com, por caso: entrada, trajetória esperada, decisão
esperada, evidências obrigatórias e afirmações vedadas.

**Verificação:** schema validado; os 17 casos base presentes e derivados do gabarito fornecido.
**Origem:** US18

---

### RF21 — Gerar casos derivados por variação controlada
**Prioridade:** SHOULD

O sistema deve gerar casos adicionais variando ativo, estado de baseline, modo de detecção e regime
de degradação, mantendo a resposta correta derivável por construção.

**Verificação:** cada caso gerado possui resposta esperada computada por regra explícita e
auditável, não por rotulação manual.
**Origem:** US18 · **Nota:** ampliação; o núcleo experimental não depende dela.

---

### RF22 — Executar runner paralelo e durável
**Prioridade:** MUST

O runner deve executar múltiplos casos concorrentemente, com limite configurável, e persistir
resultado por caso imediatamente após a conclusão.

**Verificação:** execução de N casos com concorrência C completa em tempo compatível com N/C.
**Origem:** US18 · **Relacionado:** RNF03

---

### RF23 — Retomar execução a partir de checkpoint
**Prioridade:** MUST

Ao reiniciar uma execução interrompida com o mesmo identificador, o runner deve pular os casos já
concluídos.

**Verificação:** interrupção deliberada seguida de reinício não reprocessa casos concluídos.
**Origem:** US19 · **Relacionado:** RNF03

---

### RF24 — Calcular métricas determinísticas
**Prioridade:** MUST

O sistema deve calcular, sem uso de LLM: cobertura de trajetória, ruído de chamadas, acurácia de
argumentos, acerto de decisão, ordem de verificação de pré-condições, taxa de falso "agir",
violação de permissão e estabilidade entre repetições.

**Verificação:** métricas reproduzem valores idênticos sobre o mesmo conjunto de traces.
**Origem:** US18, US21

---

### RF25 — Detectar alucinação de evidência
**Prioridade:** MUST

O sistema deve verificar programaticamente que toda evidência citada existe em algum retorno
registrado no trace, e detectar afirmações vedadas por regra.

**Verificação:** casos sintéticos com evidência forjada são detectados com 100% de acerto.
**Origem:** US03, US06 · **Relacionado:** RF07, RF08

---

### RF26 — Avaliar critérios subjetivos por rubrica binária
**Prioridade:** MUST

Critérios não verificáveis programaticamente devem ser avaliados por rubrica de critérios binários,
aplicada por LLM-as-judge, com veredito e justificativa por critério.

**Verificação:** cada avaliação produz vetor de vereditos booleanos com justificativa não-vazia.
**Origem:** US20 · **Relacionado:** RNF09

---

### RF27 — Executar meta-avaliação do juiz
**Prioridade:** SHOULD

O sistema deve permitir comparar os vereditos do juiz com rotulação humana sobre uma amostra e
reportar a concordância por critério.

**Verificação:** relatório de concordância com acurácia e coeficiente kappa por critério.
**Origem:** US20

---

### RF28 — Comparar arquiteturas sobre o mesmo conjunto
**Prioridade:** MUST

O sistema deve executar arquiteturas distintas sobre o mesmo golden dataset e produzir comparação
agregada e por caso.

**Verificação:** relatório comparativo com diferença por métrica e identificação dos casos
divergentes.
**Origem:** US24 · **Relacionado:** hipótese H1

---

## Bloco F — Interface

### RF34 — Recomputar métricas sobre traces persistidos
**Prioridade:** MUST

O cálculo de métricas deve ser função pura de `(trace, caso do gabarito, versão da métrica)`, sem I/O
nem estado externo, permitindo recomputação a qualquer momento sem reexecutar o agente.

**Verificação:** alterar a definição de uma métrica e recomputar produz resultados novos em segundos;
os valores anteriores permanecem acessíveis sob a versão antiga.
**Origem:** US18 · **Relacionado:** RF24, RNF15

> Durante o desenvolvimento, definições de métrica mudam — M5 já mudou uma vez. Se o cálculo
> dependesse de reexecução, cada correção custaria dias de cota.

---

### RF35 — Registrar aplicabilidade distinta de valor zero
**Prioridade:** MUST

Toda métrica e todo critério de rubrica deve registrar explicitamente se **se aplica** àquela
execução. Não aplicável nunca pode ser representado como zero.

**Verificação:** M14 em execuções mono retorna `applicable = 0`, não `value = 0`. Agregações filtram
por aplicabilidade antes de somar.
**Origem:** validade experimental · **Relacionado:** RF24, RF26

> Colapsar "não aplicável" em zero criaria vantagem artificial para a arquitetura mono na agregação
> de M14, e penalizaria o comportamento correto em casos de detecção sintomática.

---

### RF36 — Cachear julgamentos por versão
**Prioridade:** MUST

Julgamentos devem ser identificados por `(execução, critério, versão da rubrica, modelo juiz)`.
Rejulgar a mesma combinação não deve consumir cota.

**Verificação:** reexecutar o julgamento sobre execuções já julgadas com a mesma rubrica e o mesmo
juiz não emite requisições.
**Origem:** US20 · **Relacionado:** RF26, RNF11

---

### RF29 — Submeter chamado pela interface
**Prioridade:** SHOULD

A interface deve permitir selecionar um caso do dataset ou compor mensagem livre com contexto, e
disparar a execução.

**Verificação:** execução iniciada pela interface produz trace equivalente ao da execução por CLI.
**Origem:** US23

---

### RF30 — Inspecionar trajetória na interface
**Prioridade:** SHOULD

A interface deve exibir a trajetória passo a passo, com agente responsável, tool, argumentos,
retorno, latência, pré-condições verificadas e pontos de handoff.

**Verificação:** todo campo do trace é acessível pela interface sem consulta a arquivo.
**Origem:** US22

---

### RF31 — Exibir dashboard de resultados
**Prioridade:** SHOULD

A interface deve apresentar métricas agregadas com filtros por arquitetura, modelo, regime de
degradação e modalidade, permitindo descer ao caso individual.

**Verificação:** valores exibidos correspondem aos calculados pela suíte.
**Origem:** US18, US24

---

### RF32 — Comparar execuções lado a lado
**Prioridade:** COULD

A interface deve exibir duas execuções do mesmo caso em paralelo, destacando divergências de
decisão e de evidência.

**Verificação:** divergências destacadas correspondem às apontadas pela suíte.
**Origem:** US24

---

# Parte II — Requisitos Não-Funcionais

## Confiabilidade e reprodutibilidade

### RNF01 — Reprodutibilidade de execução
**Prioridade:** MUST · **Categoria:** Reprodutibilidade

Execuções com mesmo caso, modelo, `temperature = 0` e `seed` fixo da API devem produzir a mesma
trajetória.

**Critério de aceitação:** ≥ 95% de trajetórias idênticas em 10 repetições controladas. Desvios
residuais atribuíveis ao não-determinismo do provedor devem ser registrados e quantificados.
**Verificação:** teste de reprodutibilidade em suíte automatizada.

---

### RNF02 — Isolamento do gabarito
**Prioridade:** MUST · **Categoria:** Integridade experimental

Nenhum conteúdo de `eval/`, `docs/test-scenarios.md` ou `data/cases.parquet` pode entrar no contexto
do agente, em qualquer forma — prompt, tool, resource ou arquivo lido.

**Critério de aceitação:** teste automatizado que falha o build caso o processo do agente acesse
esses caminhos. Zero ocorrências toleradas.
**Verificação:** teste de isolamento em CI local; auditoria do trace.

> Este é o requisito mais crítico do projeto. Sua violação invalida todos os resultados.

---

### RNF03 — Durabilidade da execução
**Prioridade:** MUST · **Categoria:** Robustez

O runner deve sobreviver a falhas de rede, rate limit e interrupção de processo sem perda de
trabalho concluído.

**Critério de aceitação:** após interrupção em qualquer ponto, o reinício reprocessa no máximo 1
caso (o que estava em curso). Resultados concluídos: 0 perdas.
**Verificação:** teste de interrupção deliberada em três pontos distintos da execução.

---

### RNF04 — Tolerância a falha transitória
**Prioridade:** MUST · **Categoria:** Robustez

Falhas transitórias do provedor de LLM (429, 5xx, timeout) devem ser tratadas com nova tentativa e
recuo exponencial, sem propagar erro ao resultado do caso.

**Critério de aceitação:** até 5 tentativas com recuo exponencial; caso só é marcado como falho após
esgotamento. Falhas de infraestrutura registradas separadamente das falhas de comportamento do
agente.
**Verificação:** injeção de falha simulada na camada de cliente.

---

### RNF05 — Menor privilégio por agente
**Prioridade:** MUST · **Categoria:** Segurança

Cada agente deve receber exclusivamente as tools necessárias ao seu papel, determinadas pelo `tier`
do overlay.

**Critério de aceitação:** interseção entre o conjunto de tools do agente investigador e o conjunto
`tier: impact` é vazia. Verificado em tempo de inicialização, com falha imediata em caso de
violação.
**Verificação:** teste automatizado de composição de tools.

---

## Portabilidade e manutenção

### RNF06 — Portabilidade do contrato
**Prioridade:** MUST · **Categoria:** Arquitetura

Integrar o sistema a outra API deve exigir apenas um novo contrato OpenAPI e um novo overlay, sem
alteração no núcleo do servidor MCP nem na lógica dos agentes.

**Critério de aceitação:** o núcleo genérico não contém nenhuma referência textual a conceito de
domínio da TRACTIAN (`baseline`, `rms`, `spectrum`, `asset`). Verificado por varredura de código.
**Verificação:** demonstração com um segundo contrato OpenAPI arbitrário gerando tools válidas.

---

### RNF07 — Observabilidade integral
**Prioridade:** MUST · **Categoria:** Rastreabilidade

Toda interação com a API industrial e com o provedor de LLM deve ser registrada em trace
estruturado.

**Critério de aceitação:** 100% de cobertura — nenhuma chamada ocorre fora do trace. Verificado por
contagem cruzada entre chamadas efetuadas e entradas registradas.
**Verificação:** auditoria automática de cobertura de trace.

---

## Desempenho

### RNF08 — Latência de streaming
**Prioridade:** SHOULD · **Categoria:** Desempenho

Eventos de execução devem chegar à interface em até 1 segundo do momento em que ocorrem no backend.

**Critério de aceitação:** p95 ≤ 1000 ms medido entre timestamp do evento e recepção no cliente.
**Verificação:** medição instrumentada em execução de demonstração.

---

### RNF09 — Independência do juiz
**Prioridade:** MUST · **Categoria:** Validade experimental

O modelo utilizado como juiz deve ser distinto do modelo utilizado como agente, para evitar viés de
auto-preferência.

**Critério de aceitação:** identificadores de modelo distintos, verificados em tempo de execução com
falha imediata em caso de coincidência.
**Verificação:** asserção na inicialização da suíte de avaliação.

---

### RNF10 — Neutralidade de ordem na comparação
**Prioridade:** SHOULD · **Categoria:** Validade experimental

Comparações pareadas entre arquiteturas devem neutralizar viés de posição.

**Critério de aceitação:** toda comparação pareada é executada nas duas ordens e o resultado é a
média; divergência entre ordens é reportada como medida de viés.
**Verificação:** relatório de comparação inclui métrica de assimetria de ordem.

---

### RNF11 — Custo de execução
**Prioridade:** MUST · **Categoria:** Viabilidade

A execução completa do experimento deve caber nos limites da camada gratuita do provedor.

**Critério de aceitação:** consumo total registrado e mantido dentro da cota; contabilização de
tokens por execução disponível no relatório.
**Verificação:** relatório de consumo por execução.

---

### RNF17 — Coordenação entre processos sem perda de estado durável
**Prioridade:** MUST · **Categoria:** Robustez

A coordenação entre processos — transmissão de eventos, controle de taxa compartilhado e contagem de
cota — deve ocorrer em camada **efêmera**, separada do estado durável. A indisponibilidade dessa
camada pode degradar funcionalidade operacional, mas nunca causar perda de dado experimental.

**Critério de aceitação:** com a camada de coordenação indisponível, a execução prossegue e os traces
continuam sendo persistidos; apenas o streaming ao vivo é interrompido. Zero perda em `queue.db`,
`traces/` ou `metrics`.
**Verificação:** teste com a camada efêmera derrubada durante uma rodada.

---

### RNF18 — Latência de aceitação de ticket
**Prioridade:** MUST · **Categoria:** Desempenho

A submissão de um ticket deve ser confirmada sem aguardar o atendimento.

**Critério de aceitação:** p95 ≤ 200 ms entre `POST /tickets` e resposta `202`, independentemente da
profundidade da fila.
**Verificação:** medição sob fila carregada.

---

### RNF19 — Continuidade sob pico de entrada
**Prioridade:** MUST · **Categoria:** Robustez

Entrada de tickets acima da capacidade de processamento não pode causar perda nem degradação do
atendimento em curso.

**Critério de aceitação:** com entrada 10× acima da vazão, zero tickets perdidos; a fila cresce e é
drenada na ordem de prioridade. A profundidade é observável no console.
**Verificação:** teste de carga com submissão em rajada.

> A vazão do sistema é limitada pela cota do provedor — cerca de 187 tickets/dia na camada gratuita.
> Acima disso, o gargalo não é a fila: é o contrato com o provedor. A fila decide **quando**
> processar, não **quanto**.

---

### RNF16 — Guarda de cota diária com retomada
**Prioridade:** MUST · **Categoria:** Viabilidade

O runner deve interromper a alocação de trabalho ao aproximar-se do teto diário de requisições do
provedor, e retomar automaticamente do ponto exato no ciclo seguinte.

**Critério de aceitação:** zero requisições emitidas além da cota diária; ao retomar, nenhuma task
concluída é reprocessada. Esgotamento de cota é classificado como `budget` e **não** incrementa o
contador de tentativas da task.
**Verificação:** teste com cota artificialmente reduzida; conferência de que a retomada preserva o
estado.

---

### RNF12 — Tempo de execução da suíte
**Prioridade:** SHOULD · **Categoria:** Desempenho

A suíte completa sobre o dataset base deve concluir em tempo compatível com iteração de
desenvolvimento.

**Critério de aceitação:** o núcleo experimental (E1 + E4 + E2 + E3 = 1.021 execuções) concluído em
≤ 6 dias corridos, à vazão de 187 execuções/dia imposta pela cota do provedor.
**Verificação:** medição em execução completa; consumo diário registrado.

> ⚠️ **A concorrência não determina a vazão.** O token bucket regula a taxa global na cota do
> provedor (ADR-09): 3 workers ou 8 produzem os mesmos 15 RPM. Os workers existem apenas para
> sobrepor latência de I/O. O teto que morde é o de requisições diárias.

---

## Qualidade de código e documentação

### RNF13 — Validação de contratos de dados
**Prioridade:** MUST · **Categoria:** Qualidade

Todos os objetos trafegados entre componentes — argumentos de tool, relatórios de handoff,
resoluções, entradas de trace — devem ser validados por schema tipado.

**Critério de aceitação:** zero objetos não validados nas fronteiras entre componentes. Falha de
validação é erro explícito, nunca silencioso.
**Verificação:** inspeção de código; testes de validação com objetos malformados.

---

### RNF14 — Reprodutibilidade de ambiente
**Prioridade:** MUST · **Categoria:** Reprodutibilidade

Um terceiro deve conseguir executar a solução de ponta a ponta a partir da documentação, em ambiente
limpo.

**Critério de aceitação:** dependências fixadas com versão; instruções executadas em ambiente limpo
sem intervenção manual além da configuração de credencial.
**Verificação:** execução de validação em ambiente limpo antes da entrega.

---

### RNF15 — Registro de configuração experimental
**Prioridade:** MUST · **Categoria:** Reprodutibilidade

Toda execução deve registrar modelo, versão, temperatura, seed, versão do overlay, arquitetura e
identificador do dataset.

**Critério de aceitação:** todo resultado é reconstituível a partir dos metadados registrados, sem
consulta a informação externa.
**Verificação:** validação de completude de metadados na suíte.

---

# Parte III — Resumo

## Contagem

| Categoria | MUST | SHOULD | COULD | Total |
| :--- | ---: | ---: | ---: | ---: |
| Funcionais | 32 | 10 | 1 | **43** |
| Não-funcionais | 16 | 3 | 0 | **19** |
| **Total** | **51** | **13** | **1** | **62** |

## RNF por categoria

| Categoria | Requisitos |
| :--- | :--- |
| Reprodutibilidade | RNF01, RNF14, RNF15 |
| Integridade experimental | RNF02 |
| Robustez | RNF03, RNF04, RNF17, RNF19 |
| Segurança | RNF05 |
| Arquitetura | RNF06 |
| Rastreabilidade | RNF07 |
| Desempenho | RNF08, RNF12, RNF18 |
| Validade experimental | RNF09, RNF10 |
| Orçamento | RF16, RF33 |
| Viabilidade | RNF11, RNF16 |
| Qualidade | RNF13 |

## Requisitos de maior risco

| ID | Requisito | Risco |
| :--- | :--- | :--- |
| RNF02 | Isolamento do gabarito | Violação invalida todos os resultados do projeto |
| RF05 | Verificação de pré-condições | É o objeto da hipótese central — sem ele não há experimento |
| RNF03 | Durabilidade | Sem checkpoint, rate limit inviabiliza execuções longas (RSC-01) |
| RF12 | Restrição por autoridade | Base da garantia estrutural de segurança (hipótese H2) |
| RF33 | Braços de modelo válidos | Comparar A vs C tornaria H1 impossível de interpretar |
| RNF16 | Guarda de cota | Sem ela o experimento estoura a cota e para por dias |
| RF39 | Caminho único ticket/suíte | Se divergirem, a avaliação mede um sistema paralelo, não o produto |
| RF43 | Agente sem estado entre turnos | Violação prende workers durante a espera e trava o sistema |
