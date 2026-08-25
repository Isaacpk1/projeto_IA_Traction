# 11 — Camada de Análise

> O [`09-system-design.md`](./09-system-design.md) desenhou o caminho **chamado → agente → API →
> trace**. Ele para no trace. Este documento desenha o que vem depois: **trace → métrica → veredito
> → estatística → visualização**.
>
> É a metade do sistema que produz o resultado do projeto. Sem ela, existem mil traces e nenhuma
> conclusão.

---

## 1. Princípios

| # | Princípio | Consequência |
| :-- | :--- | :--- |
| **A1** | **Métrica é função pura** de `(trace, caso do gabarito, versão)` | Recomputável a qualquer momento, sem reexecutar o agente |
| **A2** | **Scoring e julgamento são pipelines separados** | Um é local e barato; o outro consome cota e é não-determinístico |
| **A3** | **Tudo é versionado** — métrica, rubrica, modelo juiz | Corrigir um bug em M8 não invalida silenciosamente resultados antigos |
| **A4** | **"Não aplicável" nunca é zero** | Colapsar os dois cria vantagem artificial na agregação |
| **A5** | **A estatística é declarada antes**, não escolhida depois | Ver §6 e a proteção contra comparações múltiplas |

> **A1 é o princípio mais consequente.** Durante o desenvolvimento, definições de métrica mudam — M5
> já mudou uma vez. Se o cálculo dependesse de estado externo ou de reexecução, cada correção
> custaria dias de cota. Sendo função pura sobre traces persistidos, custa segundos.

---

## 2. O pipeline

```
   ┌──────────────┐
   │  EXECUÇÃO    │  agente roda, produz trace JSONL
   └──────┬───────┘
          │ ao concluir
   ┌──────▼───────────────────────────────────────┐
   │  ① SCORING            local · determinístico │
   │  métricas M1–M15 sobre (trace, gabarito)     │
   │  ~50 ms por execução · sem cota              │
   └──────┬───────────────────────────────────────┘
          │
   ┌──────▼───────────────────────────────────────┐
   │  ② JULGAMENTO         remoto · consome cota  │
   │  rubrica binária C1–C8 via LLM juiz          │
   │  1 chamada por execução · cache por versão   │
   └──────┬───────────────────────────────────────┘
          │
   ┌──────▼───────────────────────────────────────┐
   │  ③ AGREGAÇÃO          local · determinístico │
   │  métricas por braço, seed, caso, modalidade  │
   └──────┬───────────────────────────────────────┘
          │
   ┌──────▼───────────────────────────────────────┐
   │  ④ TESTE DE HIPÓTESE  local · declarado      │
   │  dose-resposta · testes pareados · IC        │
   └──────┬───────────────────────────────────────┘
          │
   ┌──────▼───────────────────────────────────────┐
   │  ⑤ SERVIÇO            BFF → front            │
   └──────────────────────────────────────────────┘
```

**Cadências diferentes, de propósito:**

| Estágio | Quando roda | Custo | Reexecutável |
| :--- | :--- | :--- | :--- |
| ① Scoring | ao concluir cada execução | ~50 ms | Sim, livre |
| ② Julgamento | em lote, cadência própria | 1 chamada de cota | Sim, mas **custa cota** — daí o cache |
| ③ Agregação | sob demanda | ~1 s sobre mil execuções | Sim, livre |
| ④ Teste | ao final da rodada | segundos | Sim, livre |

O julgamento é o único estágio caro. Todo o resto pode ser refeito quantas vezes for preciso — o que
é exatamente o que se quer quando uma definição de métrica precisa mudar.

---

## 2.5 A fronteira entre execução e análise

### O princípio: o trace é o contrato

A camada de análise **nunca conversa com o agente**. Ela conversa com **artefatos persistidos**.

```
      EXECUÇÃO          │   FRONTEIRA   │        ANÁLISE
                        │               │
  runner → workers      │  trace.jsonl  │  scoring · judging
  MCP · API · LLM       │  (versionado) │  agregação · estatística
                        │               │
   escreve ─────────────►               ◄───────────── lê
```

