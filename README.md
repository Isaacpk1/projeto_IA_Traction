# Engenharia e Avaliação de Agentes Industriais

**Parceiro:** TRACTIAN · **Instituição:** Inteli · **Autor:** Isaac Nicolas Alves da Silva
**Período:** 13/08/2026 – 08/09/2026 · **Formato:** projeto individual

**Plataforma de suporte técnico industrial** sobre a API da TRACTIAN — recebe tickets continuamente,
investiga com agentes de IA e decide entre orientar, agir ou escalar — acompanhada do **arnês de
avaliação** que mede sua confiabilidade.

> Os 17 chamados fornecidos pela TRACTIAN são a **suíte de regressão** do produto, não o escopo dele.
> O mesmo worker que processa um ticket de cliente processa um caso da suíte, pelo mesmo caminho de
> código (RF39) — é isso que garante que a avaliação mede o sistema real.

> **Status em 27/08/2026:** fundação, tools, núcleo mono-agente e infraestrutura determinística da
> Fase 3 implementados; a validação ponta a ponta com Gemini/API local e o Langfuse seguem pendentes.
> Cronograma, estratégia de testes e plano de contingência em
> [`docs/14-roadmap-e-testes.md`](docs/14-roadmap-e-testes.md).
> As seções de **Resultados** estão marcadas como pendentes e serão preenchidas após a execução dos
> experimentos.

**Implementado agora:** contratos e portas do núcleo, fakes de teste, invariantes arquiteturais,
camada OpenAPI, agente mono, adaptador Gemini com rate limit, trace JSONL, fila SQLite com lease,
worker único, guarda de isolamento e guardrails pré-ação/pré-entrega. **Próximo marco local:** golden
dataset e métricas; em paralelo continuam pendentes Gemini/API local e o sink do Langfuse. A
estrutura completa descrita abaixo é a arquitetura-alvo, não uma alegação de que todos os
componentes já existem.

---

## 1. Problema considerado e recorte da solução

### O problema

A TRACTIAN monitora a condição de máquinas industriais. Sensores coletam vibração; modelos emitem
diagnósticos de falha incipiente. Quando um cliente questiona um diagnóstico, reclama de um alerta
que não veio, ou pede uma ação na plataforma, um analista de suporte precisa reconstruir toda a
investigação antes de responder.

Essa investigação é estruturada e intensiva em consulta — perfil ideal para um agente com
ferramentas. Mas o desafio real **não é** conectar um LLM a uma API. É que:

- **O conhecimento genérico do modelo está errado neste domínio.** Um LLM "sabe" que a ISO 10816
  define limiares de vibração por classe de máquina. Aqui isso é falso: o limiar deriva do baseline
  aprendido do próprio ativo.
- **A evidência tem pré-condições.** Um insight só é confiável se as condições em que foi gerado
  eram válidas — e o insight não anuncia isso.
- **A informação frequentemente é incompleta.** A API retorna, por desenho, dados completos,
  parciais, inconclusivos, conflitantes ou indisponíveis. O comportamento correto diante de uma
  lacuna é declará-la, não preenchê-la.
- **Algumas ações são irreversíveis.** Agir quando se deveria orientar é o erro mais caro do sistema.

### O recorte

**Contexto de uso declarado:** *fluxo autônomo com escopo definido* — dos três modos que o TAP
admite. Tickets chegam por API ou interface, entram numa fila priorizada por criticidade do ativo, e
são atendidos por agentes que investigam sozinhos até a resolução, com escalonamento humano como
saída explícita. Ações de impacto exigem confirmação.

**Três partes interdependentes:**

1. **Atendimento** — ingestão contínua, fila durável com prioridade derivada, sessão multi-turno,
   console de operação.
2. **Agentes** — camada de tools gerada do contrato OpenAPI com overlay de domínio; envelope MCP
   opcional; duas arquiteturas
   comparáveis (mono-agente ReAct e multi-agente especializado).
3. **Avaliação** — golden dataset formalizado, runner durável, métricas determinísticas, rubrica
   binária com LLM-as-judge validado por meta-avaliação.

### Por que produto, e por que isso fortalece o experimento

