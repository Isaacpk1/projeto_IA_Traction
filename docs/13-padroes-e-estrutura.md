# 13 — Padrões de Projeto e Estrutura de Código

> Este documento responde quatro perguntas: **que tipo de sistema é este**, **qual estilo
> arquitetural interno**, **como o código se organiza** e **quais padrões de projeto são usados — e
> quais deliberadamente não são**.
>
> O critério que governa tudo aqui: um padrão só entra se resolver um problema que este projeto
> realmente tem. Abstração especulativa em projeto de 15 dias é dívida, não investimento.

---

## 1. Que tipo de sistema é este

### A classificação honesta

**Monolito modular com múltiplos pontos de entrada.**

Vale desfazer uma confusão comum: o Docker Compose sobe cinco contêineres, mas isso **não** faz do
sistema um conjunto de microsserviços.

| Critério | Microsserviços | **Este projeto** |
| :--- | :--- | :--- |
| Base de código | uma por serviço | **uma só** |
| Deploy | independente por serviço | **conjunto** |
| Banco de dados | um por serviço | **compartilhado** (`queue.db`) |
| Contratos | por rede, versionados | **tipos Python compartilhados** |
| Time | um por serviço | **uma pessoa** |
| Falha isolada | serviço cai sozinho | processos caem juntos |

`backend` e `runner` são **o mesmo código Python**, subido duas vezes com entrypoints diferentes.
Compartilham contratos, banco e módulos. Isso é um monolito — apenas executado em mais de um
processo.

### O espectro — não é binário

"Monolito ou microsserviço" é uma falsa dicotomia. O espectro real:

```
 acoplado                                                    desacoplado
 ├──────────┬───────────┬────────────┬───────────┬──────────────┤
 Monolito   Monolito    Monolito     Serviços    Micro-      Serverless
 em camadas MODULAR     DISTRIBUÍDO  (SOA)       serviços    / nano
                ▲            ▲
            ESTAMOS AQUI   armadilha
```

| Estilo | Uma frase | Quando faz sentido |
| :--- | :--- | :--- |
| **Monolito em camadas** | Um deployable, sem fronteiras internas reais | Protótipo, script, projeto pequeno |
| **Monolito modular** | Um deployable, fronteiras internas **verificadas** | Time pequeno que quer disciplina sem custo de rede ← **nós** |
| **Monolito distribuído** | Vários deployables **acoplados** — precisam subir juntos | ⚠️ Nunca de propósito. É a armadilha |
| **Serviços (SOA)** | Poucos serviços grandes, por capacidade de negócio | Domínios grandes com times por área |
| **Microsserviços** | Muitos serviços pequenos, deploy e banco próprios | Vários times independentes, escala por componente |
| **Serverless** | Funções sem servidor, escala a zero | Carga muito irregular, pouca coordenação |

Há ainda estilos **ortogonais** que se combinam com esses — *self-contained systems*, arquitetura
celular, *vertical slices*. Não são pontos do mesmo eixo.

### Somos um monolito distribuído? — a crítica honesta

Alguém pode olhar cinco contêineres compartilhando um banco e dizer: *"isso é um monolito
distribuído"*. É uma objeção legítima e vale enfrentá-la de frente, porque provavelmente aparece na
apresentação.

**O que caracteriza um monolito distribuído:** você paga o **custo** da distribuição — latência de
rede, versionamento entre serviços, depuração distribuída, orquestração — sem receber o **benefício**,
que é deploy independente. É ruim porque é o pior dos dois mundos, geralmente por acidente: alguém
quis microsserviços e não conseguiu desacoplar.

**Por que este caso é diferente:**

| | Monolito distribuído | **Este projeto** |
| :--- | :--- | :--- |
| Pretende deploy independente? | Sim, e falha | **Não** — declaradamente conjunto |
| Banco compartilhado | acidente que impede separar | **decisão** — o artefato experimental é um arquivo só |
| Comunicação entre processos | chamadas de rede síncronas e acopladas | **pub/sub efêmero**; se cair, degrada sem perder dado |
| Motivo dos processos | "microsserviços são melhores" | **um motivo operacional concreto**: rodada de horas não pode travar a API |