**Consequências dessa escolha:**

- A análise roda **dias depois**, em outra máquina, a partir do repositório — sem a API no ar, sem
  cota, sem o agente existir
- Corrigir uma métrica **não exige reexecutar nada** (princípio A1)
- Quem for avaliar o projeto pode reproduzir os resultados sem gastar um único token
- A análise depende do **schema do trace**, não do runner. Trocar a implementação do agente não
  quebra a análise, desde que o schema seja respeitado

> O `ExecutionTrace` carrega `schema_version`. Traces antigos continuam legíveis quando o schema
> evolui — o que importa porque a rodada piloto e a definitiva podem usar versões diferentes.

### Os quatro canais

| # | De → Para | Mecanismo | Por quê |
| :-- | :--- | :--- | :--- |
| **1** | Runner → Scoring | **Chamada in-process** | ~50 ms, função pura, sem I/O. Fila seria overhead puro |
| **2** | Scoring → Julgamento | **Fila derivada por consulta** | Cadência e cota diferentes; ver abaixo |
| **3** | Análise → BFF | **Consulta SQLite** | Histórico é leitura indexada, não streaming |
| **4** | Runner → BFF | **Redis pub/sub** | Eventos ao vivo, ≤1 s (RNF08) |

**Os canais 3 e 4 são caminhos separados de propósito:** o front busca **histórico** por consulta e
**ao vivo** por streaming. Misturar os dois — por exemplo, servir histórico via pub/sub — criaria
dependência do Redis para ver resultados de rodadas antigas, violando RNF17.

### Sequência ao concluir uma execução

A ordem importa, e é ordem de *write-ahead*:

```
1. worker encerra o loop ReAct
2. ► persiste trace.jsonl  (fsync)          ← ponto de não-retorno
3. ► marca task 'done' no SQLite (transação)
4. ► score(trace, golden, versão) → grava em metrics
5. ► publica evento 'finished' no Redis
6. worker libera o lease e pega a próxima task
```

**Por que persistir o trace antes de marcar `done`.** Se a ordem fosse invertida e o processo caísse
entre os dois passos, a task ficaria concluída sem trace — perda silenciosa de dado experimental.
Na ordem correta, uma queda entre 2 e 3 deixa a task em `leased`, o lease expira, e ela é reexecutada.
Custa uma execução repetida; nunca custa um trace perdido.

**Falha no passo 4 não invalida a execução.** Scoring quebrado é bug de análise, não falha do agente
— a task permanece `done`, o trace está íntegro, e as métricas são recomputadas depois com um
comando. Reverter a execução por causa disso desperdiçaria cota irrecuperável.

**Falha no passo 5 é ignorada.** Se o Redis estiver fora, o evento se perde e o streaming ao vivo
falha — mas nada de durável é afetado (RNF17).

### A fila de julgamento é derivada, não armazenada

Não existe tabela de "julgamentos pendentes". O que falta julgar é o resultado de uma consulta:

```sql
SELECT e.execution_id
  FROM executions e
  LEFT JOIN judgments j
    ON  j.execution_id   = e.execution_id
    AND j.rubric_version = :rubrica
    AND j.judge_model    = :juiz
 WHERE j.execution_id IS NULL
   AND e.error_class IS NULL          -- não julga execução com falha de infra
 LIMIT :lote;
```

**Isso se auto-corrige.** Mudar a `rubric_version` faz **todas** as execuções voltarem a aparecer como
pendentes, automaticamente — sem migração, sem marcar nada. É exatamente o comportamento desejado
quando a rubrica é corrigida, e é o que torna o experimento E-V2 (binária vs Likert) uma questão de
rodar o worker com outro parâmetro.

### Interface do módulo de análise

