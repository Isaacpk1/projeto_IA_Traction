# 12 — Stack Tecnológica

> Cada tecnologia listada aqui declara **onde é usada**, **por que foi escolhida** e **o que foi
> descartado em seu lugar**. Uma dependência sem justificativa é peso morto — e num projeto de 15
> dias, peso morto é risco.
>
> A organização do código — módulos, regra de dependência e padrões de projeto — está em
> [`13-padroes-e-estrutura.md`](./13-padroes-e-estrutura.md).
>
> Versões são mínimas. O travamento exato acontece no `uv.lock` e no `package-lock.json` durante a
> implementação (RNF14).

---

## 1. Visão por serviço

```
┌──────────────────────────────────────────────────────────────────┐
│  docker compose                                                  │
│                                                                  │
│  ┌────────────────┐   ┌────────────────┐   ┌──────────────────┐  │
│  │ tractian-api   │   │   frontend     │   │      redis       │  │
│  │ FastAPI        │   │ React · Vite   │   │  7-alpine        │  │
│  │ pandas·pyarrow │   │ TypeScript     │   │  (sem volume)    │  │
│  │ [dado pronto]  │   │ Tailwind       │   │                  │  │
│  └────────────────┘   └────────────────┘   └──────────────────┘  │
│                                                                  │
│  ┌────────────────┐   ┌─────────────────────────────────────┐    │
│  │   backend      │   │            runner                   │    │
│  │ FastAPI · SSE  │   │ LangGraph · loop ReAct próprio      │    │
│  │ redis-py       │   │ MCP SDK · google-genai · httpx      │    │
│  │ sqlite3        │   │ Pydantic · sqlite3 · redis-py       │    │
│  └────────────────┘   └─────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  análise  (biblioteca, não serviço)                     │     │
│  │  pandas · statsmodels · scipy · pyarrow                 │     │
│  └─────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
```

> A análise **não é um serviço**. É uma biblioteca chamada pelo runner (scoring), pelo BFF
> (agregação) e pela linha de comando (recomputação, testes). Isso é deliberado: ela precisa rodar
> num notebook ou num teste sem subir o sistema — ver
> [`11-camada-de-analise.md`](./11-camada-de-analise.md) §2.5.

---

## 2. Tabela mestra

| Tecnologia | Versão mín. | Camada | Papel em uma linha |
| :--- | :--- | :--- | :--- |
| **Python** | 3.11 | todas | Linguagem principal |
| **uv** | recente | build | Ambiente e lockfile |
| **Pydantic** | 2.x | todas | Validação em toda fronteira (RNF13) |
| **mcp** *(SDK oficial)* | 1.x | *opcional* | Envelope MCP — aplicado no fim, se houver tempo (ADR-01) |
| **FastMCP** | 2.x | *opcional* | Idem |
| **PyYAML** | 6.x | MCP | Leitura do contrato e do overlay |
| **httpx** | 0.27+ | MCP | Cliente HTTP assíncrono para a API industrial |
| **google-genai** | recente | agente | SDK do Gemini — modelo do agente |
| **openai** | 1.x | agente | Cliente compatível para Groq e OpenRouter |
| **LangGraph** | 0.2+ | agente | Grafo entre agentes, checkpointer |
| **tenacity** | 8.x | agente | Retry com recuo exponencial (RNF04) |
| **SQLite** | 3.35+ | dados | Fila, execuções, métricas, julgamentos |
| **Redis** | 7.x | coordenação | Pub/sub, rate limit distribuído, cota |
| **redis-py** | 5.x | coordenação | Cliente assíncrono |
| **FastAPI** | 0.115+ | BFF | API REST e SSE |
| **uvicorn** | 0.30+ | BFF | Servidor ASGI |
| **sse-starlette** | 2.x | BFF | Streaming de eventos |
| **pandas** | 2.x | análise | Agregação |
| **pyarrow** | 17+ | análise | Leitura e escrita de Parquet |
| **statsmodels** | 0.14+ | análise | Regressão logística com interação |
| **scipy** | 1.14+ | análise | Testes pareados, bootstrap |
| **scikit-learn** | 1.5+ | análise | Kappa de Cohen |
| **DeepEval** | recente | avaliação | Juiz (GEval) · ToolCorrectness · component-level no piloto |
| **import-linter** | 2.x | testes | Regra de dependência, inclusive **import indireto** |
| **polyfactory** | 2.x | testes | Gera `ExecutionTrace` válido a partir do modelo Pydantic |
| **pytest** | 8.x | testes | Suíte e invariantes |
| **pytest-asyncio** | 0.24+ | testes | Testes assíncronos |
| **respx** | 0.21+ | testes | Mock de httpx sem rede |
| **time-machine** | 2.x | testes | Controle de relógio (expiração de lease) |
| **typer** | 0.12+ | CLI | Entrypoints |
| **pydantic-settings** | 2.x | config | `.env` tipado |
| **React** | 18 | front | Interface |
| **Vite** | 5.x | front | Build e dev server |
| **TypeScript** | 5.x | front | Tipagem espelhando os contratos Pydantic |
| **TanStack Query** | 5.x | front | Estado de servidor |
| **Tailwind CSS** | 3.x | front | Estilo |
| **shadcn/ui** | — | front | Componentes base |
| **Recharts** | 2.x | front | Gráficos |
| **Docker Compose** | v2 | infra | Reprodutibilidade (RNF14) |

