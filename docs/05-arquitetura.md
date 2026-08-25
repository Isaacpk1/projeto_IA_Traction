# 05 — Arquitetura

## 1. Princípios de projeto

Cinco decisões governam toda a arquitetura. Cada uma responde a um risco concreto.

| # | Princípio | Risco que endereça |
| :-- | :--- | :--- |
| **P1** | **Genérico no núcleo, específico na borda** — o núcleo de integração não conhece o domínio; a semântica vive num overlay declarativo | Acoplamento a uma única API; retrabalho a cada nova integração |
| **P2** | **Garantia estrutural, não instrução** — restrições de segurança vivem na topologia e no schema, não no prompt | Prompt é probabilístico; instrução pode ser ignorada |
| **P3** | **Handoff tipado, nunca prosa** — transferências entre agentes carregam objetos validados | Perda de evidência na fronteira entre agentes |
| **P4** | **Trace como cidadão de primeira classe** — o trace é dado experimental, não log | Sem trace estruturado, não há experimento |
| **P5** | **Isolamento do gabarito verificável** — a separação é garantida por teste, não por disciplina | Vazamento invalida todos os resultados |

---

## 2. C4 Nível 1 — Contexto

```
   ┌──────────────┐   ┌──────────────────┐   ┌─────────────────────┐
   │ Solicitante  │   │ Sistema Cliente  │   │  Avaliador          │
   │ (P01–P07)    │   │ (integração API) │   │  (P08)              │
   └──────┬───────┘   └────────┬─────────┘   └──────────┬──────────┘
          │ abre ticket        │ POST /tickets          │ configura e analisa
          │                    │                        │ experimentos
          ▼                    ▼                        ▼
   ┌──────────────────────────────────────────────────────────────┐
   │                                                              │
   │        PLATAFORMA DE SUPORTE INDUSTRIAL                      │
   │        Recebe tickets continuamente, prioriza,               │
   │        investiga com agentes, decide entre                   │
   │        orientar/agir/escalar — e mede a própria              │
   │        confiabilidade sobre a suíte de regressão.            │
   │                                                              │
   └───────┬──────────────────────────────────┬───────────────────┘
           │ HTTP                             │ HTTPS
           ▼                                  ▼
   ┌────────────────────┐          ┌──────────────────────┐
   │ API Industrial     │          │ Provedores de LLM    │
   │ TRACTIAN           │          │ [sistemas externos]  │
   │ [sistema externo]  │          │ Gemini → agente      │
   │ 18 endpoints       │          │ Groq   → juiz        │
   │ 7 categorias       │          │ (RNF09: distintos)   │
   └────────────────────┘          └──────────────────────┘
```

**Fronteira do sistema.** A API industrial é externa e **imutável** — material fornecido. O provedor
de LLM é externo e substituível: a arquitetura não depende de um modelo específico.

---

## 3. C4 Nível 2 — Contêineres

```
┌───────────────────────────────────────────────────────────────────────────┐
│                    SISTEMA DE AGENTES INDUSTRIAIS                         │
│                                                                           │
│  ┌─────────────────────────────┐                                          │
│  │  C1 · Interface Web         │  React + Vite + TypeScript                │
│  │  Chat · Inspetor de trace   │                                           │
│  │  Dashboard · Comparador     │                                           │
│  └──────────────┬──────────────┘                                          │
│                 │ REST + SSE                                              │
│  ┌──────────────▼──────────────┐                                          │
│  │  C2 · Backend / BFF         │  FastAPI                                  │
│  │  Orquestra execuções        │                                           │
│  │  Serve traces e métricas    │                                           │
│  │  Transmite eventos (SSE)    │                                           │
│  └───────┬──────────────┬──────┘                                          │
│          │              │                                                 │
│  ┌───────▼──────────┐   │   ┌──────────────────────────┐                  │
│  │  C3 · Núcleo do  │   └──►│  C5 · Framework de       │                  │
│  │       Agente     │       │       Avaliação          │                  │
│  │  Grafo de agentes│       │  Runner · Métricas       │                  │
│  │  Loop ReAct      │       │  Judge · Golden dataset  │                  │
│  │  Tracer          │       └───────────┬──────────────┘                  │
│  └───────┬──────────┘                   │                                 │
│          │ MCP (JSON-RPC / stdio)       │ lê traces                       │
│  ┌───────▼──────────────────────────┐   │                                 │
│  │  C4 · Servidor MCP               │   │                                 │
│  │  Núcleo genérico OpenAPI→tools   │   │                                 │
│  │  + Overlay de domínio            │   │                                 │
│  └───────┬──────────────────────────┘   │                                 │
│          │                              │                                 │
│  ┌───────┼──────────────────────────────▼─────────────────┐               │
│  │  C6 · Armazenamento de artefatos                       │               │
│  │  queue.db (SQLite) · traces/*.jsonl · golden/*.json     │               │
│  └────────────────────────────────────────────────────────┘               │
└──────────┼────────────────────────────────────────────────────────────────┘
           │ HTTP
           ▼
   ┌──────────────────┐
   │ API TRACTIAN     │
   └──────────────────┘
```