```python
# src/analysis/api.py — a superfície que o BFF consome (Facade)

def score_execution(execution_id: str, metric_version: str) -> list[MetricResult]: ...
def rescore_run(run_id: str, metric_version: str) -> int: ...
def pending_judgments(rubric_version: str, judge_model: str, limit: int) -> list[str]: ...
def aggregate(run_id: str, group_by: GroupBy, filters: dict) -> DataFrame: ...
def test_hypotheses(run_id: str) -> list[HypothesisVerdict]: ...
```

Nenhuma dessas funções conhece HTTP, Redis ou o agente. São puras sobre o banco e os traces — o que
permite chamá-las de um notebook, de um teste, ou da linha de comando, sem subir o sistema.

---

## 3. Contratos de dados

### 3.1 Métricas

```sql
CREATE TABLE metrics (
  execution_id    TEXT NOT NULL,
  metric_id       TEXT NOT NULL,      -- M1, M4, M5a, M5b, ...
  metric_version  TEXT NOT NULL,      -- semver da definição
  value           REAL,               -- NULL quando não aplicável
  applicable      INTEGER NOT NULL,   -- 0 | 1
  detail          TEXT,               -- JSON: o que sustentou o cálculo
  computed_at     REAL NOT NULL,
  PRIMARY KEY (execution_id, metric_id, metric_version)
);
CREATE INDEX idx_metrics_exec ON metrics(execution_id);
```

**`applicable` é obrigatório** (princípio A4). Casos concretos onde importa:

| Métrica | Não se aplica quando | Se fosse 0 |
| :--- | :--- | :--- |
| **M14** perda no handoff | arquitetura mono — não há handoff | Vantagem artificial para a mono |
| **M5a/M5b** pré-condição | `detection_mode = symptom` — baseline não é pré-requisito | Penalizaria o comportamento correto em TKT-INV-11b |
| **M10** falso agir | caso sem ação solicitada nem indicada | Diluiria a taxa com casos irrelevantes |
| **M7** afirmação vedada | caso que não discute limiar | Idem |

**`detail` guarda a prova.** Para M8 (ancoragem), guarda quais evidências foram encontradas e quais
não. Isso permite auditar um valor sem reabrir o trace, e é o que o front usa para explicar por que
uma execução recebeu determinada nota.

### 3.2 Julgamentos

```sql
CREATE TABLE judgments (
  execution_id    TEXT NOT NULL,
  criterion_id    TEXT NOT NULL,      -- C1..C8
  rubric_version  TEXT NOT NULL,
  judge_model     TEXT NOT NULL,
  verdict         TEXT NOT NULL,      -- true | false | not_applicable
  justification   TEXT NOT NULL,
  tokens          INTEGER,
  judged_at       REAL NOT NULL,
  PRIMARY KEY (execution_id, criterion_id, rubric_version, judge_model)
);
```

**A chave primária é o mecanismo de cache.** Rejulgar a mesma execução com a mesma rubrica e o mesmo
juiz é um `INSERT OR IGNORE` — não gasta cota. Mudar a rubrica ou o juiz gera chave nova e força
novo julgamento, que é o comportamento correto.

> **Efeito colateral feliz:** o experimento **E-V2** (rubrica binária vs escala Likert) fica quase de
> graça com este schema. São duas `rubric_version` sobre as mesmas execuções — nenhuma reexecução do
> agente é necessária. Ver [`10-matriz-de-experimentos.md`](./10-matriz-de-experimentos.md).

### 3.3 Rotulação humana

```sql
CREATE TABLE human_labels (
  execution_id    TEXT NOT NULL,
  criterion_id    TEXT NOT NULL,
  rubric_version  TEXT NOT NULL,
  verdict         TEXT NOT NULL,
  labeled_at      REAL NOT NULL,
  labeled_before_results INTEGER NOT NULL,  -- 1 = rotulação cega
  PRIMARY KEY (execution_id, criterion_id, rubric_version)
);
```

**`labeled_before_results` é um compromisso auditável.** A rotulação da meta-avaliação precisa
acontecer **antes** de ver os agregados, senão o viés de confirmação contamina a própria régua usada
para validar o juiz. O campo torna essa afirmação verificável, não uma promessa no README.

---

## 4. Estágio ① — Scoring

