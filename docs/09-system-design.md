# 09 — System Design

> O [`05-arquitetura.md`](./05-arquitetura.md) responde **o que existe e como se relaciona**.
> Este documento responde **como opera**: concorrência, identificadores, falhas, orçamentos,
> contratos e limites. É a camada onde o projeto encosta na realidade dos provedores.
>
> Ele cobre o caminho **chamado → agente → API → trace**. O que vem depois — trace → métrica →
> veredito → estatística → visualização — está em
> [`11-camada-de-analise.md`](./11-camada-de-analise.md), cuja §2.5 especifica a fronteira entre as
> duas metades. A stack detalhada está em [`12-stack.md`](./12-stack.md).

---

## 1. Princípios operacionais

| # | Princípio | Consequência |
| :-- | :--- | :--- |
| **O1** | **A cota do provedor é a restrição dominante** | O dimensionamento do experimento decorre da cota, não do contrário |
| **O2** | **Toda unidade de trabalho é idempotente e endereçável** | Reexecutar é seguro; retomar é trivial |
| **O3** | **Falha de infraestrutura ≠ falha de comportamento** | Só a segunda é resultado experimental |
| **O4** | **Nada é reescrito depois de gravado** | Artefato experimental auditável |
| **O5** | **Projete para distribuir, execute concentrado** | A arquitetura suporta N máquinas; o gargalo não é local |

---

## 2. Orçamento de tokens

### 2.1 O custo de uma execução ReAct é quadrático

O loop reenvia a conversa inteira a cada passo. O contexto do passo *n* contém tudo dos passos
anteriores — o custo acumula, não soma.

```
custo_total = Σ(k=0..n-1) [ sistema + catálogo + k × (raciocínio + retorno) ]
```

Com valores estimados — sistema 800, catálogo enriquecido ~150 tokens/tool, retorno médio 900,
raciocínio 150:

| Passos | Mono (18 tools ≈ 2.700) | Multi (8 tools ≈ 1.200) | Δ |
| ---: | ---: | ---: | ---: |
| 6 | 36.750 | 27.750 | −24% |
| **8** | **57.400** | **45.400** | **−21%** |
| 10 | 82.250 | 67.250 | −18% |
| 12 | 111.300 | 93.300 | −16% |

**Duas leituras obrigatórias desta tabela:**

**① O limite de passos é decisão de viabilidade, não de robustez.** Ir de 8 para 12 passos custa
94% mais tokens. O valor 12 que constava originalmente em RF16 foi escolhido sem cálculo; foi
corrigido para **8** após esta análise.

**② Uma chamada de especialista multi carrega ~21% menos contexto estimado** — porque cada papel
recebe catálogo menor. Isso não significa que a execução multi completa seja mais barata: ela pode
fazer mais chamadas e envolver mais agentes. O custo total é medido por braço.

- *Operacionalmente:* cada chamada pode ser menor, mas a execução completa pode custar mais
- *Metodologicamente:* é um confundidor de H1 — se a multi vencer, parte do ganho pode vir de
  contexto menor, não de isolamento de contexto. Registrado como limitação **L11**

### 2.2 Alavancas de economia

| Alavanca | Economia | Custo |
| :--- | ---: | :--- |
| Reduzir passos de 12 → 8 | ~48% | Menos investigação possível; casos difíceis podem truncar |
| Enxugar descrições do overlay | ~20% | **É a variável independente de H3** — não pode ser mexida livremente |
| Resumir séries longas na camada de tools | ~15% | **Muda o que o agente vê** — afeta a validade da medição |
| Podar retornos antigos do contexto | ~30% | Altera o mecanismo que H1 investiga — proibido em E1 |

> As três últimas interferem no que está sendo medido. Só a primeira é gratuita do ponto de vista
> metodológico, e por isso é a única aplicada por padrão.

---

## 3. Provedores, cotas e vazão

### 3.1 Referências de cota — validar na conta

| Provedor | Modelo | RPM | RPD | TPM | TPD |
| :--- | :--- | ---: | ---: | ---: | ---: |
| **Google AI Studio** | Gemini 2.5 Flash | variável | variável | variável | — |
| **Groq** | `gpt-oss-120b` | 30 | 1.000 | 8K | 200K |
| **OpenRouter** | `:free` sem créditos | 20 | 50 | — | — |
| **OpenRouter** | `:free` com US$10 | 20 | 1.000 | — | — |

Os valores públicos mudam por plano, projeto e modelo. A tabela é referência para o piloto, não
premissa de cronograma. O limite efetivo é registrado a partir dos headers e do console da conta.

### 3.2 Vazão resultante do piloto