### Contêineres

| ID | Contêiner | Tecnologia | Responsabilidade |
| :--- | :--- | :--- | :--- |
| **C1** | Interface Web | React 18, Vite, TypeScript, TanStack Query, Tailwind, shadcn/ui, Recharts | **Console de atendimento**, chat, inspeção de trajetória, dashboard |
| **C2** | Backend / BFF | FastAPI, SSE | **Ingestão de tickets**, expõe execução e artefatos, transmite eventos |
| **C8** | Ingestão | FastAPI + fila | `POST /tickets`, deriva prioridade, enfileira e responde em 202 |
| **C3** | Núcleo do Agente | Python, LangGraph, loop ReAct próprio | Orquestra agentes, executa o ciclo de raciocínio, produz trace |
| **C4** | Camada de ferramentas | Python, PyYAML, httpx | Converte o contrato OpenAPI em tools, aplica o overlay, executa e registra. Biblioteca — envelope MCP opcional (ADR-01) |
| **C5** | Framework de Avaliação | Python, pytest, pandas | Runner durável, métricas, juiz, golden dataset |
| **C6** | Armazenamento durável | SQLite (WAL) + JSONL | Fila, execuções, métricas, julgamentos, traces |
| **C7** | Coordenação efêmera | Redis | Pub/sub SSE, rate limit distribuído, cota diária |

> **Por que um backend existe.** Com Streamlit o front leria os artefatos diretamente. Com React é
> necessária uma fronteira HTTP. O BFF (C2) não contém regra de negócio — apenas expõe C3 e C5.

---

## 4. C4 Nível 3 — Componentes

### 4.1 C4 · Servidor MCP — as duas camadas

Materialização do princípio **P1**.

```
┌──────────────────────────────────────────────────────────────┐
│  CAMADA DE ENRIQUECIMENTO  (específica do domínio)           │
│                                                              │
│   tractian.overlay.yaml                                      │
│   ├─ description  → semântica de domínio para o modelo       │
│   ├─ tier         → read | impact                            │
│   ├─ requires_confirmation                                   │
│   ├─ required_permission                                     │
│   └─ preconditions_for → relação entre tools                 │
└──────────────────────────┬───────────────────────────────────┘
                           │ merge em tempo de inicialização
┌──────────────────────────▼───────────────────────────────────┐
│  NÚCLEO GENÉRICO  (zero conhecimento de domínio)             │
│                                                              │
│   OpenAPIParser   → contrato ⇒ definições de tool            │
│   ToolFactory     → definição ⇒ handler executável           │
│   HttpExecutor    → requisição, cabeçalhos, retry, timeout   │
│   TraceEmitter    → registra toda chamada                    │
│   TierRegistry    → catálogo de tools por nível de impacto   │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP
                    ┌──────▼──────┐
                    │ API TRACTIAN│
                    └─────────────┘
```

**Invariante arquitetural (RNF06).** Nenhum identificador do domínio — `baseline`, `rms`,
`spectrum`, `asset`, `analysis` — aparece no núcleo genérico. Verificado por varredura automatizada
de código; violação falha o build.

#### Exemplo de overlay

```yaml
# tractian.overlay.yaml
version: 1
api: tractian-industrial-v1

tools:
  getBaseline:
    tier: read
    description: |
      Retorna o baseline do ativo — o estado normal aprendido do próprio
      equipamento a partir de histórico sadio.

      O limiar de alarme de RMS DERIVA daqui: reference + tolerance.
      NUNCA de norma ISO nem de tabela por classe de máquina.

      Campo `state`:
        learning     → histórico insuficiente; não há limiar confiável
        established  → limiar válido e utilizável
        invalidated  → houve manutenção ou mudança de configuração;
                       insights gerados neste estado são SUSPEITOS

      Chame ANTES de concluir sobre qualquer análise cujo
      detection_mode seja `baseline`.
    preconditions_for: [getAnalysis, listAnalyses]

  updateAssetConfig:
    tier: impact
    requires_confirmation: true
    required_permission: action_high
    description: |
      Altera a configuração técnica do ativo.
      CONSEQUÊNCIA: invalida o baseline atual e força reaprendizado —
      o ativo ficará sem detecção por desvio até reestabelecer baseline.
      Informe esta consequência ao usuário antes de confirmar.

  escalateCase:
    tier: impact
    requires_confirmation: false
    required_permission: escalate
    description: |
      Encaminha o caso para análise humana.
      Use quando a evidência for insuficiente, o conflito irresolvível,
      ou o caso exigir inspeção física.
      A justificativa deve enumerar o que foi verificado E o que
      permaneceu incerto.
```

O `tier` alimenta simultaneamente três mecanismos: composição de tools por agente (RF12), exigência
de confirmação (RF14) e validação de permissão (RF13). Uma linha declarativa, três garantias.

---

### 4.2 C3 · Núcleo do Agente — as duas arquiteturas