### 4.1 Assinatura

```python
def score(trace: ExecutionTrace,
          golden: GoldenCase,
          version: str) -> list[MetricResult]:
    """Função pura. Mesmos argumentos → mesmo resultado, sempre."""
```

Sem I/O, sem rede, sem estado. É o que torna A1 verdadeiro na prática, e não só na intenção.

### 4.2 Intensidade de degradação — o eixo de H1

A métrica que sustenta a análise dose-resposta não estava definida ainda:

```python
def degradation_intensity(trace) -> float:
    """Proporção de retornos da API que não vieram completos."""
    modos = [s.result.get("mode") for s in trace.steps
             if s.result and "mode" in s.result]
    if not modos:
        return 0.0
    return sum(1 for m in modos if m != "complete") / len(modos)
```

Vai de 0,0 (tudo completo) a 1,0 (nada completo). **É a variável independente contínua de H1** — o
eixo X do gráfico que carrega a hipótese central.

Duas propriedades importantes: é computada **do trace**, não do gabarito (então não vaza informação
privilegiada), e varia por execução mesmo dentro do mesmo seed, porque depende de quais recursos o
agente consultou.

### 4.3 Recomputação

```bash
uv run python -m evaluation.rescore --run-id <id> --metric M8 --version 1.2.0
```

Lê os traces persistidos, recalcula, grava com a nova versão. Os valores antigos permanecem —
`metric_version` está na chave primária. Nada é sobrescrito (princípio O4).

**Consequência prática:** corrigir um bug de métrica no dia 12 do projeto custa segundos, não uma
nova rodada de execuções. Isso é o que torna aceitável descobrir problemas de medição tarde.

---

## 5. Estágio ② — Julgamento

### 5.1 O que vai para o juiz

O juiz recebe **a resolução e o trace resumido** — nunca o gabarito (RNF02 vale aqui também).

```python
class JudgeInput(BaseModel):
    case_message: str
    user_role: str
    resolution: Resolution
    tools_called: list[str]
    api_modes_seen: list[str]         # para avaliar C3 (incerteza honesta)
    evidence_available: list[dict]    # retornos, para checar ancoragem
    # ⛔ expected_path, expected_decision, forbidden_claims: NUNCA
```

### 5.2 Aplicabilidade por critério

Cada critério da rubrica tem um `applies_when` avaliado **programaticamente antes** de chamar o
juiz:

```python
APPLICABILITY = {
  "C1_baseline_declarado":  lambda ctx: ctx.analysis_discussed and ctx.mode == "baseline",
  "C2_sem_norma_generica":  lambda ctx: ctx.threshold_discussed,
  "C3_incerteza_honesta":   lambda ctx: ctx.degradation_intensity > 0,
  "C4_evidencia_ancorada":  lambda ctx: True,
  "C5_acao_justificada":    lambda ctx: ctx.decision == "agir",
  "C6_modo_deteccao":       lambda ctx: ctx.detection_mode_relevant,
  "C7_conflito_explicito":  lambda ctx: "conflict" in ctx.api_modes_seen,
  "C8_adequacao_perfil":    lambda ctx: True,
}
```

**Por que decidir isso em código, e não deixar o juiz decidir.** Se o juiz julgar a aplicabilidade,
ele pode marcar `not_applicable` para se esquivar de um critério difícil — e a taxa de `false` cai
sem que a qualidade tenha subido. Determinar aplicabilidade fora do juiz fecha essa saída.

### 5.3 Cota e lote

O juiz tem cota própria (Groq, 250/dia) e por isso **fila própria**, independente da fila de
execução. Rodam em paralelo: enquanto o agente executa a rodada do dia, o juiz processa as execuções
do dia anterior.

```
dia 1: agente executa 187  │  juiz ocioso
dia 2: agente executa 187  │  juiz julga 187 do dia 1
dia 3: agente executa 187  │  juiz julga 187 do dia 2
...
```

O julgamento fica um dia atrás e nunca é o gargalo, porque 250 > 187.

---

## 6. Estágio ④ — Teste de hipótese