O teto de oito passos é **por agente**, portanto A, B e C têm custos distintos. A vazão é calculada
com o p95 observado de chamadas por execução:

| Papel | Provedor | Limite mordente | Vazão |
| :--- | :--- | :--- | ---: |
| **Agente A/B/C** | Gemini | menor limite observado | `RPD / p95(chamadas por execução do braço)` |
| **Juiz** | Groq `openai/gpt-oss-120b` | menor limite observado | definida pelo piloto |
| **Extensão P3.3** | OpenRouter `:free` | RPD observado | fora do núcleo |

> RPM, RPD e tokens são medidos no piloto. Nenhum deles é descartado por estimativa antes da
> primeira execução real.

### 3.3 Atribuição de modelo por papel

Existem **três braços válidos**, e a validade decorre de qual variável fica constante:

| Braço | Arquitetura | Orquestrador | Contextualizador | Investigador | Executor |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A** | mono | — agente único: Flash | | | |
| **B** | multi | Flash | Flash | Flash | Flash |
| **C** | multi | **Flash-Lite** | **Flash-Lite** | Flash | Flash |

```
   A  vs  B   →  isola ARQUITETURA      (modelo constante)   → H1
   B  vs  C   →  isola HETEROGENEIDADE  (arquitetura const.) → H4
   A  vs  C   →  mudam as duas          → ININTERPRETÁVEL ⛔
```

**Por que A vs C é proibido.** A arquitetura mono tem um agente só — não há papéis a diferenciar,
logo "mono heterogêneo" não existe. Comparar A com C mudaria arquitetura **e** atribuição de modelo
simultaneamente, e nenhuma análise posterior separaria os efeitos. O runner valida a combinação
(arquitetura, atribuição) contra a lista de braços previstos e aborta se não corresponder (RF33).

**Por que baratear em vez de reforçar.** O desenho conservador não presume cota suficiente para um
modelo mais forte no investigador; o piloto verifica isso. A heterogeneidade planejada reduz a
capacidade nos papéis fáceis, que é também uma decisão real de produto.

**Validação operacional:** o piloto verifica se Flash e Flash-Lite possuem cotas independentes na
conta usada. H4 permanece condicional até essa confirmação.

```
                        ▲
                        │ avaliado por
┌───────────────────────┴──────────────────────────────┐
│  FORA DO SISTEMA SOB TESTE                           │
│  Juiz — Groq, família e provedor distintos (RNF09)   │
└──────────────────────────────────────────────────────┘
```

**O juiz é exceção legítima** porque não integra o sistema medido, e ser distinto é exigência
(RNF09) contra viés de auto-preferência.

### 3.4 Controle de vazão

Duas peças, com papéis distintos:

> **Nota de topologia.** O `RateLimiter` abaixo é in-process. Com runner e BFF em contêineres
> distintos consumindo a mesma cota da conta, o controle precisa ser **compartilhado** — implementado
> em Redis com script Lua atômico. Ver [`11-camada-de-analise.md`](./11-camada-de-analise.md) §8.3.
> A lógica é idêntica; muda apenas onde o estado do balde vive.

#### Token bucket — para o limite conhecido

```python
class RateLimiter:
    """Regula a taxa global. 15 RPM = 1 requisição a cada 4 s."""
    def __init__(self, rpm: int):
        self.intervalo = 60.0 / rpm
        self.proxima = 0.0
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self.lock:
            agora = time.monotonic()
            espera = max(0.0, self.proxima - agora)
            self.proxima = max(agora, self.proxima) + self.intervalo
        if espera:
            await asyncio.sleep(espera)
```

Todos os workers passam por aqui antes de cada chamada. **A concorrência deixa de determinar a
vazão** — 3 workers ou 8 produzem os mesmos 15 RPM. Os workers existem apenas para sobrepor
latência de I/O.

#### AIMD — rede de segurança para o limite desconhecido

```python
class AIMDController:
    """Additive Increase, Multiplicative Decrease — mesmo princípio do TCP."""
    def __init__(self, teto: int = 8):
        self.n, self.teto, self.sucessos = 1, teto, 0

    def on_success(self) -> None:
        self.sucessos += 1
        if self.sucessos >= 10:                    # sobe devagar
            self.n = min(self.n + 1, self.teto)
            self.sucessos = 0

    def on_rate_limit(self) -> None:
        self.n = max(1, self.n // 2)               # desce rápido
        self.sucessos = 0
```

**A assimetria é intencional.** Ficar 1 abaixo do ótimo custa um pouco de vazão; ficar acima gera
429 em cascata, desperdiça cota e pode acionar penalidade. Subir com cautela, recuar com agressão.