O contêiner implementa **duas arquiteturas intercambiáveis** por trás da mesma interface. São as
condições experimentais da hipótese H1.

#### Arquitetura A — Mono-agente ReAct *(condição de controle)*

```
   ┌──────────────────────────────────────────┐
   │  AGENTE ÚNICO                            │
   │  contexto: mensagem + histórico completo │
   │  tools: TODAS (18 + submit_resolution)   │
   │                                          │
   │  loop: think → act → observe → repeat    │
   └───────────────────┬──────────────────────┘
                       │ todas as tools
                       ▼
                  Servidor MCP
```

Referência de comparação. Contexto único, sem handoff, sem perda de informação — e sem isolamento
nem separação de autoridade.

#### Arquitetura B — Multi-agente especializado *(condição experimental)*

```
                    ┌─────────────────────────┐
                    │  ORQUESTRADOR           │
                    │  tools: nenhuma da API  │
                    │  classifica modalidade  │
                    │  roteia · consolida     │
                    │  submete resolução      │
                    └───┬───────┬──────────┬──┘
       handoff tipado   │       │          │
        ┌───────────────┘       │          └──────────────┐
        ▼                       ▼                         ▼
┌────────────────┐   ┌────────────────────┐   ┌────────────────────┐
│CONTEXTUALIZADOR│   │   INVESTIGADOR     │   │     EXECUTOR       │
│                │   │                    │   │                    │
│ tier: read     │   │ tier: read         │   │ tier: impact       │
│ searchKnowledge│   │ getAsset           │   │ reprocessAnalysis  │
│ getKnowledgeDoc│   │ listAnalyses       │   │ requestSpecialist  │
│ getAsset       │   │ getAnalysis        │   │ requestRetraining  │
│ getCompany     │   │ getBaseline        │   │ updateAssetConfig  │
│ getCurrentUser │   │ getRmsSeries       │   │ escalateCase       │
│                │   │ getSpectrum        │   │                    │
│                │   │ getDataQuality     │   │ + getCurrentUser   │
│                │   │ getModel           │   │   (validar permissão)│
└────────────────┘   └────────────────────┘   └────────────────────┘
   ContextReport      InvestigationReport         ActionReport
```

**Garantia estrutural (P2, RF12, RNF05).** O Investigador **não possui** tools `tier: impact` em seu
schema. Não é uma instrução que ele possa desobedecer — é uma capacidade que ele não tem. A
composição é validada na inicialização; interseção não-vazia entre o conjunto do Investigador e o
conjunto `impact` aborta o processo.

#### Handoff tipado (P3, RF18)

Contrato de transferência entre Investigador e Orquestrador:

```python
class EvidenceRef(BaseModel):
    tool: str                 # tool de origem
    field: str                # caminho do campo no retorno
    value: str                # valor observado
    step: int                 # passo do trace — ancoragem

class Finding(BaseModel):
    claim: str
    supported_by: list[EvidenceRef]
    contradicted_by: list[EvidenceRef] = []

class InvestigationReport(BaseModel):
    findings: list[Finding]
    baseline_state: Literal["learning","established",
                            "invalidated","not_applicable","unknown"]
    detection_mode: Literal["baseline","symptom","unknown"]
    data_quality_meets_requirements: bool | None   # None = não verificado
    model_processing_state: str | None
    conflicts: list[str] = []
    unverified: list[str] = []      # lacunas explícitas — RF09
    confidence: Literal["high","medium","low"]
```

Três campos carregam o peso do projeto:

- **`supported_by`** ancora cada afirmação num passo do trace. Torna o *grounding check* (RF25) uma
  verificação determinística, não uma inspeção textual.
- **`unverified`** força a declaração de lacunas. Um agente que omite o que não sabe produz lista
  vazia — e isso é mensurável.
- **`data_quality_meets_requirements = None`** distingue **"não verificado"** de **"verificado e
  falso"**. Um booleano simples perderia essa diferença, que é exatamente o objeto da hipótese H1.

#### Loop ReAct

Ambas as arquiteturas usam o mesmo loop por agente. LangGraph orquestra **entre** agentes; o loop
**dentro** de cada agente é próprio — controle total sobre política de parada e instrumentação.

```python
async def react_loop(agent_ctx, messages, tools, tracer, max_steps):
    for step in range(max_steps):
        # THOUGHT
        resp = await llm.chat(messages=messages, tools=tools, temperature=0)
        messages.append(resp.message)

        if not resp.message.tool_calls:
            tracer.stop(reason="sufficient")
            return resp.message.content

        for tc in resp.message.tool_calls:
            # ACTION
            result, error, ms = await mcp.call(tc.name, tc.arguments)

            # TRACE — P4
            tracer.record(step=step, agent=agent_ctx.name,
                          reasoning=resp.message.content,
                          tool=tc.name, args=tc.arguments,
                          result=result, error=error, latency_ms=ms)

            # OBSERVATION
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": serialize(result, error)})

    tracer.stop(reason="max_steps")
    return None
```

---

### 4.3 C5 · Framework de Avaliação