A diferença não é técnica, é de **intenção declarada**. Um monolito distribuído promete independência
e não entrega. Aqui não há promessa de independência — há uma separação de processo com justificativa
única e registrada.

> Se o runner e o BFF fossem fundidos num processo só, o sistema continuaria correto — só perderia o
> isolamento operacional. Essa reversibilidade é o teste: num monolito distribuído de verdade, você
> **não consegue** voltar.

### Por que essa é a escolha certa aqui

Microsserviços resolvem problemas que este projeto **não tem**: times independentes, deploys
independentes, escala horizontal por componente. Em compensação, custam versionamento de API entre
serviços, consistência eventual e depuração distribuída.

Como a cota do provedor é por conta e não por máquina ([`09-system-design.md`](./09-system-design.md)
§12), escala horizontal produz **zero execuções adicionais**. O único motivo de existirem processos
separados é operacional: uma rodada de horas no runner não pode travar a API que serve o front.

> **Monolito modular = fronteiras de módulo rígidas no código, deploy simples.** Você ganha a
> disciplina de acoplamento sem pagar o custo de rede.

---

## 2. A regra de dependência

O que separa "monolito modular" de "monolito e ponto" é uma regra explícita e **verificável**:

```
        ┌──────────────────────────────────────┐
        │            interfaces/               │   entrypoints
        │        cli · api · worker            │   (dependem de tudo)
        └───────┬──────────┬─────────┬─────────┘
                │          │         │
        ┌───────▼───┐ ┌────▼───────┐ ┌▼───────────┐
        │  agents/  │ │  tools/    │ │ evaluation/│   módulos
        └───────┬───┘ └────┬───────┘ └┬───────────┘   (não se importam
                │          │         │               lateralmente)
                │     ┌────▼─────────▼──┐
                │     │    analysis/    │
                │     └────────┬────────┘
                │              │
        ┌───────▼──────────────▼───────────────┐
        │               core/                  │   núcleo
        │   contracts · ports · errors         │   ZERO dependências
        └──────────────────────────────────────┘
```

**As três regras:**

1. **`core/` não importa nada** do projeto. Só Pydantic e stdlib.
2. **Módulos importam `core/`**, nunca uns aos outros diretamente.
3. **Só `interfaces/` importa módulos.** É onde a composição acontece.

### Por que isso não é burocracia

Cada regra sustenta um requisito que já existe:

| Regra | Sustenta |
| :--- | :--- |
| `analysis/` **não** importa `agents/` | **"O trace é o contrato"** ([`11`](./11-camada-de-analise.md) §2.5). Quem reproduz os resultados não precisa de SDK de LLM |
| `tools/core/` **não** importa domínio | **RNF06** — portabilidade do contrato |
| `agents/` importa `tools/` só via porta | **RF12 / RNF05** — composição por `tier` |
| Ninguém importa `interfaces/` | Entrypoints são folhas, nunca dependência |

**A regra vira contrato verificado** — `import-linter`, declarado em `pyproject.toml`:

```toml
[[tool.importlinter.contracts]]
name = "Camadas"
type = "layers"
layers = ["interfaces", "agents | tools | evaluation | analysis | intake", "core"]

[[tool.importlinter.contracts]]
name = "Análise não conhece execução"
type = "forbidden"
source_modules = ["src.analysis"]
forbidden_modules = ["src.agents", "src.tools", "google.genai", "openai"]

[[tool.importlinter.contracts]]
name = "Módulos independentes"
type = "independence"
modules = ["src.agents", "src.tools", "src.evaluation", "src.analysis", "src.intake"]

[[tool.importlinter.contracts]]
name = "Núcleo de ferramentas sem domínio"
type = "forbidden"
source_modules = ["src.tools.core"]
forbidden_modules = ["src.tools.overlays"]
```

> ⚠️ **Por que não um verificador de AST próprio.** Um checker caseiro pega **import direto**. O
> `import-linter` pega **import indireto** — cadeias através de módulos intermediários. Se
> `analysis/` importasse `utils/`, e `utils/` importasse `agents/`, o checker caseiro passaria — e a
> promessa de que a análise roda sem SDK de LLM seria falsa sem ninguém notar.