As hipóteses deixam de ser perguntas acadêmicas e viram **decisões que quem coloca um agente em
produção precisa tomar**:

| Hipótese | Como decisão de produto |
| :--- | :--- |
| **H1** mono vs multi | *Que arquitetura eu coloco em produção?* |
| **H2** garantia estrutural | *Como impeço uma ação indevida antes de qualquer efeito externo?* |
| **H4** modelo por papel | *Quanto economizo baixando o modelo nos papéis fáceis?* |

### Hipótese central

> Isolamento de contexto por especialização de agentes reduz o erro de investigação em casos de
> evidência degradada ou conflitante, mas introduz perda de informação na fronteira de handoff. O
> saldo é positivo quando o handoff é estruturado, e a vantagem da arquitetura multi **cresce com a
> intensidade da degradação** — uma relação dose-resposta, não um contraste binário.

Três hipóteses complementares tratam de **garantia estrutural versus instrução** (H2),
**enriquecimento semântico de ferramentas** (H3) e **especialização de modelo por papel** (H4).
Detalhamento em [`docs/07-plano-experimental.md`](docs/07-plano-experimental.md); o catálogo completo
de experimentos possíveis, com custo e valor, em
[`docs/10-matriz-de-experimentos.md`](docs/10-matriz-de-experimentos.md).

---

## 2. Arquitetura

### Visão geral

```
Ticket (API · interface)      Suíte de regressão (17 chamados)
         │                                  │
         └──────────────┬───────────────────┘
                        ▼
        Fila durável · prioridade por criticidade · lease
                        ▼
                     Workers
                        ▼
   Agentes  ── mono-agente ReAct │ multi-agente especializado
                        ▼
   Camada de tools ── núcleo genérico (OpenAPI→tools) + overlay
                        ▼
              API Industrial TRACTIAN
                        ▼
        Resolução: orientar · agir · escalar
                        ▼
                Trace estruturado
                        ▼
   Análise ── métricas · juiz · estatística → console e dashboard
```

**O ponto que define a arquitetura:** ticket de cliente e caso da suíte entram na **mesma fila** e
percorrem o **mesmo código**. A suíte exercita o caminho de produção — não um caminho paralelo
construído para ser medido.

### Arquitetura multi-agente

```
              ┌─────────────────────────┐
              │  ORQUESTRADOR           │
              │  sem tools da API       │
              │  roteia · consolida     │
              └───┬───────┬──────────┬──┘
   handoff tipado │       │          │
      ┌───────────┘       │          └───────────┐
      ▼                   ▼                      ▼
┌──────────────┐  ┌────────────────┐  ┌────────────────┐
│CONTEXTUALIZA-│  │  INVESTIGADOR  │  │    EXECUTOR    │
│     DOR      │  │                │  │                │
│ tier: read   │  │  tier: read    │  │ tier: impact   │
│ conhecimento │  │  ativos        │  │ reprocessar    │
│ glossário    │  │  análises      │  │ especialista   │
│ contexto     │  │  baseline      │  │ retreinamento  │
│              │  │  rms/espectro  │  │ config técnica │
│              │  │  qualidade     │  │ escalar        │
│              │  │  modelos       │  │                │
└──────────────┘  └────────────────┘  └────────────────┘
 Contextualizar      Investigar            Executar
```

**Garantia estrutural.** O Investigador **não possui** tools de impacto em seu schema. Não é uma
instrução que ele possa desobedecer — é uma capacidade que ele não tem. Validado na inicialização;
interseção não-vazia aborta o processo.

### Organização do código

**Monolito modular com múltiplos pontos de entrada**, em estilo **hexagonal** (portas e adaptadores)
com *shared kernel*. Módulos são fatias verticais por capacidade — `tools/`, `agents/`,
`evaluation/`, `analysis/` — não camadas técnicas.

A regra de dependência (`core/` não importa nada; módulos não se importam lateralmente; só
`interfaces/` compõe) é verificada por teste, não por disciplina.

### Camada de tools em duas camadas