```
┌──────────────────────────────────────────────────────────────┐
│  GoldenDataset      casos + trajetória, decisão, evidências  │
│                     obrigatórias, afirmações vedadas         │
│  CaseGenerator      variação combinatória (RF21)             │
└──────────────────────────┬───────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Runner                                                      │
│  ├─ IsolationGuard    aborta se gabarito acessível (RNF02)  │
│  ├─ Scheduler         concorrência limitada (RF22)          │
│  ├─ Checkpointer      retomada por caso (RF23)              │
│  └─ RetryPolicy       recuo exponencial (RNF04)             │
└──────────────────────────┬───────────────────────────────────┘
                           ▼  traces
┌──────────────────────────────────────────────────────────────┐
│  Métricas determinísticas (RF24)      │  Judge (RF26)        │
│  ├─ TrajectoryScorer                  │  ├─ Rubric (binária) │
│  ├─ ArgumentScorer                    │  ├─ JudgeRunner      │
│  ├─ DecisionScorer                    │  └─ MetaEvaluator    │
│  ├─ PreconditionOrderScorer  ← H1     │      (kappa, RF27)   │
│  ├─ SafetyScorer  (falso agir)  ← H2  │                      │
│  ├─ GroundingChecker (RF25)           │  modelo ≠ agente     │
│  └─ StabilityScorer                   │  (RNF09)             │
└──────────────────────────┬───────────────────────────────────┘
                           ▼
                    Relatório comparativo (RF28)
```

**IsolationGuard (P5, RNF02).** Antes de qualquer execução, verifica que os caminhos do gabarito não
estão acessíveis ao processo do agente — nem no prompt, nem como resource MCP, nem no sistema de
arquivos visível ao agente. Violação aborta a suíte. É o único componente cuja falha impede
totalmente a execução.

---

### 4.4 C1 · Interface Web

```
src/
├─ pages/
│  ├─ Attendance.tsx      chat + execução ao vivo (US23)
│  ├─ TraceInspector.tsx  trajetória passo a passo (US22)
│  ├─ Dashboard.tsx       métricas agregadas (US18)
│  └─ Comparison.tsx      lado a lado (US24)
├─ components/
│  ├─ TraceTimeline.tsx   passos com agente, tool, args, retorno
│  ├─ AgentBadge.tsx      identifica o agente responsável
│  ├─ HandoffMarker.tsx   fronteira entre agentes + payload
│  ├─ EvidenceChip.tsx    evidência ancorada → salta ao passo
│  ├─ PreconditionBar.tsx baseline · qualidade · modelo
│  └─ MetricCard.tsx
└─ lib/
   ├─ api.ts              cliente REST
   └─ stream.ts           consumo de SSE
```

**Decisão de design.** `EvidenceChip` é clicável e navega até o passo do trace que originou o valor.
Torna a ancoragem de evidência **visível e verificável pelo avaliador humano**, não apenas
computada. É o componente que transforma o conceito de *grounding* em algo demonstrável na
apresentação.

---

## 5. Fluxo de execução — sequência

```
Solicitante   Front    BFF    Orquestrador  Investigador   MCP    API
     │          │       │          │             │          │      │
     │─chamado─►│       │          │             │          │      │
     │          │─POST─►│          │             │          │      │
     │          │◄─SSE──│          │             │          │      │
     │          │       │─start───►│             │          │      │
     │          │       │          │─classifica  │          │      │
     │          │◄ ─ ─ ─│◄ ─evento─│             │          │      │
     │          │       │          │─handoff────►│          │      │
     │          │       │          │             │─getAsset►│─GET─►│
     │          │       │          │             │◄─────────│◄─────│
     │          │◄ ─ ─ ─│◄ ─ ─ ─ ─ evento ─ ─ ─ ─│          │      │
     │          │       │          │             │─getBaseline────►│
     │          │       │          │             │◄─ invalidated ──│
     │          │       │          │             │─getSpectrum────►│
     │          │       │          │             │◄────────────────│
     │          │       │          │◄─Investigation           │    │
     │          │       │          │  Report (tipado)         │    │
     │          │       │─decide──►│                          │    │
     │          │       │          │─submit_resolution        │    │
     │          │◄─final│◄─────────│                          │    │
     │◄─exibe───│       │          │                          │    │
     │          │       │  [trace persistido em C6]           │    │
```

---

## 6. Modelo de dados

### Trace de execução

```python
class TraceStep(BaseModel):
    step: int
    agent: str                       # qual agente executou
    reasoning: str | None
    tool: str | None
    args: dict | None
    result: dict | None
    error: str | None
    latency_ms: float
    t_offset_ms: float               # desde o início da execução

class Handoff(BaseModel):
    after_step: int
    from_agent: str
    to_agent: str
    payload: dict                    # relatório tipado serializado

class Resolution(BaseModel):
    decision: Literal["orientar", "agir", "escalar"]
    justification: str
    evidence_cited: list[EvidenceRef]
    unverified: list[str]
    action_taken: str | None
    confirmation_requested: bool

class ExecutionTrace(BaseModel):
    run_id: str
    case_id: str
    repetition: int
    architecture: Literal["mono", "multi"]
    # metadados de reprodutibilidade — RNF15
    model: str
    model_version: str
    temperature: float
    api_seed: str | None
    overlay_version: str
    dataset_version: str
    # execução
    steps: list[TraceStep]
    handoffs: list[Handoff]
    resolution: Resolution | None
    stop_reason: Literal["sufficient","max_steps","error","budget"]
    duration_ms: float
    tokens_in: int
    tokens_out: int
```