> Sem esse teste, a regra é intenção. Com ele, é garantia — e um `import` errado quebra o build.

---

## 3. Qual estilo interno: hexagonal, clean, onion?

### As três são a mesma família

Hexagonal (Cockburn), Onion (Palermo) e Clean (Martin) descrevem **a mesma ideia central** com
vocabulários diferentes:

> **O núcleo não depende da infraestrutura. A dependência aponta para dentro.**

O que difere é o **grau de prescrição**:

| Estilo | Vocabulário | Prescreve | Custo de cerimônia |
| :--- | :--- | :--- | :--- |
| **Hexagonal** | portas, adaptadores, *driving* e *driven* | Só a fronteira | Baixo |
| **Onion** | domínio, serviços de domínio, serviços de aplicação | Camadas concêntricas | Médio |
| **Clean** | Entities, Use Cases, Interface Adapters, Frameworks | Quatro camadas + regra de dependência | Alto |

Clean é Onion com nomes fixos e uma camada explícita de **Use Cases**. Onion é Hexagonal com camadas
concêntricas nomeadas. Hexagonal é a menos prescritiva das três.

### O que este projeto é: **Hexagonal com kernel compartilhado**

```
      ┌──────────── driving adapters ────────────┐
      │   interfaces/cli · interfaces/api        │
      └────────────────┬─────────────────────────┘
                       │  (portas de entrada)
      ┌────────────────▼─────────────────────────┐
      │   MÓDULOS  agents · tools                │
      │            evaluation · analysis         │
      │            ┌──────────────────┐          │
      │            │  core/           │  kernel  │
      │            │  contracts+ports │          │
      │            └──────────────────┘          │
      └────────────────┬─────────────────────────┘
                       │  (portas de saída)
      ┌────────────────▼─────────────────────────┐
      │   driven adapters                        │
      │   llm/gemini · storage/sqlite            │
      │   storage/jsonl · tools/core             │
      └──────────────────────────────────────────┘
```

**Por que Hexagonal e não Clean.** Clean Architecture pressupõe um **domínio rico** a proteger —
Entities com regra de negócio, Use Cases que as orquestram. Este projeto não tem isso, e vale ser
explícito sobre o motivo:

> **O domínio deste sistema mora no prompt e no raciocínio do LLM, não em objetos Python.**

`Resolution`, `EvidenceRef` e `InvestigationReport` são **estruturas de dados**, não entidades com
comportamento. A lógica de negócio — "não confie em insight com baseline invalidado" — está no
overlay e no prompt, não em um método de classe.

Isso normalmente se chamaria *anemic domain model* e seria criticado. **Aqui é correto**, e a
justificativa é declarada: o Python deste projeto faz orquestração, I/O e **medição**. Criar uma
camada de Use Cases e Entities ricas seria cerimônia sobre um domínio que não vive ali.

Adotar Clean aqui produziria pastas como `use_cases/investigate_asset.py` contendo uma classe que
apenas chama o loop ReAct. Indireção sem conteúdo.

### Cada módulo tem a forma que sua natureza pede

Forçar um único estilo em todos os módulos é, por si só, um anti-padrão. A forma interna varia:

| Módulo | Forma interna | Por quê |
| :--- | :--- | :--- |
| **`tools/`** | **Hexagonal puro** | Núcleo genérico + overlay (adaptador de domínio) + HTTP (adaptador de saída). É onde a portabilidade do RNF06 vive. O envelope MCP, se existir, é mais um adaptador — de entrada |
| **`agents/`** | **Strategy + Template Method**, camadas rasas · **sem estado** | Duas implementações de uma interface; o loop é o esqueleto comum. O agente não retém contexto entre turnos (RF43) — a sessão vive no banco, e qualquer worker retoma |
| **`evaluation/`** | **Pipeline + Repository** | Orquestração de trabalho; a fila atrás de uma porta |
| **`analysis/`** | **Funcional — funções puras**, sem camadas | Métrica é `f(trace, golden, versão)`. Camada aqui seria pura burocracia |
| **`interfaces/`** | **Driving adapters** | Traduzem CLI e HTTP em chamadas aos módulos |
| **`core/`** | **Shared kernel** | Contratos e portas; sem lógica |