> **Decisão:** o token bucket é o mecanismo primário, porque a cota do Gemini é documentada e
> constante. O AIMD entra apenas se surgirem 429 inesperados. Construir um controlador sofisticado
> para uma constante conhecida seria complexidade sem retorno.

#### Guarda de cota diária — o limite que realmente morde

```python
if consumo_hoje + CHAMADAS_POR_EXECUCAO > COTA_DIARIA * MARGEM:
    fila.pausar_lease()          # simplesmente para de alocar trabalho
```

A fila com lease torna isso trivial: parar de alocar e retomar no dia seguinte usa exatamente o
mesmo mecanismo da retomada após queda. Nada adicional a construir.

---

## 4. Modelo de execução — fila com lease

### 4.1 Por que fila

Duas razões, de naturezas diferentes.

**Razão de produto.** Tickets chegam continuamente e sem aviso; o atendimento leva dezenas de
segundos. Sem fila, ou o cliente espera bloqueado, ou o sistema perde entrada sob pico. A fila é o
que desacopla **receber** de **processar** — e é o que permite responder em 200 ms (RNF18) enquanto
o trabalho real acontece depois.

**Razão de engenharia.** Quatro requisitos que estavam especificados como mecanismos separados —
checkpoint (RF23), retry (RNF04), concorrência (RF22) e retomada (RNF03) — são **a mesma coisa**
vista de ângulos diferentes. Modelar como fila durável resolve os quatro com um mecanismo.

> **O lease com TTL serve os dois mundos.** Num experimento, devolve à fila a tarefa de um worker que
> morreu. Em produção, faz exatamente o mesmo por um ticket de cliente. Não houve adaptação — o
> mecanismo já era o certo.

### 4.2 Ciclo de vida

```
                  ┌──────────┐
    enqueue ─────►│ pending  │◄──────────────┐
                  └────┬─────┘               │
                       │ lease(worker, ttl)  │ lease expirado
                  ┌────▼─────┐               │ OU falha de infra
              ┌───│  leased  │───────────────┘ (attempts++, backoff)
              │   └──────────┘
   concluída  │                     attempts > máx
              ▼                            │
        ┌──────────┐                 ┌─────▼──────┐
        │   done   │                 │   failed   │
        └──────────┘                 └────────────┘
```

**O lease é o que distingue esta fila de um checkpoint ingênuo.** O worker não remove a task — ele a
reserva por um prazo. Se o processo morrer no meio de uma execução, a reserva vence e a task retorna
a `pending` sozinha. Um checkpoint que só registra conclusões deixaria essa task em limbo
permanente.

### 4.3 Backend: SQLite

Não é escolha de conveniência — é a correta para o contexto:

| Propriedade | Por que importa aqui |
| :--- | :--- |
| ACID com transação no lease | `UPDATE ... WHERE state='pending'` atômico entre workers |
| Durável a queda de processo | Requisito RNF03 |
| Zero infraestrutura | Sem Redis, sem broker, sem container adicional |
| WAL: leitores concorrentes | O dashboard consulta durante a execução |
| Consulta indexada | **Resolve o problema de o front ler centenas de traces sem carregar tudo em memória** |

```sql
CREATE TABLE tasks (
  task_id       TEXT PRIMARY KEY,     -- determinístico (ver §5)
  kind          TEXT NOT NULL,        -- ticket | experiment      ◄── produto
  priority      INTEGER NOT NULL,     -- derivada da criticidade  ◄── produto
  source        TEXT NOT NULL,        -- api | ui | batch         ◄── produto
  received_at   REAL NOT NULL,        --                          ◄── produto
  session_id    TEXT,                 -- multi-turno              ◄── produto
  run_id        TEXT,                 -- só para kind=experiment
  case_id       TEXT NOT NULL,
  architecture  TEXT NOT NULL,        -- mono | multi
  seed          TEXT,
  repetition    INTEGER NOT NULL,
  state         TEXT NOT NULL,        -- pending | leased | done | failed
  attempts      INTEGER NOT NULL DEFAULT 0,
  leased_by     TEXT,
  lease_expires REAL,
  execution_id  TEXT,                 -- da tentativa bem-sucedida
  error_class   TEXT,                 -- taxonomia da §6
  created_at    REAL NOT NULL,
  completed_at  REAL,
  UNIQUE(run_id, case_id, architecture, seed, repetition)
);
CREATE INDEX idx_lease   ON tasks(state, priority DESC, received_at);
CREATE INDEX idx_run     ON tasks(run_id, state);
CREATE INDEX idx_tickets ON tasks(kind, state, priority DESC);

CREATE TABLE executions (
  execution_id  TEXT PRIMARY KEY,
  task_id       TEXT NOT NULL REFERENCES tasks(task_id),
  attempt       INTEGER NOT NULL,
  model         TEXT NOT NULL,
  provider      TEXT NOT NULL,
  trace_path    TEXT NOT NULL,        -- ponteiro para o JSONL
  decision      TEXT,
  stop_reason   TEXT,
  steps         INTEGER,
  tokens_in     INTEGER,
  tokens_out    INTEGER,
  duration_ms   REAL,
  error_class   TEXT,
  started_at    REAL NOT NULL,
  ended_at      REAL
);
CREATE INDEX idx_exec_task ON executions(task_id);
```