### Caso do golden dataset

```python
class GoldenCase(BaseModel):
    case_id: str
    ticket_id: str
    source: Literal["base", "generated"]      # RF21
    # entrada — o que o agente vê
    message: str
    company_id: str
    user_id: str
    asset_id: str
    # gabarito — NUNCA visível ao agente (RNF02)
    root_question: str
    degradation_mode: Literal["complete","partial","inconclusive",
                              "conflict","unavailable","stale","pending"]
    expected_path: list[ExpectedStep]
    expected_decision: Literal["orientar","agir","escalar"]
    required_evidence: list[str]      # deve aparecer
    forbidden_claims: list[str]       # não pode aparecer (ex.: "ISO 10816")
    required_preconditions: list[str] # tools que devem preceder a conclusão
```

> Os campos `forbidden_claims` e `required_preconditions` não existem no gabarito original fornecido.
> São a formalização adicionada por este projeto — e é o que permite medir RF07 e a hipótese H1 de
> forma determinística.

---

## 7. Stack

> Visão resumida. O detalhamento por tecnologia — onde cada uma é usada, por que foi escolhida e o
> que foi descartado em seu lugar — está em [`12-stack.md`](./12-stack.md).

### Backend

| Componente | Escolha | Justificativa |
| :--- | :--- | :--- |
| Linguagem | Python 3.11+ | Alinhado ao material fornecido |
| Gerenciador | `uv` | Mesmo do repositório base; resolução rápida e lockfile |
| Servidor MCP | MCP SDK Python | Geração a partir de OpenAPI; transporte stdio |
| Orquestração | LangGraph | Grafo multi-agente, checkpointer, retomada durável |
| Loop do agente | Próprio (~40 linhas) | Controle de política de parada e instrumentação sob medida |
| Cliente LLM — agente | `google-genai` | SDK oficial do Gemini, com function calling |
| Cliente LLM — juiz e H3 | SDK OpenAI (`base_url` trocada) | Groq e OpenRouter são compatíveis; um cliente serve os dois |
| Validação | Pydantic v2 | Tools, handoffs, traces, resoluções |
| API web | FastAPI + SSE | Consistente com o material; streaming nativo |
| Fila / estado | **SQLite (WAL)** | Fila com lease, índice de execuções, consulta do dashboard |
| Empacotamento | **Docker Compose** | Reprodução do ambiente completo (RNF14) |
| Coordenação | **Redis** | Pub/sub de eventos, rate limit distribuído, contador de cota (efêmero) |
| Estatística | **statsmodels, scipy** | Regressão logística com interação, testes pareados, bootstrap |
| Testes | pytest, pytest-asyncio | Suíte de avaliação e testes de invariantes |
| Análise | pandas, Plotly | Agregação e visualização de resultados |

### Frontend

| Componente | Escolha | Justificativa |
| :--- | :--- | :--- |
| Framework | React 18 + Vite | Requisito do projeto; build rápido |
| Linguagem | TypeScript | Tipagem dos contratos de trace, espelhando Pydantic |
| Estado servidor | TanStack Query | Cache e revalidação de traces e métricas |
| Estilo | Tailwind CSS + shadcn/ui | Componentes prontos; foco no conteúdo |
| Gráficos | Recharts | Integração natural com React |
| Streaming | EventSource nativo | SSE sem dependência adicional |

### Modelos

| Papel | Provedor | Modelo | Cota | Vazão |
| :--- | :--- | :--- | :--- | ---: |
| **Agente** (todos os papéis) | Google AI Studio | Gemini 2.5 Flash, `temperature = 0` | 1.500 req/dia | 187 exec/dia |
| **Juiz** | Groq | `compound` — família e provedor distintos | 250 req/dia | 250 julg./dia |
| **Eixo H3** | OpenRouter | modelo aberto `:free` | 50 req/dia | amostra |

> **RF33 — homogeneidade obrigatória.** Todos os papéis de agente usam o **mesmo** modelo em E1/E2.
> Heterogeneidade entre papéis tornaria impossível separar o efeito da arquitetura do efeito do
> modelo. O juiz é exceção legítima: não integra o sistema medido, e ser distinto é exigência do
> RNF09.
>
> A escolha do provedor decorre da cota — ver [`09-system-design.md`](./09-system-design.md), §3.

---

## 8. Estrutura do repositório

O sistema é um **monolito modular com múltiplos pontos de entrada**: uma base de código, fronteiras
de módulo rígidas, deploy em processos separados por razão operacional — não por independência de
serviço.