> Tudo nesta seção está declarado **antes** de qualquer execução. Nenhum teste é escolhido depois de
> ver os dados.

### 6.1 H1 — dose-resposta *(teste primário)*

A predição P1.1 não é "a multi é melhor", é **"a vantagem da multi cresce com a degradação"**. Isso é
um termo de interação:

```python
# M4 é binário → regressão logística
modelo = smf.logit(
    "acerto ~ intensidade * C(braco)",
    data=df[df.braco.isin(["A", "B"])]
).fit()

# O coeficiente da interação intensidade:C(braco)[T.B] É o teste de P1.1
```

| Resultado | Interpretação |
| :--- | :--- |
| Interação **> 0**, IC não cruza zero | **P1.1 confirmada** — a vantagem da multi cresce com a degradação |
| Interação ≈ 0 | **P1.1 refutada** — a diferença, se existe, é constante |
| Interação **< 0** | **P1.1 refutada na direção oposta** — a mono se sai relativamente melhor sob degradação |

**Por que isso é mais forte que um contraste binário.** Um contraste mostra que existe diferença.
Dose-resposta mostra que a diferença **acompanha a causa proposta** — que é evidência de mecanismo,
não apenas de associação.

### 6.2 Demais testes

| Hipótese | Teste | Métrica primária |
| :--- | :--- | :--- |
| **H1** | Regressão logística com interação | M4 × intensidade |
| **H2** | McNemar pareado, casos adversariais | M10 |
| **H3** | McNemar pareado | M7 |
| **H4** | **Teste de não-inferioridade**, margem 5 p.p. | M4 |

> **H4 exige teste de não-inferioridade, não teste de diferença.** A predição P4.1 afirma que o braço
> C **não é pior** que B em mais de 5 pontos. Um teste convencional que "não rejeita a diferença" não
> prova equivalência — pode significar apenas falta de poder estatístico. O teste correto verifica se
> o limite inferior do IC da diferença fica acima de −5 p.p.
>
> Confundir os dois é o erro mais comum em comparações de "é tão bom quanto".

### 6.3 Intervalos de confiança

Todos por **bootstrap pareado por caso** — os casos são a unidade de amostragem, não as execuções.
Reamostrar execuções trataria 8 seeds do mesmo caso como 8 observações independentes, o que
subestimaria o erro.

### 6.4 Meta-avaliação

```python
kappa = cohen_kappa_score(vereditos_humanos, vereditos_juiz)
```

Calculado **por critério**. Critérios com κ < 0,60 são reescritos ou excluídos da análise, e a
exclusão é reportada.

---

## 7. Estágio ⑤ — O que o front mostra

Cada view existe para responder **uma** pergunta. Se não responde, não entra.

| View | Pergunta | Fonte |
| :--- | :--- | :--- |
| **Rodada** | A execução está saudável? Quanto falta? | `tasks`, contagem por classe de falha, consumo de cota |
| **Dose-resposta** | **A hipótese central se sustenta?** | `metrics` M4 × intensidade, por braço |
| **Comparação de braços** | Onde A, B e C diferem, métrica a métrica? | `metrics` agregadas |
| **Matriz de casos** | Em quais casos os braços divergiram? | `metrics` por caso × braço |
| **Inspetor de trace** | O que aconteceu nesta execução? | `traces/*.jsonl` |
| **Rubrica** | Como o juiz avaliou, e ele é confiável? | `judgments`, `human_labels`, κ |

**A view de dose-resposta é a central.** É o gráfico que carrega H1 e o que deve abrir a
apresentação. As demais existem para sustentá-lo ou para investigar quando algo destoa.

**Regra de navegação:** toda métrica agregada deve permitir descer até a execução individual, e toda
execução deve permitir subir até o passo do trace que originou cada evidência. Sem isso, um número
estranho no dashboard vira um mistério em vez de uma investigação.

> O desenho visual dos gráficos — tipo de marca, paleta, escalas — não está especificado aqui. Será
> definido na implementação, com as diretrizes de visualização aplicadas no momento da construção.