> **`analysis/` é o exemplo mais claro.** Um scorer é uma função pura de três argumentos. Envolvê-lo
> em `MetricService` → `MetricRepository` → `MetricEntity` não acrescentaria nada e tornaria a
> recomputação (RF34) mais difícil de escrever e de testar.

### E os módulos são *vertical slices*

A organização por **capacidade** (agentes, MCP, avaliação, análise) e não por **camada técnica**
(controllers, services, repositories) é o padrão *vertical slice*. Combina naturalmente com
monolito modular: cada módulo é uma fatia vertical completa, e a regra de dependência garante que as
fatias não se enrosquem.

A alternativa — `controllers/`, `services/`, `models/` — espalharia cada funcionalidade por três
pastas e tornaria impossível ler no repositório o que o sistema faz.

> Isso também atende o que Robert Martin chama de *screaming architecture*: abrir `src/` e ver
> `tools/`, `agents/`, `evaluation/`, `analysis/` diz imediatamente do que o projeto trata. Ver
> `controllers/` e `services/` diria apenas que é um projeto web.

### Resumo da resposta

| Pergunta | Resposta |
| :--- | :--- |
| Monolito ou microsserviço? | **Monolito modular**, executado em múltiplos processos |
| Hexagonal, Onion ou Clean? | **Hexagonal** — portas e adaptadores, sem camada de Use Cases |
| Por que não Clean? | O domínio vive no prompt e no LLM, não em objetos Python. Entities e Use Cases seriam cerimônia |
| Como os módulos se dividem? | **Vertical slices** por capacidade, com **shared kernel** em `core/` |
| Todos os módulos têm a mesma forma? | **Não** — cada um tem a forma que sua natureza pede |

---

## 4. Estrutura de pastas