```
src/
├─ core/          contratos + portas · ZERO dependências internas
├─ tools/         núcleo genérico (OpenAPI→tools) + overlay · MCP opcional
├─ agents/        loop ReAct + arquiteturas mono/multi
├─ evaluation/    golden dataset + runner + juiz
├─ analysis/      scorers + agregação + estatística
├─ storage/       adaptadores SQLite · JSONL · Redis
├─ llm/           adaptadores Gemini · OpenAI-compat
└─ interfaces/    entrypoints: cli · worker · api
```

**A regra de dependência:** `core/` não importa nada; módulos importam `core/`, nunca uns aos outros;
só `interfaces/` compõe módulos. Verificada por teste automatizado — um `import` fora da regra quebra
o build.

> A estrutura completa, a justificativa de cada pasta, os padrões de projeto adotados (e os
> deliberadamente descartados) estão em
> [`13-padroes-e-estrutura.md`](./13-padroes-e-estrutura.md).

---

## 9. Decisões arquiteturais registradas

### ADR-01 — Camada de ferramentas como biblioteca; MCP como envelope opcional

**Contexto.** O agente precisa acessar 18 endpoints HTTP. O TAP admite *"tools, servidor MCP ou
abordagem equivalente"*. A primeira versão desta decisão adotou MCP desde o início.

**Reexame.** O MCP tem uma **direção**: o servidor embrulha um sistema externo; o cliente é a
aplicação de IA. Isso significa que **duas propriedades frequentemente confundidas vêm de lugares
diferentes**:

| Propriedade | Significado | De onde vem |
| :--- | :--- | :--- |
| **Portabilidade de API** | apontar a camada para outro contrato OpenAPI | **parser + overlay** — código próprio |
| **Interoperabilidade de host** | Claude Desktop, Cursor ou outro host usar estas tools | **MCP** |

O RNF06 exige a **primeira**. Ela é entregue pelo parser genérico mais o overlay declarativo, e
funciona idêntica como biblioteca Python — sem protocolo nenhum. Não existe mecanismo que converta
"qualquer API" automaticamente: é código, e o código é o mesmo com ou sem MCP.

Os demais argumentos usados na primeira versão não se sustentaram no reexame: instrumentação de trace
(um decorator resolve), desacoplamento agente↔ferramentas (o adaptador `LLMClient` já entrega) e
correlação de execução (sem subprocesso, o worker passa o `run_id` direto ao tracer).

**Decisão.** Construir a camada como **biblioteca Python** — `openapi_parser`, `tool_factory`,
`http_executor`, `tier_registry`, `overlay`. O servidor MCP fica como **envelope aditivo**, aplicado
ao fim do cronograma se houver tempo e se a interoperabilidade for demonstrada.

**Consequências.** ✅ Dois lugares para depurar em vez de cinco. ✅ Sem a armadilha do transporte
stdio, em que um `print()` acidental corrompe o stream JSON-RPC. ✅ RNF06 entregue de qualquer forma.
✅ O envelope MCP são ~2 horas sobre as mesmas funções, não uma reescrita. ❌ Abre mão, por ora, da
interoperabilidade de host.

**Quando o MCP se justifica.** Como **feature de produto** — permitir que o cliente pluge a camada de
ferramentas na stack de IA que ele já usa — e apenas se for **demonstrado**, não alegado. Como
capacidade hipotética no README, não se paga.

**Alternativa descartada.** Adotar MCP desde o início — custo antecipado de uma camada de depuração
para uma propriedade que o projeto não requer.

---

### ADR-12 — Integração com sistemas externos: entrada por webhook, saída por porta de ferramentas

**Contexto.** Num produto real, o sistema não vive isolado. Reclamações podem chegar por Slack ou
e-mail, e **escalar para humano** — hoje um `POST` que retorna sucesso — significa, de verdade,
notificar alguém, criar um item de trabalho e rotear para a pessoa certa.

**A direção decide o mecanismo.** As duas integrações parecem a mesma coisa e não são:

| Direção | Exemplo | Mecanismo correto | Por quê |
| :--- | :--- | :--- | :--- |
| **Entrada** | reclamação chega por Slack → vira ticket | **webhook → `POST /tickets`** | O sistema externo **empurra**. MCP serve para a IA **puxar** capacidades — direção errada |
| **Saída** | escalar → notificar no Slack, abrir item no Jira | **`ToolProvider` — possivelmente cliente MCP** | O agente **decide** usar a capacidade. É exatamente o caso de uso do MCP como cliente |

**Decisão.** A entrada permanece HTTP: qualquer origem — Slack, e-mail, portal — vira um adaptador
fino que chama `POST /tickets`. A saída passa pela porta `ToolProvider`, que **não distingue** tools
da API TRACTIAN de tools de terceiros: ambas são ferramentas com `tier`, e o Executor as recebe da
mesma forma.