---

## 3. Detalhamento por camada

### 3.1 Base e ambiente

#### Python 3.11+
**Onde:** todos os serviços exceto o front.
**Por quê:** alinhado ao material fornecido pela TRACTIAN. A partir do 3.11, `asyncio.TaskGroup` e
melhorias de desempenho em asyncio importam para o runner concorrente.
**Descartado:** 3.10 — funciona, mas perde `TaskGroup`, que simplifica o controle dos workers.

#### uv
**Onde:** gerenciamento de dependências e execução (`uv sync`, `uv run`).
**Por quê:** é o gerenciador usado no repositório base — manter consistência reduz atrito para quem
avaliar. Resolução rápida e lockfile determinístico atendem RNF14.
**Descartado:** Poetry (mais lento, outro formato de lock), pip + requirements (sem resolução
determinística).

#### Pydantic 2
**Onde:** **toda fronteira entre componentes** — argumentos de tool, `InvestigationReport`,
`Resolution`, `TraceStep`, `GoldenCase`, `MetricResult`, eventos SSE.
**Por quê:** RNF13 exige validação em toda fronteira, com falha explícita e nunca silenciosa. A v2
tem desempenho suficiente para validar milhares de objetos por execução sem custo perceptível.
**Descartado:** dataclasses (sem validação), attrs (validação mais fraca), TypedDict (só checagem
estática, não em tempo de execução).

> Pydantic é o que torna `RNF13` verificável em vez de aspiracional. Os schemas TypeScript do front
> são gerados a partir desses modelos, mantendo os dois lados em sincronia.

---

### 3.2 Camada MCP

#### Geração de tools — código próprio
**Onde:** `src/tools/core/openapi_parser.py` e `tool_factory.py`.
**Por quê:** converter os 18 `operationId` do contrato em definições de tool com JSON Schema é a
mecânica que entrega o RNF06 — outra API exige apenas novo contrato e novo overlay. **Não depende de
MCP:** o mesmo parser alimenta a biblioteca hoje e o envelope MCP depois, se ele existir.
**Descartado:** escrever as 18 tools à mão (não escala e acopla o núcleo ao domínio); geradores de
código estático (produzem código a manter em vez de derivação na inicialização).

> ⚠️ **Ponto de verificação da semana 1.** A geração precisa produzir schemas válidos para os 18
> `operationId`. Se falhar em algum, o plano B é gerar o que der e completar manualmente,
> registrando quais.

#### mcp e FastMCP — *opcionais*
**Onde:** `src/tools/mcp_wrapper.py`, se o item 3 do ADR-01 for executado.
**Por quê:** expõem as mesmas funções por JSON-RPC, permitindo que hosts compatíveis usem a camada.
É **interoperabilidade de host**, não portabilidade de API — a segunda já vem do parser.
**Risco conhecido:** no transporte stdio, qualquer escrita acidental em `stdout` corrompe o stream
JSON-RPC, com falha silenciosa e difícil de diagnosticar.