### 4.4 Idempotência de enfileiramento

`task_id` é hash determinístico da tupla de trabalho, com restrição `UNIQUE` na chave natural.
Reenfileirar o experimento inteiro é seguro — as tasks concluídas colidem e são ignoradas:

```python
def task_id(run_id, case_id, arch, seed, rep) -> str:
    chave = f"{run_id}|{case_id}|{arch}|{seed or 'noseed'}|{rep}"
    return hashlib.sha256(chave.encode()).hexdigest()[:16]

# retomar == reenfileirar
cur.executemany(
    "INSERT OR IGNORE INTO tasks (...) VALUES (...)", todas_as_tasks
)
```

Não existe lógica de "descobrir o que já fiz". A restrição de unicidade é a lógica.

### 4.5 Operação de lease

```sql
-- transação única: recupera expiradas e reserva a próxima
UPDATE tasks SET state='pending', attempts=attempts+1
 WHERE state='leased' AND lease_expires < :agora;

UPDATE tasks
   SET state='leased', leased_by=:worker, lease_expires=:agora+:ttl
 WHERE task_id = (
   SELECT task_id FROM tasks
    WHERE state='pending' AND attempts < :max
      AND (:run_id IS NULL OR run_id=:run_id)
    ORDER BY attempts ASC, priority DESC, received_at ASC LIMIT 1
 )
RETURNING task_id, case_id, architecture, seed, repetition;
```

No worker contínuo, `:run_id` é `NULL` e tickets e experimentos competem pela mesma fila; no comando
de retomada de uma rodada, o parâmetro restringe o lease àquele experimento. Em SQL real, a decisão
entre esses dois escopos é montada com cláusulas parametrizadas — nunca com `run_id = NULL`.

`ORDER BY attempts ASC, priority DESC, received_at ASC` combina três critérios, nessa ordem:

1. **Tentativas** — tasks que nunca falharam vêm primeiro; as problemáticas vão para o fim e a
   execução não fica presa numa que falha repetidamente
2. **Prioridade** — derivada da criticidade do ativo (RF38). Ativo crítico ultrapassa
3. **Chegada** — desempate por ordem, o que garante ausência de inanição dentro de uma prioridade

> **A mesma consulta serve ticket e experimento.** Tarefas de `kind = experiment` recebem prioridade
> base e são drenadas quando não há ticket de cliente aguardando. É a materialização do RF39: um
> caminho só.

---

## 5. Hierarquia de identificadores

| ID | Escopo | Geração | Propósito |
| :--- | :--- | :--- | :--- |
| `experiment_id` | E1, E2, E3, E4 | fixo | Agrupa varreduras |
| `run_id` | uma varredura de configuração | ULID | Isola uma rodada completa |
| **`task_id`** | uma unidade de trabalho | **determinístico** — hash da tupla | **Idempotência** |
| **`execution_id`** | **uma tentativa** da task | **ULID por tentativa** | **Separa infra de comportamento** |
| `step_id` | um passo do loop ReAct | `{execution_id}.{n}` | Ancoragem de evidência |
| `call_id` | uma chamada JSON-RPC ao MCP | `{step_id}.{k}` | Correlação com a API |

### 5.1 Por que `task_id` e `execution_id` são separados

A task é **o que precisa ser feito**; a execução é **uma tentativa de fazer**.

Uma task que tomou 429 duas vezes e completou na terceira tem **um** `task_id` e **três**
`execution_id`. Sem essa separação, a pergunta "o agente falhou?" não tem resposta — as duas
primeiras falhas foram do provedor, não do agente.

É essa distinção que sustenta a taxonomia da §6. Colapsar os dois identificadores inflaria a taxa de
erro do agente com instabilidade de rede.

### 5.2 Propagação da correlação

No caminho padrão in-process, o worker passa `run_id` e `execution_id` diretamente ao
`TraceEmitter`. Se o envelope MCP opcional estiver habilitado, o mesmo contexto chega no handshake,
não como argumento de tool:

```
initialize {
  clientInfo: { name: "agente-tractian",
                run_id: "...", execution_id: "...", architecture: "multi" }
}
```