```
projeto_IA_Traction/
│
├─ docs/                          # 01 a 13
├─ docker-compose.yml
├─ pyproject.toml
│
├─ src/
│  │
│  ├─ core/                       # ◄── NÚCLEO · zero dependências internas
│  │  ├─ contracts/
│  │  │  ├─ trace.py              # TraceStep, Handoff, ExecutionTrace
│  │  │  ├─ resolution.py         # Resolution, EvidenceRef, Finding
│  │  │  ├─ handoff.py            # InvestigationReport, ContextReport
│  │  │  ├─ golden.py             # GoldenCase, ExpectedStep
│  │  │  └─ metrics.py            # MetricResult, Judgment
│  │  ├─ ports/                   # interfaces — sem implementação
│  │  │  ├─ llm.py                # LLMClient
│  │  │  ├─ tools.py              # ToolProvider
│  │  │  ├─ queue.py              # WorkQueue
│  │  │  ├─ trace_sink.py         # TraceSink
│  │  │  └─ event_bus.py          # EventBus
│  │  ├─ errors.py                # taxonomia: infra · behavior · contract · budget
│  │  └─ ids.py                   # task_id, execution_id, step_id
│  │
│  ├─ tools/                      # ◄── MÓDULO · camada de ferramentas (ADR-01)
│  │  ├─ core/                    # genérico — RNF06, sem domínio
│  │  │  ├─ openapi_parser.py
│  │  │  ├─ tool_factory.py
│  │  │  ├─ http_executor.py
│  │  │  └─ tier_registry.py
│  │  ├─ overlays/
│  │  │  └─ tractian.overlay.yaml # ◄── único lugar com domínio
│  │  ├─ provider.py              # ToolProvider — o que os agentes consomem
│  │  └─ mcp_wrapper.py           # ◄── OPCIONAL · envelope MCP (ADR-01, passo 3)
│  │
│  ├─ agents/                     # ◄── MÓDULO · arquiteturas
│  │  ├─ react.py                 # o loop — compartilhado por todos
│  │  ├─ architectures/
│  │  │  ├─ base.py               # Architecture (Strategy)
│  │  │  ├─ mono.py               # braço A
│  │  │  └─ multi.py              # braços B e C (grafo LangGraph)
│  │  ├─ roles/
│  │  │  ├─ orchestrator.py
│  │  │  ├─ contextualizer.py
│  │  │  ├─ investigator.py
│  │  │  └─ executor.py
│  │  ├─ prompts/
│  │  │  ├─ base.md               # ◄── prompt base compartilhado (RF33)
│  │  │  └─ roles/*.md            # delta por papel
│  │  └─ tracer.py
│  │
│  ├─ intake/                     # ◄── MÓDULO · ingestão de tickets (produto)
│  │  ├─ ticket.py                # validação e normalização
│  │  ├─ prioritizer.py           # criticidade do ativo → prioridade (RF38)
│  │  └─ session.py               # sessão multi-turno (RF40, RF41)
│  │
│  ├─ evaluation/                 # ◄── MÓDULO · execução da avaliação
│  │  ├─ golden/
│  │  │  ├─ base_cases.json
│  │  │  ├─ adversarial_cases.json
│  │  │  └─ generator.py
│  │  ├─ runner/
│  │  │  ├─ queue_sqlite.py       # WorkQueue → SQLite
│  │  │  ├─ worker.py
│  │  │  ├─ rate_limiter.py       # token bucket (local e Redis)
│  │  │  └─ isolation_guard.py    # RNF02 — bloqueante
│  │  └─ judge/
│  │     ├─ rubric.yaml
│  │     ├─ applicability.py      # Specification — decidido em código
│  │     └─ runner.py
│  │
│  ├─ analysis/                   # ◄── MÓDULO · não importa agents/ nem tools/
│  │  ├─ scorers/                 # um arquivo por métrica
│  │  │  ├─ base.py               # Scorer (protocolo)
│  │  │  ├─ trajectory.py         # M1, M2
│  │  │  ├─ arguments.py          # M3
│  │  │  ├─ decision.py           # M4
│  │  │  ├─ preconditions.py      # M5a, M5b
│  │  │  ├─ grounding.py          # M8 · V1
│  │  │  ├─ safety.py             # M10, M11
│  │  │  ├─ stability.py          # M12, M13
│  │  │  └─ handoff_loss.py       # M14
│  │  ├─ registry.py              # catálogo de scorers por versão
│  │  ├─ aggregate.py
│  │  ├─ hypotheses.py            # dose-resposta, McNemar, não-inferioridade
│  │  ├─ meta_eval.py             # kappa
│  │  └─ api.py                   # superfície pública do módulo
│  │
│  ├─ storage/                    # ◄── MÓDULO · adaptadores de persistência
│  │  ├─ sqlite/
│  │  │  ├─ schema.sql
│  │  │  └─ repositories.py       # Repository
│  │  ├─ jsonl_traces.py          # TraceSink → arquivo
│  │  └─ redis_bus.py             # EventBus → Redis
│  │
│  ├─ llm/                        # ◄── MÓDULO · adaptadores de provedor
│  │  ├─ gemini.py                # LLMClient → google-genai
│  │  ├─ openai_compat.py         # LLMClient → Groq e OpenRouter
│  │  └─ factory.py               # papel → cliente (valida RF33)
│  │
│  └─ interfaces/                 # ◄── ENTRYPOINTS · composição
│     ├─ cli.py                   # atender um chamado
│     ├─ worker.py                # runner
│     └─ api/                     # BFF
│        ├─ main.py
│        ├─ routes/
│        └─ stream.py             # SSE
│
├─ frontend/
│  └─ src/
│     ├─ pages/                   # Attendance · Trace · Dashboard · Compare
│     ├─ components/
│     ├─ lib/
│     └─ types/                   # gerados dos contratos Pydantic
│
├─ tests/
│  ├─ test_architecture.py        # regra de dependência
│  ├─ test_invariants.py          # RNF02, RNF05, RF33, RF35
│  └─ ...
│
└─ artifacts/                     # bind mount — o artefato experimental
   ├─ queue.db
   ├─ traces/{run_id}/
   └─ runs/{run_id}/
```

### Duas decisões de organização

**① `llm/` e `storage/` separados dos módulos que os usam.** São adaptadores de infraestrutura. Se
ficassem dentro de `agents/` e `evaluation/`, a troca de provedor tocaria código de domínio.

**② Um arquivo por métrica em `analysis/scorers/`.** Parece exagero para 16 métricas, mas cada uma é
uma função pura versionada (princípio A1), e corrigir M8 não pode arriscar M4. Arquivos separados
tornam o diff da correção trivial de revisar.