#### PyYAML
**Onde:** leitura de `api-contract.openapi.yaml` e de `tractian.overlay.yaml`.
**Por quê:** os dois arquivos são YAML. Sem alternativa relevante.

#### httpx
**Onde:** `src/tools/core/http_executor.py` — chamadas à API industrial.
**Por quê:** cliente assíncrono, necessário porque o runner é concorrente. Suporta timeouts por fase
e injeção do cabeçalho `x-user-id`.
**Descartado:** `requests` (síncrono, bloquearia os workers), `aiohttp` (API menos ergonômica para
este uso).

---

### 3.3 Camada de agente

#### google-genai
**Onde:** cliente do modelo do agente (Gemini 2.5 Flash e Flash-Lite).
**Por quê:** SDK oficial do Gemini, com suporte a *function calling* — a capacidade de que todo o
projeto depende. É o provedor que torna o experimento viável (187 execuções/dia contra 3 e 6 das
alternativas gratuitas).
**Descartado:** `google-generativeai` — SDK anterior, substituído pelo unificado.

#### openai
**Onde:** cliente do **juiz** (Groq) e do eixo H3 (OpenRouter).
**Por quê:** ambos expõem API compatível com OpenAI; trocar `base_url` basta. Um cliente serve os
dois provedores.
**Descartado:** SDKs específicos por provedor — três clientes para o mesmo protocolo.

> **Dois SDKs, e isso é intencional.** O agente usa `google-genai`; juiz e H3 usam `openai`. A
> separação reforça RNF09 na prática: agente e juiz não compartilham nem cliente nem provedor.

#### LangGraph
**Onde:** `src/agents/architectures/multi.py` — grafo entre orquestrador e especialistas.
**Por quê:** ADR-03. Roteamento com estado, checkpointer e retomada durável entre nós.
**Não é usado para:** o loop ReAct **dentro** de cada agente, que é próprio (~40 linhas). O trace
precisa capturar campos específicos do experimento — pré-condições verificadas, evidência ancorada,
handoffs — e extrair isso de callbacks de framework seria lutar contra a abstração.
**Descartado:** LangGraph também para o loop interno (perda de controle sobre a instrumentação);
CrewAI e AutoGen (abstrações mais opinativas, menos inspecionáveis).

#### tenacity
**Onde:** decorador nas chamadas de LLM e HTTP.
**Por quê:** RNF04 pede recuo exponencial com limite de tentativas. Uma linha por ponto de chamada.
**Descartado:** retry manual (repetitivo e fácil de errar no jitter).

---

### 3.4 Dados e coordenação

#### SQLite
**Onde:** `artifacts/queue.db` — tabelas `tasks`, `executions`, `metrics`, `judgments`,
`human_labels`.
**Por quê:** ADR-07 e ADR-10. ACID no lease, durabilidade a queda de processo, zero infraestrutura, e
— decisivo — **o artefato experimental vira um arquivo que acompanha o repositório**, inspecionável
meses depois com qualquer cliente.
**Modo:** WAL, para leitores concorrentes durante a execução.
**Descartado:** Postgres em contêiner — a vazão do sistema é ~0,03 escrita/s na fila; SQLite tem
~10.000× de margem. Resolveria um gargalo três ordens de grandeza acima do que existe, ao custo de um
serviço a mais e da perda do artefato-arquivo.

#### Redis 7 + redis-py
**Onde:** pub/sub de eventos de execução, token bucket distribuído, contador de cota diária.
**Por quê:** ADR-11. Com runner e BFF em contêineres separados, os eventos precisam atravessar
processos (RNF08) e a cota precisa ser contada de forma compartilhada (RNF16).
**Sem volume, de propósito:** nada durável mora ali. Redis fora do ar degrada o streaming ao vivo e
nada mais (RNF17).
**Descartado:** Redis como fila (perderia a durabilidade que o SQLite dá de graça); BFF lendo o JSONL
por *tail* (frágil, latência incompatível com RNF08).