O adaptador carimba todo `call_id` com esse contexto. **O agente não sabe que isso existe** — nenhuma
poluição de schema, nenhum risco de o modelo errar o identificador.

Isso só funciona porque a decisão é **um subprocesso MCP por worker** (§7.2). Com servidor
compartilhado, a correlação teria que viajar como argumento de tool.

---

## 6. Taxonomia de falhas

A separação abaixo é a diferença entre medir o agente e medir a internet.

| Classe | Exemplos | Destino da task | Conta como resultado? |
| :--- | :--- | :--- | :--- |
| **`infra`** | 429, timeout, 5xx, conexão perdida | volta a `pending`, novo `execution_id` | ❌ Descartada da análise |
| **`behavior`** | loop, parada prematura, decisão errada, alucinação | `done` — execução registrada | ✅ **É o resultado** |
| **`contract`** | retorno fora do schema, tool inexistente | `failed` + alerta | ❌ Bug a investigar |
| **`budget`** | cota diária esgotada | volta a `pending`, sem incrementar tentativas | ❌ Retomada no dia seguinte |

```python
def classificar(exc) -> str:
    if isinstance(exc, (RateLimitError, TimeoutError, ConnectionError)):
        return "infra"
    if isinstance(exc, (ValidationError, UnknownToolError)):
        return "contract"
    if isinstance(exc, QuotaExhausted):
        return "budget"
    return "behavior"
```

> **`budget` não incrementa `attempts`.** Cota esgotada não é falha da task — é ausência de recurso.
> Contar como tentativa levaria tasks legítimas ao estado `failed` por motivo alheio a elas.

**Relatório obrigatório.** Todo resultado experimental informa a contagem por classe. Uma taxa de
`infra` alta invalida a comparação daquela rodada, porque as execuções descartadas podem não ser
aleatórias — casos mais longos consomem mais chamadas e têm mais chance de tomar 429, o que
enviesaria a amostra contra os casos difíceis. Se `infra` exceder 10%, a rodada é repetida.

---

## 7. Topologia de execução

### 7.1 Processos locais

```
┌─────────────────────────────────────────────────────┐
│  Máquina local                                      │
│                                                     │
│  :8000  API TRACTIAN (FastAPI, uvicorn)             │
│  :8100  Backend/BFF (FastAPI + SSE)                 │
│  :5173  Front (Vite dev server)                     │
│                                                     │
│  :6379  Redis (coordenação efêmera)                 │
│                                                     │
│  runner (processo)                                  │
│   ├─ worker 1 ──► subprocesso MCP 1 ──┐             │
│   ├─ worker 2 ──► subprocesso MCP 2 ──┼──► :8000    │
│   └─ worker N ──► subprocesso MCP N ──┘             │
│         └─ publica eventos ──► Redis ──► BFF ──► SSE│
│                                                     │
│  queue.db (SQLite, WAL)  ◄── runner e BFF leem      │
└─────────────────────────────────────────────────────┘
```

### 7.2 Empacotamento — Docker Compose

```yaml
# docker-compose.yml
services:
  tractian-api:      # API industrial (material fornecido)
    build: ../inteli-tractian-project/api
    ports: ["8000:8000"]

  redis:             # coordenação efêmera — sem volume, por design
    image: redis:7-alpine
    ports: ["6379:6379"]

  backend:           # BFF
    build: ./backend
    ports: ["8100:8100"]
    environment: [GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, REDIS_URL]
    volumes: ["./artifacts:/app/artifacts"]   # queue.db e traces persistem no host
    depends_on: [tractian-api, redis]

  runner:            # execução das rodadas
    build: ./backend
    command: python -m evaluation.runner
    environment: [GEMINI_API_KEY, GROQ_API_KEY, REDIS_URL]
    volumes: ["./artifacts:/app/artifacts"]
    depends_on: [tractian-api, redis]

  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    depends_on: [backend]
```

**Por que Compose.** RNF14 exige que um terceiro execute a solução de ponta a ponta em ambiente
limpo. Com Compose isso é `docker compose up` — sem instalar Python, Node, `uv` ou acertar versões.
A reprodutibilidade deixa de depender do que está instalado na máquina de quem avalia.

**O que fica fora do contêiner.** `artifacts/` é montado do host. A fila e os traces são o **artefato
experimental** — precisam sobreviver a `docker compose down` e ser versionáveis junto com o
repositório.

**O Redis não tem volume — é efêmero de propósito.** Ele carrega apenas coordenação: pub/sub de
eventos, tokens de rate limit e contador de cota. Perdê-lo custa o streaming ao vivo do momento, nunca
dado experimental (RNF17). Detalhamento em [`11-camada-de-analise.md`](./11-camada-de-analise.md) §8.