---

## 5. Padrões de projeto

> A divisão abaixo é o que importa: alguns padrões são **exigidos pelo experimento** — sem eles a
> medição fica inválida. Outros são conveniência. Misturar os dois na apresentação enfraquece o
> argumento.

### 5.1 Padrões exigidos pelo experimento

#### **Strategy** — as arquiteturas

```python
# core/ports/architecture.py
class Architecture(Protocol):
    name: Literal["mono", "multi"]
    async def run(self, case: Case, ctx: RunContext) -> ExecutionTrace: ...
```

`MonoArchitecture` e `MultiArchitecture` implementam a mesma interface. O runner não sabe qual está
usando.

**Por que é exigência, não estética.** H1 compara duas arquiteturas. Se cada uma tivesse seu próprio
runner, sua própria instrumentação e seu próprio caminho de persistência, **a diferença medida
incluiria a diferença entre os runners**. Strategy é o que garante que tudo fora da variável
manipulada seja literalmente o mesmo código.

> Sem Strategy, H1 não é testável. É o padrão mais load-bearing do projeto.

---

#### **Ports & Adapters (Hexagonal)** — provedores e persistência

```python
# core/ports/llm.py — a porta
class LLMClient(Protocol):
    async def chat(self, messages: list[Message],
                   tools: list[ToolDef], **kw) -> LLMResponse: ...

# llm/gemini.py e llm/openai_compat.py — os adaptadores
```

**Por que é exigência.** Três requisitos dependem disso:

- **RNF09** — juiz de provedor distinto: dois adaptadores atrás de uma porta
- **RNF06** — portabilidade do contrato: `tools/core/` fala com `ToolProvider`, não com a TRACTIAN
- **ADR-12** — a mesma porta admite ferramentas de terceiros (Slack, Jira) para escalonamento, sem
  distinguir origem: são tools com `tier`, e o Executor as recebe igual
- **"O trace é o contrato"** — `analysis/` não conhece `LLMClient`, por isso roda sem SDK de LLM

O último é o mais concreto: é o que permite que quem for avaliar o projeto reproduza os resultados
sem chave de API.

---

#### **Repository** — persistência trocável

```python
class WorkQueue(Protocol):
    def enqueue(self, tasks: list[Task]) -> int: ...
    def lease(self, worker: str, ttl: float) -> Task | None: ...
    def complete(self, task_id: str, execution_id: str) -> None: ...
    def fail(self, task_id: str, error_class: ErrorClass) -> None: ...
```

**Por que é exigência.** O ADR-10 promete que trocar SQLite por Postgres não tocaria o runner. Sem
Repository, essa promessa é falsa — e uma promessa arquitetural não verificável é pior que nenhuma.

---

#### **Specification** — aplicabilidade de critério

```python
# evaluation/judge/applicability.py
APPLICABILITY: dict[str, Callable[[JudgeContext], bool]] = {
    "C1_baseline_declarado": lambda c: c.analysis_discussed and c.mode == "baseline",
    "C3_incerteza_honesta":  lambda c: c.degradation_intensity > 0,
    ...
}
```

**Por que é exigência.** Se o juiz decidisse a aplicabilidade, ele poderia marcar `not_applicable`
para escapar de um critério difícil — e a taxa de `false` cairia sem que a qualidade tivesse subido
(risco RA-02). Decidir fora do juiz fecha essa saída.

---

### 5.2 Padrões de conveniência

| Padrão | Onde | O que resolve |
| :--- | :--- | :--- |
| **Template Method** | `agents/react.py` | O esqueleto do loop é um só; papéis variam tools e prompt. Garante que o tracing seja idêntico em todos |
| **Factory** | `tools/core/tool_factory.py` | `operationId` + overlay → tool executável |
| **Factory** | `llm/factory.py` | papel → cliente; **valida RF33** e aborta se os papéis divergirem de um braço previsto |
| **Registry** | `tools/core/tier_registry.py` | Catálogo por `tier`, alimenta a composição de RF12 |
| **Registry** | `analysis/registry.py` | Scorers por versão, sustenta a recomputação de RF34 |
| **Pipeline** | `analysis/scorers/` | Lista de scorers aplicada em sequência sobre o trace |
| **Decorator** | `tenacity` no cliente | Retry com recuo exponencial (RNF04) |
| **Observer / Pub-Sub** | `storage/redis_bus.py` | Eventos runner → BFF (RNF08) |
| **Command** | `Task` na fila | Intenção serializada e reexecutável; base da idempotência |
| **Value Object** | `EvidenceRef`, `MetricResult` | Imutáveis, comparáveis por valor |
| **Facade** | `analysis/api.py` | Superfície única do módulo para o BFF e a CLI |