```
┌────────────────────────────────────────────────┐
│  OVERLAY (domínio)                             │
│  descrição semântica · tier · confirmação      │
│  permissão requerida · pré-condições           │
└──────────────────┬─────────────────────────────┘
                   │ merge na inicialização
┌──────────────────▼─────────────────────────────┐
│  NÚCLEO GENÉRICO (zero domínio)                │
│  parser OpenAPI · fábrica de tools             │
│  executor HTTP · retry · emissor de trace      │
└────────────────────────────────────────────────┘
```

Integrar outra API exige um novo contrato e um novo overlay — o núcleo não muda. A camada funciona
como biblioteca Python; o envelope MCP é um adaptador opcional (ADR-01).

Detalhamento completo, C4 e decisões arquiteturais registradas em
[`docs/05-arquitetura.md`](docs/05-arquitetura.md).

---

## 3. Instalação e execução

### O que funciona no estado atual

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check src tests
uv run mypy src
uv run lint-imports
```

Os testes da camada de tools usam o contrato fornecido pela TRACTIAN. Por padrão, ele é procurado
em `../api_traction/inteli-tractian-project/agent-input/api-contract.openapi.yaml`; outro caminho
pode ser informado por `TRACTIAN_CONTRACT_PATH`. Os cinco testes contra a API real são ignorados
quando `TRACTIAN_API_URL` não está disponível.

### Execução ponta a ponta planejada

> Os comandos desta subseção descrevem o estado-alvo e **ainda não funcionam**, porque agente,
> runner, Compose, backend e frontend pertencem às próximas fases do roadmap.

#### Pré-requisitos do estado-alvo

- Python ≥ 3.11
- [`uv`](https://docs.astral.sh/uv/)
- Node.js ≥ 20 (interface)
- Chave da [Google AI Studio](https://aistudio.google.com/) — modelo do agente
- Chave da [Groq](https://console.groq.com/) — modelo juiz
- Chave da [OpenRouter](https://openrouter.ai/) — eixo H3 (opcional)
- API industrial da TRACTIAN em execução (repositório `inteli-tractian-project`)

#### Passo 1 — subir a API industrial

```bash
cd ../inteli-tractian-project
make setup
make up            # http://localhost:8000/docs
```

#### Alternativa — subir tudo com Docker

```bash
docker compose up          # API + backend + front + Langfuse
```

O Compose sobe também o **Langfuse** (`http://localhost:3000`), onde cada execução do agente aparece
como um trace navegável — passo a passo, tokens, custo e score do juiz. Ele é **opcional**: o trace
canônico é gravado em JSONL no disco e nada depende do serviço estar de pé (ADR-14).

#### Passo 2 — configurar este projeto

```bash
uv sync
cp .env.example .env
# editar .env: GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY,
#              TRACTIAN_API_URL, AGENT_MODEL, JUDGE_MODEL
```

#### Passo 3 — atender um chamado

```bash
uv run python -m agent.cli --case case_tkt_inv_06 --architecture multi
```

#### Passo 4 — executar a suíte de avaliação

```bash
uv run python -m evaluation.runner --experiment e1 --repetitions 2
uv run python -m evaluation.analysis --run-id <id>
```

O runner é uma **fila durável com lease**: interromper a qualquer momento e reexecutar o mesmo
comando retoma exatamente de onde parou, sem reprocessar casos concluídos. Ao atingir o teto diário
do provedor, ele pausa sozinho e prossegue no ciclo seguinte.

#### Passo 5 — interface web

```bash
uv run uvicorn backend.main:app --reload    # backend
cd frontend && npm install && npm run dev   # front → http://localhost:5173
```

O front tem **três telas**, e a divisão de trabalho com o Langfuse é deliberada:

| Onde | Responde |
| :--- | :--- |
| **Console de atendimento** (front) | fila de chamados, status, resolução entregue, veredito do guardrail |
| **Chat multi-turno** (front) | conversa com o agente sobre um chamado, com streaming |
| **Dashboard de hipóteses** (front) | M1–M16 por braço, curva dose-resposta, veredito de H1–H4 |
| **Langfuse** (link por execução) | **por que** o agente decidiu — spans, argumentos de cada tool, tokens, custo |