### 7.1 Endpoints adicionais no BFF

Complementam os já definidos em [`09-system-design.md`](./09-system-design.md) §8.1:

| Método | Rota | Devolve |
| :--- | :--- | :--- |
| `GET` | `/runs/{id}/dose-response` | Pares (intensidade, acerto) por braço, mais coeficientes ajustados |
| `GET` | `/runs/{id}/metrics?group_by=arm\|case\|seed\|mode` | Agregação parametrizada |
| `GET` | `/runs/{id}/hypotheses` | Veredito por hipótese com IC e valor-p |
| `GET` | `/runs/{id}/divergences` | Casos em que os braços discordaram |
| `GET` | `/runs/{id}/judge-agreement` | κ por critério, e critérios excluídos |
| `GET` | `/executions/{id}/metrics` | Métricas de uma execução, com `detail` |

---

## 8. Coordenação efêmera — Redis

### 8.1 O problema que o Compose criou

Ao separar runner e BFF em contêineres distintos, surgiu uma lacuna que o
[`09-system-design.md`](./09-system-design.md) não resolvia:

> **Os eventos de execução acontecem no processo do runner. O SSE é servido pelo processo do BFF.
> Como um chega ao outro?**

Alternativas consideradas:

| Opção | Problema |
| :--- | :--- |
| BFF lê o JSONL do runner (*tail*) | Frágil, latência de polling, não atende RNF08 (≤ 1 s) |
| Runner e BFF no mesmo processo | Contraria a separação do Compose; runner longo travaria a API |
| **Redis pub/sub** | ✅ Resolve diretamente |

E uma segunda lacuna, do mesmo tipo: **a cota é da conta, não do processo.** Se o BFF disparar uma
execução avulsa pela interface enquanto o runner executa a rodada, os dois consomem o mesmo teto
diário. Um contador em memória por processo não coordena isso.

### 8.2 A divisão

```
┌──────────────────────────────────────────────────────┐
│  SQLite — ESTADO DURÁVEL                             │
│  fila · execuções · métricas · julgamentos · rótulos │
│  É o artefato experimental. Versionável. Auditável.  │
│  Perder = perder o projeto.                          │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│  REDIS — COORDENAÇÃO EFÊMERA                         │
│  pub/sub de eventos · tokens de rate limit           │
│  contador de cota diária · cache de agregados        │
│  Perder = reiniciar e seguir. Nenhum dado científico.│
└──────────────────────────────────────────────────────┘
```

**O critério é simples: se perder aquilo dói no resultado do experimento, é SQLite. Se só atrapalha a
operação do momento, é Redis.**

### 8.3 Os três usos

**① Pub/sub para SSE**

```python
# runner
await redis.publish(f"exec:{execution_id}", event.model_dump_json())

# BFF
async for msg in pubsub.listen():
    yield f"data: {msg['data']}\n\n"
```

Atende RNF08 sem polling. Se o Redis cair, o streaming ao vivo para — mas o trace continua sendo
gravado, e o inspetor funciona normalmente depois. **Degradação graciosa, sem perda de dado.**

**② Rate limit distribuído**

```lua
-- token bucket atômico, compartilhado entre processos
local tokens = redis.call('GET', KEYS[1]) or ARGV[1]
if tonumber(tokens) > 0 then
  redis.call('DECR', KEYS[1])
  return 1
end
return 0
```

Substitui o `asyncio.Lock` in-process do doc 09 §3.4 quando há mais de um processo consumindo a mesma
cota. Com um único runner, os dois funcionam; com runner + BFF, só o distribuído está correto.

**③ Contador de cota diária**

```python
consumo = await redis.incr(f"quota:{provedor}:{data}")
await redis.expireat(chave, fim_do_dia_utc)
```

`INCR` é atômico. A guarda de cota (RNF16) passa a valer para todos os processos, não só para o
runner.

### 8.4 Por que Redis aqui e não para a fila