---

### 3.5 Backend / BFF

#### FastAPI + uvicorn
**Onde:** `backend/` — endpoints REST e SSE.
**Por quê:** consistência com o material da TRACTIAN, tipagem nativa com Pydantic, e ASGI necessário
para streaming. O BFF **não contém regra de negócio** — expõe o runner e a biblioteca de análise.
**Descartado:** Flask (sem async nativo nem integração com Pydantic), Django (peso desproporcional).

#### sse-starlette
**Onde:** `src/interfaces/api/stream.py` — `GET /executions/{id}/stream`.
**Por quê:** SSE com reconexão via `Last-Event-ID`, que é o que permite recuperar eventos perdidos a
partir do trace persistido.
**Descartado:** WebSocket — bidirecional é desnecessário aqui; SSE reconecta sozinho e é mais simples
de servir e depurar.

---

### 3.6 Camada de análise

#### pandas + pyarrow
**Onde:** agregação de métricas, `metrics.parquet`.
**Por quê:** agregação por braço, seed, caso e modalidade é trabalho tabular. Parquet mantém tipos e
comprime — e o material da TRACTIAN já usa o formato.
**Descartado:** Polars (mais rápido, mas o volume é de milhares de linhas — a diferença é
irrelevante, e pandas tem integração mais direta com statsmodels).

#### statsmodels
**Onde:** `src/analysis/hypotheses.py` — o teste primário de H1.
**Por quê:** a predição P1.1 é um **termo de interação** em regressão logística
(`acerto ~ intensidade * braço`). O coeficiente da interação **é** o teste da hipótese. statsmodels dá
o coeficiente com erro-padrão e intervalo de confiança em fórmula legível.
**Descartado:** scikit-learn — otimizado para predição, não para inferência; não entrega
erro-padrão de coeficiente, que é justamente o que se precisa aqui.

#### scipy
**Onde:** McNemar (H2, H3), Wilcoxon, bootstrap dos intervalos de confiança.
**Por quê:** testes pareados sobre métricas binárias e contínuas. O bootstrap é **por caso**, não por
execução — os casos são a unidade de amostragem.
**Descartado:** implementação manual dos testes (risco de erro em algo que decide a conclusão do
projeto).

#### scikit-learn
**Onde:** `cohen_kappa_score` na meta-avaliação do juiz.
**Por quê:** uma função. Não justifica implementação própria.

#### DeepEval — três usos, três justificativas

**① Juiz da rubrica — `GEval`**
**Onde:** `evaluation/judge/`.
**Configuração obrigatória:**

```python
GEval(
    name="C1_baseline_declarado",
    evaluation_steps=[...],   # ← EXPLÍCITOS, nunca auto-gerados por `criteria`
    strict_mode=True,         # ← saída binária, alinhada à rubrica (RF26)
    model=modelo_groq,        # ← RNF09: distinto do agente
)
```

> ⚠️ **A documentação declara que o GEval NÃO é determinístico** quando recebe só `criteria` — ele
> regenera os passos de raciocínio a cada execução. Isso colidiria com o **RNF01**. Passar
> `evaluation_steps` fixos é a mitigação documentada, e por isso é obrigatória aqui, não opcional.
> Existe também `DAGMetric` para controle determinístico, a avaliar se o `strict_mode` não bastar.

**② Validação cruzada — `ToolCorrectnessMetric`**
**Onde:** amostra de ~30 execuções, comparada ao nosso M1.
**Por quê:** se uma implementação independente concordar com a nossa, é **validação externa** da
métrica de trajetória. Custo quase zero, argumento forte no README. Suporta ordenação via
`should_consider_ordering=True`.

**③ Diagnóstico no piloto — avaliação em nível de componente**
**Onde:** apenas na rodada piloto (~20 execuções).
**Por quê:** `@observe(metrics=[...])` anexa métricas a **spans individuais** — permite descobrir
coisas como *"o agente escolhe a tool certa no passo 2 mas ignora o retorno no passo 5"*, que
nenhuma métrica agregada revela.