O front mostra *o que o sistema faz* e *o que o experimento concluiu*; o Langfuse mostra *como o
agente raciocinou*. Reimplementar inspeção de trace no front seria mais de um dia de trabalho para
entregar algo pior — ver [`14`](docs/14-roadmap-e-testes.md) §3.

---

## 4. Modelos e configurações

| Papel | Provedor | Modelo | Cota | Vazão |
| :--- | :--- | :--- | :--- | ---: |
| **Agente** (todos os papéis) | Google AI Studio | Gemini 2.5 Flash · `temp = 0` · até 8 passos por agente | validar na conta | definida pelo piloto |
| **Juiz** | Groq | modelo configurado, distinto do agente (RNF09) | validar na conta | definida pelo piloto |
| **Eixo H3** | OpenRouter | modelo aberto `:free` | validar na conta | amostra condicionada ao orçamento |

> **RF33 — homogeneidade de modelo.** Todos os papéis de agente usam o **mesmo** modelo em E1.
> Heterogeneidade entre papéis tornaria impossível separar o efeito da arquitetura do efeito do
> modelo. O juiz é exceção legítima: não integra o sistema medido.

**Por que Gemini.** É o candidato inicial por disponibilidade de tool calling e cota, não por
preferência. O piloto mede os limites efetivos antes de confirmar a escolha ou o cronograma.
Registrado como limitação L12 — o TAP cita modelos abertos como referência de viabilidade, e Gemini
é opção gratuita, não aberta; o eixo H3 cobre parcialmente essa dimensão.

Modelo/versão/provedor por agente, temperatura, seed, braço, prompt, overlay, contrato, dataset e
commit são gravados em cada trace (RNF15). Isso identifica a configuração e permite recomputar as
métricas; não promete que um provedor remoto reproduzirá a mesma saída do LLM no futuro.

### Configuração experimental

| Variável | Níveis |
| :--- | :--- |
| Arquitetura | `mono` · `multi` |
| Degradação | 1 âncora (`seed=complete`) + 7 seeds distintos — permite análise dose-resposta |
| Overlay | `raw` · `enriched` (H3) |
| Repetições | 2 por célula |
| Passos por agente | 8 (decisão de orçamento — custo do ReAct é quadrático) |

---

## 5. Metodologia experimental

### Desenho

**E1 — Arquitetura (H1):** 2 arquiteturas × 8 configurações de seed × 17 casos × 2 repetições =
**544 execuções**. O efeito de interesse é **dose-resposta**: H1 prevê que a vantagem da arquitetura
multi **cresça** conforme a intensidade de degradação aumenta. Um contraste binário mostraria que
existe diferença; dose-resposta mostra que a diferença acompanha a causa proposta.

> A API é **determinística em todos os regimes** — verificado no código-fonte (`api/app/prob.py`).
> Isso permite usar seeds distintos como níveis de uma variável contínua, em vez de um fator binário,
> multiplicando o poder estatístico sem custo adicional.

**E2 — Segurança (H2):** 5 casos adversariais × 2 políticas × 5 repetições = **50 execuções**.
Compara `prompt_only` e `pre_action_guard` mantendo arquitetura e modelo constantes. O primeiro braço
é obrigatoriamente dry-run; mede tentativas inseguras sem produzir efeitos externos.

**E4 — Especialização de modelo (H4, condicional):** braço B (multi uniforme) vs braço C (multi com Flash-Lite nos
papéis fáceis) = **272 execuções**. A arquitetura é mantida constante — é isso que torna o resultado
interpretável. Comparar mono uniforme com multi heterogêneo mudaria duas variáveis ao mesmo tempo.

**E3 — Overlay (H3):** amostra, ~130 execuções.

**Núcleo obrigatório: 594 execuções. Máximo condicional: 996.** O prazo é calculado após o piloto,
com o p95 real de chamadas por execução de cada braço.

### Pirâmide de avaliação

```
        ╱  LLM-as-judge   ╲   DeepEval GEval · rubrica binária, 8 critérios
      ╱   programático     ╲  ancoragem, afirmações vedadas
    ╱    determinístico     ╲ trajetória, argumentos, decisão
```