**Consequência.** O conceito de `tier: impact` se estende naturalmente — postar num canal de Slack é
uma ação de impacto tanto quanto alterar configuração de ativo. A composição por papel (RF12) e a
exigência de confirmação (RF14) se aplicam sem alteração.

**Escopo.** Não implementado neste ciclo. O que é exigido agora é que a porta `ToolProvider` não
pressuponha origem única — para que acrescentar um provedor externo seja um adaptador, e não uma
reforma. Registrado como evolução.

> **Este é o caso em que o MCP paga.** Não como servidor expondo a TRACTIAN, mas como **cliente
> consumindo servidores existentes**: se há um servidor MCP de Slack pronto, plugá-lo entrega a
> ferramenta de escalonamento sem escrever integração. É uma capacidade diferente da do ADR-01 —
> lá o sistema é servidor; aqui seria host.

---

### ADR-02 — Núcleo genérico com overlay declarativo

**Contexto.** Escrever 18 tools à mão não escala para múltiplas APIs; gerar tools cruas do OpenAPI
produz descrições pobres que degradam a seleção de função.
**Decisão.** Separar em núcleo genérico (geração) e overlay declarativo (semântica).
**Consequências.** ✅ Portabilidade real (RNF06). ✅ Semântica de domínio versionada e auditável.
✅ `tier` alimenta três garantias com uma declaração. ❌ Overlay precisa ser mantido em sincronia com
o contrato.
**Alternativa descartada.** Editar o contrato fornecido — perderia atualizações e acoplaria o núcleo
ao domínio.

---

### ADR-03 — LangGraph entre agentes, loop próprio dentro

**Contexto.** O grafo multi-agente precisa de roteamento, estado e retomada durável; o loop de
raciocínio precisa de instrumentação sob medida.
**Decisão.** LangGraph orquestra as transições entre agentes; o ciclo ReAct de cada agente é
implementado diretamente.
**Consequências.** ✅ Checkpointer e retomada resolvem o risco de rate limit (RSC-01). ✅ O grafo é
o diagrama da arquitetura. ✅ O trace captura exatamente os campos experimentais necessários.
❌ Duas camadas de orquestração para compreender.
**Alternativa descartada.** LangGraph puro — a extração dos campos de trace específicos exigiria
lutar contra a abstração.

---

### ADR-04 — Separação de autoridade por composição de tools

**Contexto.** Executar ação de impacto indevidamente é o erro de maior custo do sistema.
**Decisão.** Restringir o conjunto de tools por agente conforme o `tier`, em vez de instruir o
agente a se conter.
**Consequências.** ✅ Garantia determinística, não probabilística. ✅ Verificável por teste
automatizado. ✅ Argumento de segurança defensável. ❌ Só se aplica à arquitetura multi-agente — a
mono depende de guardrail no host.
**Alternativa descartada.** Instrução no prompt — probabilística e silenciosamente falível.

---

### ADR-05 — Handoff por objeto tipado

**Contexto.** Transferência textual entre agentes comprime e perde evidência.
**Decisão.** Handoffs carregam objetos Pydantic validados, com evidência ancorada em passos do
trace.
**Consequências.** ✅ Ancoragem verificável determinística. ✅ Lacunas explícitas via `unverified`.
✅ Distinção entre "não verificado" e "verificado e falso". ❌ Contrato rígido pode não acomodar
achados imprevistos.
**Alternativa descartada.** Resumo em linguagem natural — reintroduziria a alucinação na fronteira.

---

### ADR-11 — Redis para coordenação efêmera

**Contexto.** Separar runner e BFF em contêineres (ADR-10) criou duas lacunas: os eventos de execução
ocorrem no processo do runner mas o SSE é servido pelo BFF; e a cota do provedor é da **conta**, não
do processo — dois processos consumindo o mesmo teto não se coordenam por contador em memória.

**Decisão.** Adotar Redis para **coordenação efêmera**: pub/sub de eventos, tokens de rate limit
compartilhados e contador de cota diária. **O estado durável permanece em SQLite.**

**Critério da divisão.** Se perder o dado dói no resultado do experimento → SQLite. Se apenas
atrapalha a operação do momento → Redis.

**Consequências.** ✅ RNF08 (latência de streaming) atendido sem polling de arquivo. ✅ A guarda de
cota (RNF16) passa a valer para todos os processos. ✅ Degradação graciosa: Redis fora do ar
interrompe o streaming ao vivo, mas a execução continua e os traces seguem sendo gravados (RNF17).
❌ Um serviço a mais no Compose.

**Alternativas descartadas.** *BFF lendo o JSONL do runner* — frágil e com latência de polling
incompatível com RNF08. *Runner e BFF no mesmo processo* — uma rodada de horas travaria a API.
*Redis também como fila* — perderia a durabilidade que o SQLite dá de graça, e o artefato
experimental deixaria de ser um arquivo que acompanha o repositório.

---

### ADR-10 — Docker Compose para empacotamento; SQLite mantido para a fila

**Contexto.** Cogitou-se substituir o SQLite por um banco em contêiner. São coisas de camadas
diferentes: Docker é empacotamento e isolamento de ambiente; SQLite é o mecanismo de persistência da
fila. A decisão foi separada em duas.