---

### 5.3 Padrões deliberadamente NÃO usados

Registrar o que se decidiu não fazer vale tanto quanto o que se fez.

| Padrão | Por que não |
| :--- | :--- |
| **Container de injeção de dependência** | Python resolve com argumentos padrão e composição em `interfaces/`. Um container acrescentaria mágica e um arquivo de configuração para resolver nada |
| **Event Sourcing** | O trace é append-only, mas o estado **não** é reconstruído a partir dele. O estado atual vive em tabelas. Event Sourcing traria projeções e replay sem necessidade |
| **CQRS formal** | A separação leitura/escrita já existe naturalmente (runner escreve, BFF lê). Formalizar com modelos separados seria cerimônia |
| **Abstract Factory** | Uma Factory basta. Fábrica de fábricas para dois provedores é abstração sobre abstração |
| **Unit of Work** | As transações são pequenas e locais ao lease. O `sqlite3` já dá o suficiente |
| **Mediator** | O orquestrador **é** o mediador entre agentes — mas implementado como agente, não como padrão genérico de mensageria |

> **A regra que governa esta seção:** *só crie uma porta onde existe, ou está prometida, uma segunda
> implementação.* `LLMClient` tem duas (Gemini, OpenAI-compat). `WorkQueue` tem uma e uma promessa
> registrada em ADR. `Architecture` tem duas — é a variável do experimento. Interface para algo que
> terá uma implementação para sempre é indireção sem retorno.

---

## 6. Módulo → requisitos

| Módulo | Requisitos atendidos | Contêiner |
| :--- | :--- | :--- |
| `core/` | RNF13 (validação em toda fronteira) | — biblioteca |
| `tools/` | RF02, RF03, RF04, RF12 · RNF06, RNF07 | biblioteca (envelope MCP opcional) |
| `agents/` | RF01, RF05–RF11, RF15–RF18 · RNF01 | runner |
| `intake/` | RF37, RF38, RF40, RF41, RF43 · RNF18, RNF19 | backend |
| `evaluation/` | RF20–RF23, RF26, RF27, RF36 · RNF02–RNF04, RNF16 | runner |
| `analysis/` | RF24, RF25, RF28, RF34, RF35 | biblioteca |
| `storage/` | RF17 · RNF03, RNF17 | runner + backend |
| `llm/` | RF33 · RNF09 | runner |
| `interfaces/` | RF19, RF29–RF32 · RNF08 | backend + CLI |

---

## 7. Ordem de construção

Derivada da regra de dependência: **do núcleo para fora**. Nada depende do que ainda não existe.
O cronograma com datas está em [`14-roadmap-e-testes.md`](./14-roadmap-e-testes.md).

| # | O quê | Bloqueia |
| :-- | :--- | :--- |
| 1 | `core/contracts/` + `core/ports/` | tudo |
| 2 | `tools/core/` + overlay | agentes |
| 3 | `llm/` (adaptador Gemini) | agentes |
| 4 | `agents/react.py` + `mono.py` | braço A |
| 5 | `storage/` + `evaluation/runner/` | qualquer rodada |
| 6 | `analysis/scorers/` | qualquer resultado |
| 7 | `agents/multi.py` | braços B e C |
| 8 | `evaluation/judge/` | rubrica |
| 9 | `interfaces/api/` + `frontend/` | demonstração |

> **O passo 1 é curto e destrava tudo.** São os modelos Pydantic e os protocolos — algumas centenas
> de linhas sem lógica. Escrever isso primeiro evita a maior fonte de retrabalho: descobrir na
> metade que o schema do trace não comporta um campo que a análise precisa.