O nível determinístico cobre 7 dos 9 objetos de análise do enunciado sem custo nem ruído. O juiz é
reservado ao que é genuinamente subjetivo.

### Defesa em camadas — e onde o juiz NÃO está

| Mecanismo | Quando age | Garantia | Bloqueia entrega? |
| :--- | :--- | :--- | :--- |
| Composição por `tier` | antes | reduz a capacidade por papel | — |
| Instrução no prompt | durante | probabilística | — |
| **`PreActionGuard`** | **antes do efeito externo** | **determinística — valida RF13–RF15** | **bloqueia a ação** |
| **`PreDeliveryGuard` (RF44)** | **antes da resposta** | **determinística — V1–V3** | **sim** |
| Juiz LLM | fora do caminho | mede, não protege | **nunca** |

O juiz avalia **depois da execução, em lote**. Pô-lo no caminho de entrega custaria latência, cortaria
a vazão pela metade e — decisivo — faria H1 medir *agente + juiz* em vez da arquitetura do agente.

Uma **quarta camada** está desenhada e fora do escopo: um agente adversarial que, antes de uma ação
de impacto, investiga o mesmo caso instruído a **refutar** a conclusão. Ataca o modo de falha central
do domínio — confirmação — e é a única camada independente do primeiro julgamento. Catalogada como
**E-A6** ([`10`](docs/10-matriz-de-experimentos.md)) e priorizada como extra em
[`14`](docs/14-roadmap-e-testes.md) §8.

### Controles metodológicos

| Controle | Mecanismo |
| :--- | :--- |
| Braços de modelo válidos | Modelo uniforme quando arquitetura varia; arquitetura constante quando o modelo varia (RF33) |
| Comparações múltiplas | Predições escritas antes da execução; uma métrica primária por hipótese; todas reportadas |
| Separação infra × comportamento | Taxonomia de falhas; só `behavior` conta como resultado |
| Isolamento do gabarito | `IsolationGuard` bloqueante — aborta a suíte em caso de violação |
| Auto-preferência do juiz | Modelo do juiz ≠ modelo do agente, verificado em execução |
| Viés de posição | Comparações pareadas nas duas ordens; assimetria reportada |
| Não-determinismo | `temperature = 0` + N repetições; variância do modelo separada da variância da API |
| Validação do juiz | Meta-avaliação contra rotulação humana cega em 30 execuções; kappa por critério |

> A rotulação humana é feita **antes** de ver os resultados agregados, para evitar viés de
> confirmação na própria régua de validação.

Detalhamento completo em [`docs/07-plano-experimental.md`](docs/07-plano-experimental.md).

---

## 6. Resultados

> ⏳ **Pendente de execução.**

Estrutura prevista do relatório:

| Seção | Conteúdo |
| :--- | :--- |
| 1 | Configuração executada: modelos, versões, contagens, cota consumida |
| 2 | Meta-avaliação do juiz: kappa por critério; critérios excluídos |
| 3 | E1 — resultados por métrica, arquitetura e regime; teste de cada predição de H1 |
| 4 | E2 — taxa de tentativa insegura e bloqueios pré-ação; teste de H2 |
| 5 | E3 — se executado; se não, registro explícito da não-execução |
| 6 | E4 — se executado; não-inferioridade e custo por papel para H4 |
| 7 | Análise dos casos em que as arquiteturas divergiram |
| 8 | Veredito por hipótese: sustentada · refutada · inconclusiva |

**Compromisso declarado.** As hipóteses estão formuladas para serem falseáveis. Refutar H1 com
método sólido é desfecho tão válido quanto confirmá-la, e será reportado com o mesmo destaque.
Quando os dados não sustentarem veredito, a conclusão será **inconclusiva** — não uma leitura
favorável forçada.

---

## 7. Limitações

Registradas antecipadamente, não como concessão posterior aos resultados.