### 7.3 Por que não um banco em contêiner

Cogitou-se substituir o SQLite por Postgres em contêiner. A conta decide:

| | Valor |
| :--- | ---: |
| Vazão do sistema (limitada pela cota do provedor) | 15 requisições/min |
| Escritas na fila decorrentes | **~0,03 por segundo** |
| Capacidade do SQLite | milhares por segundo |
| Margem | **~10.000×** |

Postgres resolveria um gargalo de concorrência três ordens de grandeza acima do que este sistema
produz. Em troca, custaria um serviço a mais no Compose, e o artefato experimental deixaria de ser um
arquivo que acompanha o repositório.

> **Docker e SQLite não são alternativas.** Docker é empacotamento; SQLite é persistência. A decisão
> correta foi adotar os dois — Compose para o ambiente, SQLite para a fila. Ver ADR-10.

**Reversibilidade.** A fila é acessada por uma interface (`enqueue`, `lease`, `complete`, `fail`).
Trocar o backend não tocaria no runner.

### 7.4 Envelope MCP opcional: um subprocesso por worker

MCP stdio é conexão **1:1** por subprocesso. Duas opções existiam:

| Opção | Prós | Contras |
| :--- | :--- | :--- |
| **Um por worker** ✅ | Correlação ambiente e correta; isolamento de falha; sem estado compartilhado | N processos |
| Compartilhado | Menos processos | Correlação de trace quebra; `run_id` teria que ir como argumento de tool, poluindo schema e sujeito a erro do modelo |

**Se habilitado, escolher um por worker.** O caminho padrão não cria subprocesso: chama o
`ToolProvider` in-process. Esta seção apenas fixa a topologia do envelope opcional.

### 7.5 Ciclo de vida do subprocesso

```
runner inicia worker
   ├─ ToolProvider in-process (padrão)
   ├─ opcional: spawn MCP + handshake initialize
   ├─ catálogo filtrado por tier conforme o papel
   ├─ loop: lease → executar → registrar → liberar
   │    └─ a cada nova task: novo execution_id via notification
   └─ ao encerrar: shutdown gracioso do subprocesso
```

O subprocesso **persiste entre tasks** do mesmo worker — reiniciar a cada task pagaria o handshake
sem necessidade. O `execution_id` é atualizado por notificação.

---

## 8. Contratos do BFF

Necessários **antes** de escrever qualquer código de front ou backend — sem eles, os dois lados são
construídos contra suposições divergentes.

### 8.1 Endpoints

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| `GET` | `/cases` | Lista casos do golden dataset (**apenas campos de entrada** — RNF02) |
| `POST` | `/executions` | Dispara uma execução; devolve `execution_id` |
| `GET` | `/executions/{id}` | Trace completo de uma execução |
| `GET` | `/executions/{id}/stream` | **SSE** — eventos em tempo real |
| `GET` | `/runs` | Lista rodadas com progresso e contagem por classe de falha |
| `GET` | `/runs/{id}/metrics` | Métricas agregadas, com filtros |
| `GET` | `/runs/{id}/tasks` | Estado da fila — paginado |
| `GET` | `/compare?a={id}&b={id}` | Duas execuções lado a lado, com divergências |

> ⚠️ **`GET /cases` nunca expõe `expected_path`, `expected_decision`, `required_evidence`,
> `forbidden_claims` ou `required_preconditions`.** O serializador de resposta usa um modelo
> restrito, e um teste automatizado verifica a ausência desses campos (RNF02).

### 8.2 Schema de eventos SSE

```typescript
type ExecutionEvent =
  | { type: "started";   execution_id: string; case_id: string;
                         architecture: "mono" | "multi"; model: string }
  | { type: "agent_enter"; agent: string; tools_available: string[] }
  | { type: "thinking";  agent: string; step: number; text: string }
  | { type: "tool_call"; agent: string; step: number;
                         call_id: string; tool: string; args: object }
  | { type: "tool_result"; call_id: string; mode: DegradationMode;
                           result: object | null; error: string | null;
                           latency_ms: number }
  | { type: "handoff";   from: string; to: string; payload: object }
  | { type: "precondition_checked"; kind: "baseline" | "data_quality" | "model";
                                    value: string; source_step: number }
  | { type: "resolution"; decision: "orientar" | "agir" | "escalar";
                          justification: string; evidence_cited: EvidenceRef[];
                          unverified: string[] }
  | { type: "finished";  stop_reason: string; duration_ms: number;
                         tokens_in: number; tokens_out: number }
  | { type: "error";     error_class: "infra"|"behavior"|"contract"|"budget";
                         message: string };
```

O evento `precondition_checked` existe para que o front destaque visualmente a verificação de
pré-condições — o comportamento central de H1 — sem precisar reinterpretar o trace.