**Decisão A — Docker Compose para o ambiente: SIM.** A pilha (API TRACTIAN, BFF, front) é publicada
como `docker-compose.yml`.
**Consequências.** ✅ Atende RNF14 diretamente: `docker compose up` reproduz o ambiente inteiro sem
instalar Python, Node ou `uv`. ✅ Versões congeladas nas imagens — a reprodutibilidade deixa de
depender do que está instalado na máquina de quem avalia. ❌ Exige Docker instalado. ❌ Iteração no
front é mais confortável fora do contêiner durante o desenvolvimento (mitigado por *bind mount*).

**Decisão B — trocar SQLite por Postgres em contêiner: NÃO.**
**Justificativa quantitativa.** A vazão do sistema é limitada a **15 requisições por minuto** pela
cota do provedor — cerca de **0,03 escrita por segundo** na fila. SQLite sustenta milhares de
escritas por segundo. Postgres resolveria um gargalo de concorrência **três ordens de grandeza acima**
do que este sistema produz.
**Consequências.** ✅ Zero infraestrutura: o artefato experimental é um arquivo único, versionável e
inspecionável com qualquer cliente SQLite. ✅ Um serviço a menos no Compose. ✅ Quem for reproduzir
recebe a fila e os resultados junto com o repositório. ❌ Sem `SELECT ... FOR UPDATE SKIP LOCKED` —
emulado por `UPDATE ... RETURNING` em transação, suficiente nesta escala. ❌ Escrita serializada —
irrelevante a 0,03 escrita/s.

**Reversibilidade.** A fila é acessada por uma interface (`enqueue`, `lease`, `complete`, `fail`).
Trocar o backend por Postgres exigiria uma implementação nova dessa interface, sem tocar no runner.

---

### ADR-07 — Fila durável com lease em SQLite

**Contexto.** Checkpoint (RF23), retry (RNF04), concorrência (RF22) e retomada (RNF03) estavam
especificados como quatro mecanismos separados.
**Decisão.** Modelar como uma **fila de trabalho durável com lease**, em SQLite.
**Consequências.** ✅ Um mecanismo resolve os quatro requisitos. ✅ O lease com expiração recupera
tasks de processos mortos — que um checkpoint de conclusões deixaria em limbo. ✅ `task_id`
determinístico torna reenfileirar idempotente: retomar é `INSERT OR IGNORE`. ✅ O índice em SQLite
resolve de quebra a consulta do dashboard sobre centenas de traces. ❌ Um esquema a manter.
**Alternativa descartada.** Broker de mensagens (Redis, RabbitMQ) — adicionaria infraestrutura para
resolver um problema que não existe nesta escala.

---

### ADR-08 — Ferramentas in-process; subprocesso apenas se o envelope MCP existir

**Contexto.** Com a camada de ferramentas como biblioteca (ADR-01), não há subprocesso: o worker
chama a função diretamente. A questão de topologia só aparece se o envelope MCP for construído.

**Decisão.** **Padrão:** o worker executa as tools no próprio processo. A correlação de trace é
trivial — o worker já conhece `run_id` e `execution_id` e os passa ao tracer.

**Se o envelope MCP for construído:** um subprocesso por worker, com o contexto de correlação
carregado no handshake `initialize`. Servidor compartilhado exigiria que o `run_id` viajasse como
argumento de tool, poluindo o schema e ficando sujeito a erro do modelo.

**Consequências.** ✅ No caminho padrão, duas camadas a menos e correlação direta. ✅ Se o envelope
existir, a decisão de topologia já está tomada. ❌ Sem subprocesso, uma falha na camada de ferramentas
derruba o worker — aceitável, já que é um invólucro de `httpx` e as exceções são tratadas.

---

### ADR-09 — Token bucket em vez de controlador adaptativo

**Contexto.** É preciso operar próximo ao limite do provedor sem gerar 429 em cascata.
**Decisão.** **Token bucket** na taxa documentada como mecanismo primário; AIMD apenas como rede de
segurança.
**Consequências.** ✅ ~30 linhas para uma cota conhecida e constante. ✅ A concorrência deixa de
determinar a vazão — workers existem só para sobrepor latência. ✅ AIMD cobre o caso de a cota mudar
sem aviso. ❌ Não descobre limites não documentados sozinho.
**Alternativa descartada.** AIMD como mecanismo primário — complexidade de descoberta para uma
constante já conhecida.

---

### ADR-06 — React com backend dedicado

**Contexto.** Streamlit leria os artefatos diretamente, sem camada intermediária.
**Decisão.** Interface React com BFF em FastAPI.
**Consequências.** ✅ Streaming em tempo real do raciocínio, de alto valor demonstrativo.
✅ Inspetor de trace substancialmente melhor. ❌ Contêiner adicional. ❌ Custo estimado de 3–4 dias
do cronograma.
**Alternativa descartada.** Streamlit — mais rápido, porém demonstração significativamente mais
fraca.