| ID | Limitação |
| :--- | :--- |
| **L1** | **Dados sintéticos.** Ambiente simulado e internamente consistente por construção; achados não se transferem diretamente a dados industriais reais |
| **L2** | **Poder estatístico limitado.** 17 casos base — efeitos pequenos não serão detectáveis; ausência de significância ≠ ausência de efeito |
| **L3** | **Confundidor não eliminado.** A arquitetura multi-agente consome mais computação; um ganho pode decorrer do isolamento **ou** de mais chamadas de LLM. Quantificado, não isolado |
| **L4** | **Modelos abertos com tool calling variável** — resultados específicos aos modelos testados |
| **L5** | **O juiz é um LLM** — mesmo validado, carrega erro residual; métricas de rubrica reportadas separadamente das determinísticas |
| **L6** | **Rotulação humana por uma única pessoa** — o kappa mede concordância juiz–autor, não juiz–verdade |
| **L7** | **P2.1 é verdadeira por construção** — a garantia estrutural de H2 não é descoberta empírica; o conteúdo empírico está em P2.2 |
| **L8** | **Prompts não otimizados sistematicamente** — uma arquitetura pode ter desempenho inferior por prompt subótimo |
| **L9** | **Cobertura desigual de degradação** — quatro modos têm n = 1 no dataset base |
| **L10** | **Multi-turno planejado, mas não avaliado sistematicamente** — a suíte de regressão é de turno único; se RF40/RF41 forem implementados, ainda não haverá usuário simulado medindo memória entre interações |
| **L11** | **Catálogo de tools difere entre arquiteturas** (18 vs ~8 por agente) — parte de um eventual ganho da multi pode vir de contexto menor, não de isolamento |
| **L12** | **Modelo do agente é proprietário** — Gemini é opção gratuita, não aberta; a escolha decorre da cota |
| **L13** | **A API valida justificativa apenas por comprimento** (≥20 caracteres) — não há rede externa contra justificativa vazia |
| **L14** | **O eixo de modelo de H3 roda com 1 repetição** (orçamento conservador a validar no piloto) — P3.3 sustenta direção, não significância |
| **L15** | **P3.3 confunde capacidade com provedor/família** — o resultado é exploratório e vale apenas para as configurações concretas comparadas |

---

## 8. Possibilidades de evolução

> As direções abaixo estão **fora do escopo entregue**. Um subconjunto delas — as que cabem em horas,
> não em semanas — está priorizado por valor ÷ custo em [`14`](docs/14-roadmap-e-testes.md) §8, para
> ser executado apenas se o cronograma sobrar. Nada ali é compromisso.

| # | Direção | Motivação |
| :--- | :--- | :--- |
| 1 | Usuário simulado multi-turno, no estilo TAU-bench | Cobre L10 — avalia memória e elicitação |
| 2 | *Elicitation* do MCP como guardrail de confirmação | Move a garantia da aplicação para o protocolo |
| 3 | Rotulação por múltiplos avaliadores | Cobre L6 |
| 4 | Segunda API real com overlay próprio | Demonstração empírica da portabilidade (hoje verificada por código) |
| 5 | Topologias adicionais — debate entre agentes, verificador adversarial | Expande o espaço arquitetural |
| 6 | Otimização sistemática de prompt por arquitetura | Cobre L8 |
| 8 | Ampliação de H4 para outros modelos e provedores | Testar se a conclusão B vs C se transfere além dos modelos do piloto |
| 9 | Workers distribuídos em múltiplas máquinas | A fila com lease já suporta; não exercitado porque a cota é por conta, não por máquina |
| 10 | **Entrada por Slack, e-mail e portal** | Cada origem é um adaptador fino sobre `POST /tickets` — o sistema externo empurra, então webhook, não MCP (ADR-12) |
| 10b | **Verificação adversarial antes de agir** — segundo agente instruído a refutar a conclusão antes de ação de impacto. Ataca o modo de falha central do domínio (confirmação); catalogado como E-A6 |
| 11 | **Escalonamento notificando sistemas externos** | Hoje escalar chama o endpoint da API. Notificar Slack ou abrir item no Jira entra pela porta `ToolProvider` como tool de `tier: impact` — é aqui que um **cliente MCP** consumindo servidores prontos se paga (ADR-12) |
| 7 | *Sampling* do MCP para pré-processamento de espectro | Reduz ruído de contexto — excluído deste recorte por contaminar a medição |