### 8.3 Reconexão

O cliente envia `Last-Event-ID`; o backend reenvia os eventos posteriores a partir do trace
persistido. Como o trace é append-only (O4), a recuperação é uma leitura sequencial simples.

---

## 9. Armazenamento

### 9.1 Layout

```
artifacts/
├─ queue.db                        # fila + índice de execuções
├─ traces/
│  └─ {run_id}/
│     ├─ {execution_id}.jsonl      # append-only, um evento por linha
│     └─ ...
├─ runs/
│  └─ {run_id}/
│     ├─ config.json               # metadados de reprodutibilidade (RNF15)
│     ├─ metrics.parquet           # métricas por execução
│     └─ report.md
└─ golden/
   ├─ base_cases.json
   └─ generated_cases.json
```

**Divisão de responsabilidade:** SQLite guarda **o que é consultado** (estado, agregados, ponteiros);
JSONL guarda **o que é lido inteiro** (o trace de uma execução). Escrita sequencial rápida e
resistente a corrupção; consulta indexada sem carregar nada em memória.

### 9.2 Agregação

As métricas determinísticas são calculadas **assim que cada execução conclui** e gravadas em
`metrics.parquet`. O dashboard consulta o agregado, nunca os traces crus — que só são lidos quando o
usuário abre uma execução específica.

---

## 10. Sequências dos caminhos difíceis

### 10.1 Ação de impacto com confirmação

```
Executor        MCP           BFF          Front        Usuário
   │             │             │             │             │
   │─getCurrentUser─►          │             │             │
   │◄─ permissions ─│          │             │             │
   │  valida action_high       │             │             │
   │             │             │             │             │
   │─── confirmation_required ─►─── SSE ────►│             │
   │             │             │             │─ exibe ────►│
   │             │             │             │◄─ confirma ─│
   │◄────────── confirmação ───◄─── POST ────│             │
   │             │             │             │             │
   │─updateAssetConfig─►  (justificativa ≥20 chars)        │
   │◄─ ActionResult ─│         │             │             │
   │  registra no trace        │             │             │
```

> Em execução automatizada não há humano. A confirmação é resolvida por **política configurada**
> (auto-confirmar / auto-recusar), registrada nos metadados da rodada — e o evento permanece no
> trace, para que M10 continue mensurável.

### 10.2 Retomada após queda

```
t0   worker A faz lease da task X   (lease_expires = t0 + 300s)
t1   worker A morre
...  task X permanece 'leased', invisível
t0+300  próximo lease executa a recuperação:
        UPDATE ... SET state='pending', attempts=attempts+1
        WHERE state='leased' AND lease_expires < now
t2   worker B faz lease de X → novo execution_id, mesmo task_id
```

Nenhuma intervenção manual. O TTL do lease é o mecanismo de detecção.

### 10.3 Esgotamento de cota diária

```
consumo_hoje aproxima de 1.500
   └─ guarda de cota pausa o lease
      └─ workers concluem as tasks em curso e ficam ociosos
         └─ tasks pendentes permanecem 'pending'
            └─ no dia seguinte: runner reenfileira (INSERT OR IGNORE)
               └─ tasks concluídas colidem e são ignoradas
                  └─ execução prossegue exatamente de onde parou
```

---

## 11. Dimensionamento

### 11.1 Orçamento por experimento

| Experimento | Hipótese | Execuções | Status | Prazo |
| :--- | :--- | ---: | :--- | :--- |
| **E1** — A vs B, 8 seeds × 2 reps | H1 | 544 | núcleo | calcular após piloto A/B |
| **E2** — `prompt_only` vs `pre_action_guard`, arquitetura A, dry-run | H2 | 50 | núcleo | calcular após piloto das duas políticas |
| **Núcleo** | | **594** | obrigatório | precisa caber na janela medida |
| **E3** — overlay + eixo de modelo, amostra | H3 | +130 | condicional | só após o núcleo |
| **E4** — B vs C | H4 | +272 | condicional | só após piloto C |
| **Máximo** | | **996** | com extensões | não é compromisso do núcleo |

### 11.2 Folga

Não há prazo numérico defensável antes do piloto. Se o núcleo não couber, reduzem-se repetições ou
seeds conforme o plano de contingência; E3 e E4 são cortados primeiro.

### 11.3 Sequência recomendada