| | Fila (durável) | Coordenação (efêmera) |
| :--- | :--- | :--- |
| Perder o dado significa | perder o experimento | reiniciar o serviço |
| Precisa acompanhar o repositório | **sim** — é o artefato | não |
| Precisa ser inspecionável meses depois | **sim** | não |
| Precisa de pub/sub e atomicidade distribuída | não | **sim** |
| **Escolha** | **SQLite** | **Redis** |

Redis como fila exigiria Streams com configuração cuidadosa de persistência para se aproximar da
durabilidade que o SQLite dá de graça — e ainda assim o resultado não seria um arquivo que acompanha
o repositório.

> **Você estava certo:** com Docker, o Redis passa a custar uma entrada no Compose. E há dois
> problemas reais que ele resolve e que nenhuma outra opção resolvia bem. O que ele **não** faz é
> substituir o SQLite — são camadas com requisitos opostos.

---

## 9. Topologia revisada

```
┌───────────────────────────────────────────────────────────┐
│  docker compose                                           │
│                                                           │
│  ┌───────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ tractian-api  │  │   frontend   │  │     redis      │  │
│  │ :8000         │  │   :5173      │  │     :6379      │  │
│  └───────▲───────┘  └──────┬───────┘  └───▲────────▲───┘  │
│          │                 │ REST+SSE     │ pub/sub │      │
│          │          ┌──────▼───────┐      │         │      │
│          │          │   backend    │──────┘         │      │
│          │          │   :8100      │                │      │
│          │          └──────┬───────┘                │      │
│          │                 │ lê                     │      │
│          │          ┌──────▼───────────────┐        │      │
│          └──────────│  runner              │────────┘      │
│           HTTP      │  workers + MCP subp. │  publica      │
│                     └──────┬───────────────┘               │
│                            │                               │
│              ┌─────────────▼──────────────┐                │
│              │  ./artifacts  (bind mount) │                │
│              │  queue.db · traces/ · runs/│                │
│              └────────────────────────────┘                │
└───────────────────────────────────────────────────────────┘
```

`artifacts/` é montado do host — sobrevive a `docker compose down` e acompanha o repositório. O Redis
não tem volume: é efêmero por design.

---

## 10. Riscos da camada de análise

| ID | Risco | Detecção | Resposta |
| :--- | :--- | :--- | :--- |
| **RA-01** | Definição de métrica muda no meio da rodada | `metric_version` divergente entre execuções | Recomputar tudo na versão nova; ambas ficam registradas |
| **RA-02** | Juiz marca `not_applicable` em excesso, inflando a nota | Taxa de `not_applicable` acima do previsto pela regra programática | Aplicabilidade é decidida em código, não pelo juiz (§5.2) |
| **RA-03** | κ baixo em critério central da rubrica | Meta-avaliação | Reescrever o critério ou excluí-lo, reportando |
| **RA-04** | Bootstrap por execução em vez de por caso subestima o erro | Revisão do código de análise | Unidade de reamostragem é o caso (§6.3) |
| **RA-05** | Métricas `N/A` tratadas como zero na agregação | Teste com execuções mono, onde M14 é indefinida | Coluna `applicable`; agregação filtra antes de somar |
| **RA-06** | Teste de diferença usado onde cabia não-inferioridade (H4) | Revisão do plano estatístico | Declarado em §6.2 antes da execução |
| **RA-07** | Redis indisponível durante a rodada | Falha de conexão | Streaming degrada; execução e persistência continuam |

---

## 11. Requisitos introduzidos

| Requisito | Descrição |
| :--- | :--- |
| **RF34** *(novo)* | Métricas versionadas e recomputáveis sobre traces persistidos, sem reexecutar o agente |
| **RF35** *(novo)* | Aplicabilidade de métrica e de critério registrada explicitamente, distinta de valor zero |
| **RF36** *(novo)* | Julgamentos em cache por `(execução, rubrica, juiz)`, evitando gasto redundante de cota |
| **RNF17** *(novo)* | Coordenação entre processos (eventos, rate limit, cota) sem perda de estado durável em caso de falha da camada efêmera |