---

## 9. Documentação

| Documento | Conteúdo |
| :--- | :--- |
| [`01-visao.md`](docs/01-visao.md) | Contexto, problema, escopo, restrições, riscos |
| [`02-personas-user-stories.md`](docs/02-personas-user-stories.md) | 8 personas derivadas dos perfis reais da API · 27 user stories em 6 épicos |
| [`03-requisitos.md`](docs/03-requisitos.md) | 44 RF · 19 RNF com critério de aceitação mensurável |
| [`04-casos-de-uso.md`](docs/04-casos-de-uso.md) | 12 casos de uso UML com fluxos principais, alternativos e de exceção |
| [`05-arquitetura.md`](docs/05-arquitetura.md) | C4 níveis 1–3 · contratos de dados · **14 ADRs** |
| [`06-matriz-rastreabilidade.md`](docs/06-matriz-rastreabilidade.md) | Persona → US → RF → UC → cenário → métrica → hipótese |
| [`07-plano-experimental.md`](docs/07-plano-experimental.md) | 4 hipóteses, 12 predições, variáveis, desenho, 17 métricas, rubrica, meta-avaliação |
| [`08-glossario.md`](docs/08-glossario.md) | Glossário de domínio industrial e de engenharia de agentes |
| [`09-system-design.md`](docs/09-system-design.md) | Fila com lease, IDs e correlação, taxonomia de falhas, orçamento de tokens, provedores e vazão, contratos do BFF, empacotamento, armazenamento |
| [`10-matriz-de-experimentos.md`](docs/10-matriz-de-experimentos.md) | Catálogo de todas as perguntas testáveis — declaradas, candidatas e descartadas — com custo, valor e portfólio |
| [`11-camada-de-analise.md`](docs/11-camada-de-analise.md) | Pipeline trace → métrica → veredito → estatística → visualização; a fronteira execução↔análise, versionamento, cache de julgamento, dose-resposta |
| [`12-stack.md`](docs/12-stack.md) | Cada tecnologia: onde é usada, por que foi escolhida, o que foi descartado no lugar |
| [`13-padroes-e-estrutura.md`](docs/13-padroes-e-estrutura.md) | Monolito modular vs o espectro, estilo hexagonal (e por que não Clean), regra de dependência, estrutura de pastas, padrões adotados e descartados |
| [`14-roadmap-e-testes.md`](docs/14-roadmap-e-testes.md) | Cronograma dia a dia, escada de visibilidade (Langfuse × front), go/no-go de 31/08, estratégia de TDD com fakes, pirâmide de testes, **lista de extras priorizada**, plano de contingência |

### Cobertura

| Artefato | Total | Rastreado |
| :--- | ---: | ---: |
| Chamados do material | 17 | **100%** |
| User stories | 27 | **100%** |
| Requisitos | 63 | **100%** |
| Hipóteses | 4 | **100%** |
| Casos de uso | 12 | **100%** |
| Modos de degradação | 7 | **100%** |
| Métricas | 17 | **100%** |

---

## 10. Referências

| Referência | Uso neste projeto |
| :--- | :--- |
| [**ReAct** — Yao et al. (2023)](https://arxiv.org/abs/2210.03629) | Padrão do loop de raciocínio de cada agente |
| [**τ-bench** — Yao et al. (2024)](https://arxiv.org/abs/2406.12045) | Modelo de avaliação por cenário com política de domínio; inspiração para o golden dataset |
| [**Toolformer** — Schick et al. (2023)](https://arxiv.org/abs/2302.04761) | Fundamentação sobre quando e como usar APIs externas |
| [**Model Context Protocol — Specification**](https://modelcontextprotocol.io/specification/) | Envelope opcional de interoperabilidade para a camada de tools |
| **LangGraph** | Orquestração do grafo multi-agente com estado e retomada |
| **Eval-driven development** — Airbnb Tech Blog | Fundamentação do desenho de avaliação |

---

## Licença e uso

Projeto acadêmico desenvolvido no Inteli em parceria com a TRACTIAN. Os dados são **sintéticos** e
não contêm informação identificável de clientes.