> ⚠️ **Não escala para o experimento.** A conta:
>
> | | |
> | :--- | ---: |
> | 8 passos × 1.021 execuções | 8.168 spans |
> | 1 métrica LLM por span | 8.168 chamadas de juiz |
> | cota do juiz (Groq) | 250/dia |
> | **tempo necessário** | **33 dias** |
>
> No piloto: 20 × 8 = 160 chamadas, uma vez. Cabe.

**O que o DeepEval NÃO cobre.** M5a/M5b, M7, M8, M14, M10, M11 — todas operam sobre a **estrutura da
trajetória** (em qual passo o dado chegou, qual evidência foi ancorada a qual passo), e o
`LLMTestCase` não tem campo para isso. A regra: métrica de **entrada→saída** cabe; métrica de
**trajetória** não.

#### import-linter
**Onde:** contratos em `pyproject.toml`, rodado no CI e como teste.
**Por quê:** substitui um verificador de AST escrito à mão — e faz **mais**: detecta **import
indireto**, cadeias através de módulos intermediários. Um checker de import direto deixaria passar
`analysis/ → utils/ → agents/`, quebrando silenciosamente a promessa de que a análise roda sem SDK
de LLM.

```toml
[[tool.importlinter.contracts]]
name = "Análise não conhece execução"
type = "forbidden"
source_modules = ["src.analysis"]
forbidden_modules = ["src.agents", "src.tools", "google.genai", "openai"]
```

Três tipos de contrato mapeiam nossas três regras: `layers`, `forbidden`, `independence`.

#### polyfactory
**Onde:** `tests/factories/`.
**Por quê:** `ExecutionTrace` tem passos aninhados, handoffs e resolução com evidências. Escrever à
mão em cada teste é inviável para 16 métricas × 2 testes. O polyfactory gera a partir do modelo
Pydantic e o teste **sobrescreve só o campo que importa** — é o que torna o TDD das métricas
executável em dois dias.

---

### 3.7 Frontend

| Tecnologia | Onde | Por quê | Descartado |
| :--- | :--- | :--- | :--- |
| **React 18 + Vite** | toda a interface | Requisito do projeto; build rápido em dev | Next.js — SSR desnecessário para app local |
| **TypeScript** | tipos dos contratos | Espelha os modelos Pydantic; erro de contrato aparece em tempo de compilação | JS puro — perderia a checagem justamente na fronteira mais frágil |
| **TanStack Query** | histórico, métricas, traces | Cache e revalidação; separa naturalmente o caminho de histórico do de streaming | Redux — estado de servidor não é estado de aplicação |
| **EventSource** *(nativo)* | streaming ao vivo | SSE nativo do browser, com reconexão automática | Biblioteca de WS — dependência sem ganho |
| **Tailwind + shadcn/ui** | estilo e componentes | Componentes acessíveis prontos; o tempo vai para o conteúdo, não para CSS | MUI — mais opinativo e pesado |
| **Recharts** | gráficos | Composição em React; suficiente para dose-resposta, barras pareadas e heatmap | D3 puro — poder desnecessário e mais tempo de implementação |

> A **view de dose-resposta** é a que carrega H1 e abre a apresentação. Se em algum momento o
> Recharts não der conta dela especificamente, a saída é SVG sob medida **apenas nesse gráfico** —
> não trocar a biblioteca inteira.

---

### 3.8 Testes e infraestrutura

#### pytest + pytest-asyncio
**Onde:** suíte de avaliação e — mais importante — **testes de invariante**:

| Teste | Garante |
| :--- | :--- |
| Isolamento do gabarito | RNF02 — falha o build se caminho de gabarito for acessível |
| Composição de tools | RNF05 — interseção vazia entre investigador e `tier: impact` |
| Braço de modelo válido | RF33 — combinação (arquitetura, atribuição) prevista |
| Núcleo sem domínio | RNF06 — varredura por `baseline`, `rms`, `spectrum` em `src/tools/core/` |
| Retomada por lease | RNF03 — interrupção em três pontos |
| Aplicabilidade ≠ zero | RF35 — M14 em mono retorna `applicable=0` |