| Fase | Execuções | Objetivo |
| :--- | ---: | :--- |
| 1. Medição de cota | amostra mínima | Confirmar limites e chamadas por execução em A/B/C |
| 2. Piloto | ~20 | Inspecionar traces à mão; corrigir instrumentação |
| 3. Rotulação cega | — | Rotular amostra **antes** de ver agregados |
| 4. E1 + E2 | 594 | Rodada definitiva do núcleo |
| 5. Julgamento | 594 | Rubrica + meta-avaliação |
| 6. E3 / E4 | +130 / +272 | Condicionais, nessa ordem de custo |

---

## 12. O que não foi construído — e por quê

Registrado explicitamente. Omitir uma decisão de não-construir faz parecer que ela não foi
considerada.

| Não construído | Motivo |
| :--- | :--- |
| **Workers distribuídos em várias máquinas** | A cota é **por conta**, não por máquina. Mais máquinas produzem zero execuções adicionais. A fila com lease suporta workers stateless sem alteração — a arquitetura está pronta, o exercício é que não se justifica |
| **Broker de mensagens (Redis Streams, RabbitMQ) como adaptador da fila** | A porta `WorkQueue` admite qualquer backend. Em escala real de produção — múltiplas máquinas, milhares de tickets/dia — o adaptador seria Redis Streams ou RabbitMQ. Não implementado porque a cota do provedor satura muito antes da capacidade local do SQLite; o piloto registra a diferença real. Trocar o adaptador não toca runner nem agentes |
| **Roteamento entre múltiplos provedores para o agente** | Multiplicaria a vazão, mas exigiria que tasks diferentes rodassem em modelos diferentes — o que contamina E1. O roteamento fica restrito ao eixo H3, onde o modelo **é** a variável |
| **Controlador AIMD como mecanismo primário** | A cota do Gemini é documentada e constante. Token bucket na taxa conhecida basta; AIMD fica como rede de segurança |
| **Sampling do MCP para pré-processar retornos** | Reduziria contexto, mas inserir inferência de LLM dentro da ferramenta contamina a medição do comportamento do agente |
| **Elicitation do MCP como guardrail** | Exigiria humano respondendo — inviável em mais de mil execuções automatizadas. Registrado como evolução |
| **Postgres em contêiner** | A vazão do sistema é ~0,03 escrita/s na fila. SQLite tem ~10.000× de margem. Ver §7.3 e ADR-10 |
| **Redis como fila** | Perderia a durabilidade que o SQLite dá de graça, e o artefato experimental deixaria de ser um arquivo que acompanha o repositório. Redis entra apenas para coordenação efêmera (ADR-11) |

---

## 13. Riscos operacionais

| ID | Risco | Detecção | Resposta |
| :--- | :--- | :--- | :--- |
| **RO-01** | Cota alterada pelo provedor sem aviso | 429 acima do esperado | AIMD recua; guarda de cota pausa; recalibrar |
| **RO-02** | Tool calling instável no modelo escolhido | Taxa de `contract` alta no piloto | Trocar de modelo na fase 1 — antes da rodada definitiva |
| **RO-03** | Falhas de infra não aleatórias (casos longos falham mais) | `infra` correlacionada com número de passos | Se `infra` > 10%, repetir a rodada |
| **RO-04** | Lease TTL curto demais causa execução duplicada | Duas execuções concluídas para a mesma task | TTL > p99 da duração; unicidade em `(task_id, attempt)` |
| **RO-05** | Vazamento de gabarito pela API do BFF | Teste automatizado de serialização | Falha de build (RNF02) |
| **RO-06** | Crescimento de contexto acima do previsto | `tokens_in` acima do orçado | Reduzir passos; reavaliar dimensionamento |
| **RO-07** | Redis indisponível durante a rodada | Falha de conexão no publish | Streaming degrada; execução e persistência continuam (RNF17) |
| **RO-08** | Runner e BFF consomem a mesma cota sem coordenação | Cota estourada antes do previsto | Token bucket e contador diário em Redis, não em memória |

---

## 14. Requisitos introduzidos ou alterados por este documento

| Requisito | Mudança |
| :--- | :--- |
| **RF16** | Limite de passos corrigido de 12 para **8** — decisão de orçamento, §2.1 |
| **RF33** *(novo)* | Homogeneidade de modelo entre papéis quando arquitetura varia em E1 — §3.3 |
| **RNF16** *(novo)* | Guarda de cota diária com retomada automática — §3.4 |
| **RNF14** | Atendido por Docker Compose — §7.2, ADR-10 |
| **RNF17** *(novo)* | Coordenação efêmera sem perda de estado durável — ADR-11 e `11-camada-de-analise.md` §8 |
| **L11** *(nova limitação)* | Diferença de tamanho de catálogo entre arquiteturas como confundidor de H1 — §2.1 |
| **H4** | Mantida como hipótese **condicional** (braço C, E4). RF33 admite heterogeneidade somente quando a arquitetura é constante — §3.3 |