#### Docker Compose v2
**Onde:** `docker-compose.yml` (raiz) — `tractian-api`, `redis`, `backend`, `runner`, `frontend`.
**Por quê:** RNF14. `docker compose up` reproduz o ambiente sem instalar Python, Node ou uv.
**`artifacts/` é bind mount** do host: a fila e os traces precisam sobreviver a `compose down` e
acompanhar o repositório.

---

## 4. Dependências por serviço

```toml
# pyproject.toml (agrupado por extra)
[project]
dependencies = ["pydantic>=2.9", "httpx>=0.27", "pyyaml>=6.0", "tenacity>=8.5"]

[project.optional-dependencies]
mcp      = ["mcp>=1.2", "fastmcp>=2.0"]
agent    = ["google-genai", "openai>=1.50", "langgraph>=0.2"]
eval     = ["pandas>=2.2", "pyarrow>=17", "statsmodels>=0.14",
            "scipy>=1.14", "scikit-learn>=1.5"]
backend  = ["fastapi>=0.115", "uvicorn>=0.30", "sse-starlette>=2.1", "redis>=5.1"]
dev      = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff", "mypy"]
```

> Os grupos espelham os módulos de [`13-padroes-e-estrutura.md`](./13-padroes-e-estrutura.md).

Os extras permitem que a **análise seja instalada sem o agente** — quem for reproduzir os resultados
a partir dos traces não precisa de SDK de LLM nem de chave de API. É a consequência prática de "o
trace é o contrato".

---

## 5. O que não usamos — e por quê

| Descartado | Motivo |
| :--- | :--- |
| **Postgres** | ~0,03 escrita/s na fila; SQLite tem 10.000× de margem. Perderia o artefato-arquivo |
| **RabbitMQ / Celery** | Fila com lease em SQLite resolve; broker seria infraestrutura para um problema inexistente |
| **Kubernetes** | A cota é por conta, não por máquina. Escala horizontal produz zero execuções a mais |
| **LangSmith / Phoenix** | Capturam chamadas de LLM; o trace precisa capturar pré-condições, evidência ancorada e handoffs — custom de qualquer jeito. Citados como evolução |
| **Vector store / RAG** | O endpoint `/knowledge` já existe. RAG só entraria se contribuísse ao experimento; não contribui |
| **Fine-tuning** | Inviável no prazo e irrelevante para as hipóteses |
| **Next.js** | SSR desnecessário em aplicação local |
| **Polars** | Volume de milhares de linhas; ganho irrelevante, integração pior com statsmodels |
| **CrewAI / AutoGen** | Abstrações opinativas; a instrumentação sob medida é o núcleo da entrega |
| **Alembic** | Schema estável e pequeno; migração manual basta |

---

## 6. Política de versões

| Regra | Motivo |
| :--- | :--- |
| Dependências travadas em `uv.lock` e `package-lock.json` | RNF14 — reprodutibilidade |
| Imagens Docker por tag exata, nunca `latest` | `latest` quebra reprodução silenciosamente |
| Modelo, versão e provedor gravados em cada trace | RNF15 — todo resultado reconstituível |
| Versão de métrica e de rubrica na chave primária | A3 — corrigir métrica não invalida resultado antigo |

---

## 7. Riscos de stack

| ID | Risco | Detecção | Resposta |
| :--- | :--- | :--- | :--- |
| **RS-01** | FastMCP não gera schema válido para algum `operationId` | Contagem de tools ≠ 18 na inicialização | Gerar o que der; completar manualmente e registrar quais |
| **RS-02** | Tool calling do Gemini instável em cadeias longas | Taxa de `contract` alta no piloto | Trocar de modelo na semana 1, antes da rodada definitiva |
| **RS-03** | LangGraph dificulta a extração de campos do trace | Instrumentação exigindo gambiarra | O loop interno já é próprio; se persistir, abandonar o grafo e rotear à mão |
| **RS-04** | Recharts insuficiente para a view de dose-resposta | Protótipo do gráfico | SVG sob medida só nesse gráfico |
| **RS-05** | `google-genai` com API diferente da esperada | Falha no piloto | Camada fina de cliente isola o SDK do resto do agente |
