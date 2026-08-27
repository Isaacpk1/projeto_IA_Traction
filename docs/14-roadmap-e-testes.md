# 14 — Roadmap e Estratégia de Testes

> Duas coisas que não são opinião: o calendário e o fato de que a execução do experimento **não
> comprime**. Todo o resto se organiza em torno disso.

---

## 1. A restrição que governa o cronograma

```
24/08 seg   25/08 ter   26/08 qua   27/08 qui   28/08 sex   29/08 SÁB   30/08 DOM
31/08 seg   01/09 ter   02/09 qua   03/09 qui   04/09 sex   05/09 SÁB   06/09 DOM
07/09 seg   08/09 ter ◄── ENTREGA E APRESENTAÇÃO
```

**15 dias corridos.** E dentro deles:

| Fato | Consequência |
| :--- | :--- |
| A vazão depende das chamadas por execução de cada braço | O piloto precisa ocorrer antes de prometer uma data de término |
| O núcleo possui 594 execuções; o máximo condicional, 996 | E3 e E4 só entram se a medição preservar tempo de análise |
| A análise precisa dos resultados | Só começa quando o experimento acaba |

**Portanto:**

> ### 🚦 Tudo que o experimento precisa para rodar tem que estar pronto até **31/08**.

São **7 dias** para construir: contratos, camada de ferramentas, agente mono, agente multi, fila,
runner, guardrail, golden dataset e métricas.

O que vem depois — ingestão de tickets, console, BFF, front, juiz, estatística — é construído
**enquanto o experimento roda em segundo plano**. Essa é a única forma de caber.

### 1.1 Estado verificado em 27/08/2026

- **Concluído:** contratos e portas do núcleo, fakes, factories, regras do `import-linter`, parser
  OpenAPI, overlay, factory, executor HTTP, catálogo por `tier`, dry-run e papéis declarativos.
- **Fase 1 concluída:** as 18 tools são geradas do contrato real; cobertura do overlay, composição
  por autoridade, transporte e portabilidade do núcleo têm testes automatizados.
- **Pendências da Fase 0:** medição real de cota e Langfuse. O loop próprio foi adotado e o sink
  JSONL canônico, com composição best-effort, já está implementado; falta o sink secundário do
  Langfuse. Essas pendências impedem marcar o DoD integral da Fase 0 como concluído.
- **Fase 2 local concluída:** faltam a validação com Gemini/API local e a navegação do mesmo trace no
  Langfuse; nenhuma credencial ou serviço correspondente está disponível neste ambiente.
- **Fase 3 local concluída:** fila SQLite, lease com dono e TTL, worker único, rate limiter conectado
  ao Gemini, isolamento RNF02 e guards pré-ação/pré-entrega têm testes determinísticos.
- **Ainda inexistente:** golden formalizado, métricas, arquitetura multi, BFF, frontend e Compose.
  Comandos ponta a ponta permanecem explicitamente marcados como planejados no README.

---

## 2. As duas trilhas

```
        ├──────── CONSTRUÇÃO DO NÚCLEO ────────┤
24/08 ──┤ contratos · tools · agente · fila     ├── 31/08  🚦 GO/NO-GO
        │ guardrail · métricas · golden dataset │
        └───────────────────────────────────────┘
                                                 │
01/09 ──┬─ TRILHA A (fundo) ── experimento executando ──────────┬── 06/09
        │                       núcleo 594 · máximo 996         │
        │                                                        │
        └─ TRILHA B (frente) ── ingestão · console · BFF ────────┘
                                front · juiz · estatística

07/09 ── análise dos resultados · README · apresentação
08/09 ── ENTREGA
```

**A trilha A não exige atenção.** O runner é CLI, roda sozinho, retoma se cair, pausa na cota e
prossegue. Você olha o progresso pelo Langfuse uma vez por dia.

---

## 3. Como você enxerga o sistema durante a construção

Esta seção existe porque durante 10 dos 15 dias **não há front**. E depurar um agente de raciocínio
com `print` é o caminho mais rápido para perder três dias.

### 3.1 A escada de visibilidade

| Fase | Instrumento | Custo de construção | O que responde |
| :--- | :--- | :--- | :--- |
| 0 → sempre | **Langfuse** (container + `TraceSink`) | ~2 h, **uma vez** | "por que o agente decidiu isso?" — passo a passo, latência, tokens, custo |
| 0 → sempre | **JSONL em disco** | zero (já é RF) | fonte de verdade; nada depende de serviço externo |
| 3 → sempre | `pytest -v` sobre traces sintéticos | zero | "a lógica está certa?" |
| 03/09 → | **Front React** | 2 dias | "o produto funciona e é demonstrável?" |

> **A decisão importante:** o Langfuse entra na **Fase 0**, não quando der. Ele é a diferença entre
> calibrar prompt olhando um trace renderizado e calibrar prompt lendo JSON no terminal. Custa duas
> horas uma única vez e serve os 15 dias inteiros.

### 3.2 Por que Langfuse e não só CLI

O visualizador de CLI com `rich` (~50 linhas) foi a decisão anterior. Ele foi **substituído**, não
somado — construir os dois é desperdício. O Langfuse entrega, de graça, tudo que a CLI daria e mais:

| Precisa | CLI `rich` | Langfuse |
| :--- | :---: | :---: |
| Ver um trace passo a passo | ✅ | ✅ |
| Comparar duas execuções lado a lado | ❌ | ✅ |
| Filtrar por caso / braço / seed | ❌ | ✅ |
| Custo e tokens por passo | ❌ | ✅ |
| Ver o histórico enquanto o experimento roda | ❌ | ✅ |
| Anexar score do juiz ao trace | ❌ | ✅ |
| Funciona sem container | ✅ | ❌ |

O último ponto é o que justifica a arquitetura do `CompositeTraceSink` (doc [`11`](./11-camada-de-analise.md) §2.5):
o JSONL é obrigatório e a falha propaga; o Langfuse é opcional e a falha é engolida. **Se o Langfuse
cair no meio do experimento, nada se perde.**

### 3.3 O que o front básico é — e o que ele não é

Você pediu um front "bem básico, para ver tudo melhor do que um print". A definição precisa:

**Três telas, nada além:**

| Tela | Quando | O que mostra | Por que é essencial |
| :--- | :--- | :--- | :--- |
| **Console de atendimento** | 03/09 | fila de tickets, status, resolução entregue, veredito do guardrail | É a **demonstração de produto** — a coisa que prova que não é script de experimento |
| **Chat multi-turno** | 03/09 | conversa com o agente sobre um ticket, com streaming | Prova RF37–RF43 ao vivo na apresentação |
| **Dashboard de hipóteses** | 04/09 | M1–M16 por braço, curva dose-resposta, veredito de H1–H4 | É onde o resultado do experimento aparece |

**O que o front NÃO faz — e isso é decisão, não falta de tempo:**

- ❌ **Não reimplementa inspeção profunda de trace.** Cada execução no console tem um **link para o
  Langfuse**. Reconstruir renderização de span, timeline e diff seria 1,5 dia para ficar pior.
- ❌ **Não tem autenticação, papéis ou multi-tenancy.** Extras, §8.
- ❌ **Não tem edição de golden case pela UI.** JSON versionado é melhor para um dataset que precisa
  ser reprodutível.

> **A regra:** o front mostra **o que o produto faz** e **o que o experimento concluiu**. O Langfuse
> mostra **por que o agente decidiu**. Não se sobrepõem.

---

## 4. Fases

### Fase 0 — Fundação · **24–25/08** (2 dias)

| Entrega | Detalhe |
| :--- | :--- |
| `pyproject.toml` + estrutura de pastas | conforme [`13`](./13-padroes-e-estrutura.md) |
| `core/contracts/` | `ExecutionTrace`, `Resolution`, `Delivered`, `EvidenceRef`, `InvestigationReport`, `GoldenCase`, `MetricResult`, `Task` |
| `core/ports/` | `LLMClient`, `ToolProvider`, `WorkQueue`, `TraceSink` |
| **`tests/fakes/`** | **`FakeLLMClient`, `FakeToolProvider`, `InMemoryQueue`** |
| **`tests/factories/`** | **polyfactory sobre `ExecutionTrace`, `Resolution`, `GoldenCase`** |
| **Langfuse subindo no Compose** | `langfuse` + `langfuse-db`; `JsonlTraceSink` + `LangfuseTraceSink` + `CompositeTraceSink` (ADR-14) |
| Contratos do `import-linter` | em `pyproject.toml` — substitui o checker de AST |
| **Spike `pydantic-ai` — 2h, timeboxed** | uma tool, um loop com `TestModel`, verificar se o histórico permite montar o trace |
| `tests/test_architecture.py` | regra de dependência |
| Script de medição de cota | mede RPM, RPD e p95 de chamadas por execução em A/B/C |
| Decisão do spike | adotar `pydantic-ai` ou loop próprio — **decidir no dia 1, não depois** |

> **Os fakes vêm primeiro, antes de qualquer implementação real.** Sem `FakeLLMClient`, não existe
> TDD do agente — só teste de integração caro e não-determinístico. Ver §6.

> **Timebox do Langfuse: 2 h.** Se o self-host não subir nesse tempo, use o cloud free tier
> (50k observações/mês, folgado para até 996 execuções) e siga. Se nem isso, `JsonlTraceSink` sozinho
> já satisfaz todos os RFs — o Langfuse é conforto, não requisito (RC-08).

**DoD:** `pytest` verde · regra de dependência falhando quando violada de propósito · cota medida ·
**um trace de mentira aparecendo na UI do Langfuse**.

---

### Fase 1 — Camada de ferramentas · **26/08** (1 dia)

`openapi_parser` · `overlay` merge · `tool_factory` · `http_executor` · `tier_registry`

**DoD:** 18 tools geradas do contrato real, com descrição enriquecida e `tier` correto · varredura de
domínio em `tools/core/` passa (RNF06) · teste de composição por `tier` passa (RF12).

---

### Fase 2 — Agente mono · **27/08** (1 dia)

**Status em 26/08/2026:** loop ReAct, prompt base, `submit_resolution`, arquitetura mono, adaptador
Gemini e JSONL canônico implementados. Caso determinístico e persistência estão validados por teste.
Permanecem pendentes os dois itens externos do DoD: Gemini contra a API local e trace no Langfuse.

`react.py` · `tracer.py` · `submit_resolution` · **prompt base (`prompts/base.md`)** · adaptador
Gemini

> **A calibração acontece aqui, e acontece olhando UM trace no Langfuse** — não uma média. Ver que o
> agente chamou `getBaseline`, recebeu `invalidated` e ignorou é o que ajusta prompt e rubrica.
> Dashboard com 20 execuções é ruído. Por isso o Langfuse é Fase 0 e não Fase 6.

**DoD:** um caso completo com `FakeLLMClient` (determinístico, em milissegundos) · **depois** o mesmo
caso contra Gemini real e API local · trace válido gravado em JSONL · **o mesmo trace navegável no
Langfuse**.

---

### Fase 3 — Fila, runner e guardrail · **28/08** (1 dia)

**Status em 27/08/2026:** implementação local concluída. O teste executa 20 tarefas, interrompe após
7, reabre o SQLite e conclui as 13 restantes sem reprocessar; isolamento e guards também estão
cobertos. A execução dos 20 casos contra Gemini/API real permanece bloqueada pelo ambiente externo.

`queue_sqlite.py` · `worker.py` · `rate_limiter.py` · `isolation_guard.py` ·
**`pre_action_guard.py` (RF13–RF15)** · **`pre_delivery_guard.py` (RF44)**

> O `PreActionGuard` bloqueia efeitos externos sem permissão, confirmação ou evidência válida. O
> `PreDeliveryGuard` aplica V1/V2/V3 e separa `Resolution` de `Delivered`. O juiz LLM fica fora dos
> dois caminhos: ele mede depois. Ver ADR-13.

**DoD:** 20 casos executam · interromper com `Ctrl-C` e reexecutar retoma sem reprocessar · guarda de
isolamento aborta quando o gabarito é exposto de propósito (RNF02) · **ação sem pré-condição não
chega à API** · resolução com evidência forjada não é entregue.

---

### Fase 4 — Golden dataset e métricas · **29–30/08** (fim de semana, 2 dias)

`base_cases.json` formalizado dos 17 · `adversarial_cases.json` (A1–A5) · scorers M1–M16

**DoD:** cada métrica com teste sobre trace sintético · métricas calculadas sobre as execuções da
Fase 3 · `applicable` correto (M14 em mono retorna `applicable=0`, não zero — RF35).

---

### Fase 5 — Multi-agente · **31/08** (1 dia)

Orquestrador · 3 papéis · handoff tipado · grafo LangGraph · composição por `tier`

**DoD:** braço B executa um caso · handoff registrado no trace · **teste de RF12 confirma que o
Investigador não possui tool de `tier: impact`**.

---

## 🚦 5. GO / NO-GO — 31 de agosto

Checklist objetivo. Se algum item falhar, **corte pela lista da §9** — não empurre o prazo.

- [ ] Um caso executa de ponta a ponta nos braços A e B
- [x] Fila retoma após interrupção
- [x] Guarda de isolamento bloqueia (RNF02)
- [x] `PreActionGuard` bloqueia ação sem RF13–RF15 antes da API
- [x] `PreDeliveryGuard` (RF44) bloqueia resolução com evidência forjada
- [ ] Métricas calculam sobre traces reais
- [ ] Golden dataset com `forbidden_claims` e `required_preconditions`
- [ ] Cota real medida e vazão confirmada
- [ ] Rotulação humana cega de **40 casos** feita (10 calibração + 30 validação, sem sobreposição)

> **Duas condições sobre a rotulação, ambas obrigatórias.** Precisa acontecer **antes** de ver
> qualquer resultado agregado — senão a meta-avaliação fica contaminada por viés de confirmação. E os
> 40 precisam ser **divididos** em 10 de calibração e 30 de validação, sem sobreposição — senão o
> kappa mede a memória do juiz, não o julgamento dele.

> **O Langfuse não está no checklist.** Ele é conforto de desenvolvimento, não pré-condição de
> experimento. Se não subiu, o JSONL cobre tudo que os RFs exigem.

---

### Fase 6 — Experimento + produto · **01–06/09**

**Trilha A — fundo, sem atenção:**

| Marco | Critério |
| :--- | :--- |
| Piloto | p95 de chamadas por execução e cotas efetivas registrados por braço |
| Núcleo | E1 + E2 = **594 execuções** concluídas primeiro |
| Extensões | E3 (+130) e E4 (+272) habilitadas somente se couberem integralmente |
| Máximo | **996 execuções**, sem consumir o dia reservado à análise |

Julgamento roda em paralelo na vazão confirmada pelo piloto. **Score do juiz é anexado ao trace no Langfuse**
(`langfuse.score()`), o que permite filtrar "todas as execuções que o juiz reprovou" e abrir o
raciocínio de cada uma — isso é calibração de rubrica praticamente de graça.

**Trilha B — construção:**

| Dias | Entrega |
| :--- | :--- |
| 01–02/09 | Ingestão (`POST /tickets`), prioridade, sessão multi-turno (RF37–RF43) |
| 03/09 | BFF + front: **console de atendimento** e **chat com streaming** |
| 04/09 | Front: **dashboard de hipóteses** (M1–M16, dose-resposta) + link por execução para o Langfuse |
| 05–06/09 | Juiz (DeepEval `GEval`, `strict_mode=True`) + rubrica + meta-avaliação (kappa) + camada estatística |

---

### Fase 7 — Fechamento · **07/09** (1 dia)

Análise dos resultados · teste das 12 predições · dashboard com dados reais · README com Resultados
e Limitações · apresentação.

**DoD:** veredito escrito para H1 e H2; para H3 e H4, veredito se executadas ou registro explícito
da não-execução — incluindo resultados **inconclusivos**.

---

## 6. Estratégia de TDD

### 6.1 Por que os fakes vêm primeiro

TDD exige que o teste rode **rápido e determinístico**. Um agente que chama LLM não é nenhum dos
dois. A solução não é abrir mão do TDD — é injetar um duplo:

```python
# tests/fakes/llm.py
class FakeLLMClient:
    """Devolve uma sequência roteirizada. Determinístico, instantâneo, sem cota."""
    def __init__(self, roteiro: list[LLMResponse]):
        self.roteiro, self.chamadas = list(roteiro), []

    async def chat(self, messages, tools, **kw) -> LLMResponse:
        self.chamadas.append((messages, tools))
        return self.roteiro.pop(0)
```

Com isso, o loop ReAct inteiro é testável:

```python
async def test_agente_verifica_baseline_antes_de_concluir():
    llm = FakeLLMClient([
        resposta_com_tool_call("getAnalysis", {"analysisId": "an_9903"}),
        resposta_com_tool_call("getBaseline", {"assetId": "asset_S420"}),
        resposta_com_tool_call("submit_resolution", {"decision": "escalar", ...}),
    ])
    tools = FakeToolProvider({
        "getAnalysis": {"type": "imbalance", "baseline_state_at_detection": "invalidated"},
        "getBaseline": {"state": "invalidated"},
    })

    trace = await run_agent(caso_tkt_inv_06, llm, tools)

    assert indice(trace, "getBaseline") < indice_da_conclusao(trace)   # M5a
    assert trace.resolution.decision == "escalar"
```

**Isto é o hexagonal se pagando.** As portas `LLMClient` e `ToolProvider` existem exatamente para
que os duplos entrem no lugar dos reais.

### 6.2 O que se testa como

| Componente | Determinístico? | Abordagem | TDD real? |
| :--- | :---: | :--- | :---: |
| Scorers (M1–M16) | ✅ | função pura sobre trace sintético | ✅ **ideal** |
| **Guards pré-ação/pré-entrega** | ✅ | tentativa sem pré-condição + trace com evidência forjada | ✅ **ideal** |
| Fila (lease, prioridade, idempotência) | ✅ | SQLite em memória | ✅ **ideal** |
| `openapi_parser` + overlay | ✅ | contrato real como fixture | ✅ **ideal** |
| Prioritizer | ✅ | criticidade → prioridade | ✅ **ideal** |
| Sessão multi-turno (RF43) | ✅ | persistir e restaurar | ✅ **ideal** |
| Invariantes (RNF02, RNF05, RF33, RF12) | ✅ | asserção estrutural | ✅ **ideal** |
| `CompositeTraceSink` | ✅ | sink secundário lançando exceção | ✅ **ideal** |
| Loop ReAct | ⚠️ | `FakeLLMClient` roteirizado | ✅ **sim, com duplo** |
| Handoff tipado | ⚠️ | fake + validação Pydantic | ✅ **sim, com duplo** |
| `http_executor` | ⚠️ | transporte mock do httpx | ✅ **sim, com duplo** |
| Comportamento do agente com LLM real | ❌ | **é o experimento, não teste** | ❌ |
| Qualidade da resolução | ❌ | rubrica + juiz | ❌ |

> **A linha divisória.** Testes verificam que o **sistema funciona**. O experimento mede se o
> **agente raciocina bem**. Confundir os dois leva a testes frágeis que quebram porque o modelo
> respondeu diferente — e isso não é bug.

**Um teste que vale destacar** — o que garante que o Langfuse nunca derruba o experimento:

```python
def test_falha_do_langfuse_nao_perde_trace():
    jsonl, langfuse = JsonlTraceSink(tmp), SinkQueSempreFalha()
    sink = CompositeTraceSink(jsonl=jsonl, langfuse=langfuse)

    sink.record(passo)          # não levanta

    assert jsonl.ler() == [passo]
```

### 6.3 A pirâmide

```
         ╱ E2E ╲              2–3 testes · LLM real · CONSOME COTA
       ╱ integração ╲         ~20 · fakes + API local
     ╱     unidade     ╲      ~150 · puro, milissegundos
   ╱   invariantes      ╲     ~9 · bloqueiam o build
```

**Os testes de invariante são os mais importantes do projeto**, e não estão no topo por acaso — eles
não medem comportamento, eles **impedem** que o projeto se invalide:

| Teste | Bloqueia |
| :--- | :--- |
| Isolamento do gabarito | RNF02 — vazamento invalida **todos** os resultados |
| Composição por `tier` | RF12 / RNF05 — Investigador sem tool de impacto |
| `PreActionGuard` obrigatório em provider real | RF13–RF15 — nenhuma ação externa sem gateway |
| `prompt_only` exige provider dry-run | E2 — braço inseguro nunca produz efeito externo |
| Braço de modelo válido | RF33 — A vs C torna H1 ininterpretável |
| Regra de dependência (`import-linter`) | `analysis/` não importa `agents/` nem SDK de LLM |
| Núcleo sem domínio | RNF06 |
| Retomada por lease | RNF03 |
| Aplicabilidade ≠ zero | RF35 |
| Caminho único ticket/suíte | RF39 |
| **Trace preservado sob falha de sink secundário** | ADR-14 — observabilidade não é ponto único de falha |

**E2E consome cota.** O piloto mede o consumo real por arquitetura. Dois ou três testes, rodados
manualmente antes de marcos — nunca em CI a cada commit.

### 6.4 O ciclo, na prática

```
1. Escreva o teste que falha       ← define o comportamento
2. Implemente o mínimo             ← faça passar
3. Refatore                        ← com a rede de proteção
```

**Começando por um caso real, não por um genérico.** Para o scorer M5b:

```python
def test_m5b_precondicao_utilizada_e_nao_apenas_obtida():
    """TKT-INV-06: baseline invalidated obtido E citado na resolução."""
    trace = trace_sintetico(
        passos=[("getAnalysis", {"baseline_state_at_detection": "invalidated"}),
                ("getBaseline", {"state": "invalidated"})],
        resolution=Resolution(
            decision="escalar",
            evidence_cited=[EvidenceRef(tool="getBaseline", field="state",
                                        value="invalidated", step=1)]))
    r = score_m5b(trace, golden_tkt_inv_06)
    assert r.applicable and r.value == 1.0

def test_m5b_obtida_mas_nao_utilizada():
    """Informação estava disponível e o agente ignorou — M5a passa, M5b falha."""
    ...  # mesmo trace, evidence_cited vazio
```

Repare que o **segundo teste é o que dá valor à métrica**. Um teste que só cobre o caminho feliz não
prova que o instrumento discrimina.

---

## 7. Definition of Done — geral

Vale para toda fase:

- [ ] Testes de unidade escritos **antes** da implementação
- [ ] Testes de invariante passando
- [ ] Contratos Pydantic validados nas fronteiras (RNF13)
- [ ] Sem `import` violando a regra de dependência (`lint-imports` verde)
- [ ] Documentação atualizada se a decisão mudou

---

## 8. 🎁 Extras — só se sobrar tempo

Tudo abaixo é **valor adicional, não requisito**. Nenhum item aqui é pré-condição de nenhuma
hipótese, de nenhum RF obrigatório, nem do GO/NO-GO. A ordem é por **valor entregue ÷ custo** —
execute de cima para baixo, e pare quando o tempo acabar.

> **A regra de ouro dos extras:** só começa um item da lista se o núcleo estiver verde **e** se ele
> couber inteiro no tempo restante. Extra pela metade é pior que extra nenhum — vira dívida que
> aparece na apresentação.

| # | Extra | Trabalho | Cota extra | O que agrega |
| ---: | :--- | :--- | ---: | :--- |
| **1** | **E-V2 — Rubrica binária vs Likert** | ~3 h | **0 execuções**<br>+594 julgamentos | Testa se a decomposição binária realmente aumenta a concordância com humano. **Não reexecuta o agente** (RF34) — melhor relação valor/custo do catálogo |
| **2** | **Validação cruzada `ToolCorrectness`** | ~2 h | ~30 chamadas | Confronta M5a/M6 (implementação própria) com métrica de biblioteca terceira. Argumento de validade de instrumento, quase de graça |
| **3** | **E-T2 — Isolamento de tool sem isolamento de agente** | ~4 h | +272 exec | **Resolve a limitação L11**: separa "efeito de isolamento de contexto" de "efeito de catálogo menor". Converte limitação declarada em achado |
| **4** | **E-A6 — Agente adversarial ("advogado do diabo")** | ~1,5 dia | +~300 exec | Camada probabilística adicional. Ver §8.1 |
| **5** | **Envelope MCP sobre a camada de tools** | ~2 h | 0 | Permite plugar Claude Desktop / Slack / n8n no sistema. ADR-01 já deixa o caminho aberto — é adaptador, não reescrita |
| **6** | **E-A3 — Handoff tipado vs handoff em prosa** | ~4 h | +272 exec | Valida o ADR-05 e a predição P1.4, hoje afirmações não demonstradas |
| **7** | **E-V4 — Casos base vs casos gerados** | ~4 h | +272 exec | Verifica se casos sintéticos reproduzem a dificuldade dos originais — pré-requisito honesto para o item 8 |
| **8** | **Ampliação do golden dataset** (17 → 30 casos) | ~1 dia | +muito | Mais poder estatístico. **Mas cada caso novo multiplica por 60 execuções** — só cabe se o experimento terminar cedo, e só faz sentido depois do item 7 |
| **9** | **Autenticação / papéis / multi-tenancy no front** | ~1 dia | 0 | Realismo de produto. Zero valor experimental — último por isso |

> A ordem dos experimentais (E-V2 → E-T2 → E-A6 → E-A3 → E-V4) é a mesma da §9.2 de
> [`10-matriz-de-experimentos.md`](./10-matriz-de-experimentos.md). Os itens não-experimentais estão
> intercalados pelo mesmo critério de valor ÷ custo.

### 8.1 O agente adversarial (E-A6) — por que está aqui e não no núcleo

A ideia: um **quarto agente** que percorre o mesmo caminho dos outros, mas com instrução invertida —
em vez de "resolva o ticket", recebe "**encontre o motivo pelo qual esta resolução está errada**".
No fim, as duas linhas de raciocínio se confrontam e a que sobrevive é a entregue.

**Por que é bom:** ataca o modo de falha mais perigoso do sistema — o agente que constrói uma
narrativa plausível e coerente a partir de uma premissa errada, e que os controles determinísticos
não avaliam semanticamente. O `PreDeliveryGuard` verifica se a evidência **existe**; o adversarial
questiona se ela **sustenta a conclusão**.

**Por que é extra e não núcleo:**

| Razão | Detalhe |
| :--- | :--- |
| **Custa cota que o experimento não reservou** | +~300 execuções além do máximo condicional de 996; prazo depende do piloto |
| **Não pertence a nenhuma hipótese** | H1 é dose-resposta de arquitetura; H4 é não-inferioridade de modelo. Como **quinto braço** seria uma H5 que não existe — e com 4 hipóteses já declaradas, não cabe |
| **Muda o objeto de medida** | Se entrar no caminho de entrega, H1 passa a medir "agente + adversarial", não a arquitetura |
| **Confunde a defesa** | A tese é sobre engenharia e avaliação de agentes. Um mecanismo novo no fim do cronograma dilui isso |

**Como fica documentado mesmo se não for implementado:** o desenho completo está em
[`10-matriz-de-experimentos.md`](./10-matriz-de-experimentos.md) (E-A6) — prompt, protocolo de
confronto, critério de desempate e métrica. Na apresentação, isso vira uma seção de **Trabalhos
Futuros com desenho pronto**, que vale mais que uma implementação apressada e não medida.

### 8.2 As camadas de defesa — onde cada uma está

Contexto para entender onde E-A6 se encaixa (ADR-13):

| # | Camada | Quando age | Garantia | Status |
| ---: | :--- | :--- | :--- | :--- |
| 1 | **Composição por `tier`** (RF12) | na composição | determinística por papel | **implementada — Fase 1** |
| 2 | **Instrução no prompt** | **durante** | probabilística | **implementada — Fase 2** |
| 3 | **`PreActionGuard`** (RF13–RF15) | antes da API | determinística | **implementada — Fase 3** |
| 4 | **`PreDeliveryGuard` V1·V2·V3** (RF44) | antes da resposta | determinística | **implementada — Fase 3** |
| 5 | **Agente adversarial** (E-A6) | antes de **agir**, por confronto | probabilística e **independente** | extra, não iniciado |

> **O juiz LLM não é camada de defesa.** Ele mede, não protege — roda fora do caminho de entrega, na
> camada de análise (Fase 6). Colocá-lo no caminho aumentaria latência e consumo, além de contaminar
> H1, que passaria a medir "agente + juiz".

> As camadas 1, 3 e 4 são **determinísticas**; as camadas 2 e 5 são **probabilísticas**. Por isso o
> núcleo garante as determinísticas primeiro.

---

## 9. Plano de contingência

Se o GO/NO-GO de 31/08 falhar, **corte nesta ordem**. Cada corte preserva o que a rubrica pesa mais.

> **Antes de qualquer corte desta lista: a §8 inteira já está fora.** Extras não são cortes — eles
> nunca foram compromisso.

| # | Corte | Custo | Perde |
| ---: | :--- | :--- | :--- |
| 1 | **E3** (H3, overlay) | −130 exec | Uma hipótese secundária, já condicional |
| 2 | **Multi-turno** (RF40, RF41) | −1,5 dia | Feature SHOULD; RF43 continua obrigatório sempre que a sessão multi-turno estiver habilitada |
| 3 | **Braço C** (H4) | −272 exec | Uma hipótese; A vs B permanece intacto |
| 4 | **Console de atendimento** | −1 dia | Mantém chat + dashboard |
| 5 | **Front React → relatório HTML estático** | −2 dias | Demo ao vivo; resultados continuam. **O Langfuse continua servindo de inspeção** |
| 6 | Reduzir seeds de 8 para 4 | −272 exec | Poder da análise dose-resposta |

**Nunca cortar:**

- Experimento A vs B — é a hipótese central
- Guarda de isolamento — sem ela nenhum resultado vale
- Trace estruturado em JSONL — sem ele não há dado
- `PreActionGuard` e `PreDeliveryGuard` — impedem efeito e entrega inseguros
- Meta-avaliação do juiz — sem ela as métricas de rubrica têm erro desconhecido

---

## 10. Riscos do cronograma

| ID | Risco | Sinal | Resposta |
| :--- | :--- | :--- | :--- |
| **RC-01** | Núcleo não pronto em 31/08 | GO/NO-GO falha | Cortar pela §9 e iniciar o experimento no dia 01 de qualquer forma |
| **RC-02** | Tool calling do Gemini instável | Taxa de `contract` alta na Fase 2 | Trocar de modelo **na Fase 2**, não depois |
| **RC-03** | Vazão medida não comporta o máximo | Script de medição da Fase 0 | Preservar 594; cortar E3/E4 antes de reduzir seeds ou repetições |
| **RC-04** | Experimento inicia atrasado | Passar de 01/09 | Cada dia de atraso tira um dia da análise. Após 03/09, cortar o braço C |
| **RC-05** | Bug de métrica descoberto tarde | Valores implausíveis | Recomputação é barata (RF34) — só não reexecute o agente |
| **RC-06** | Rotulação humana empurrada | Não feita até 31/08 | **Fazer mesmo assim antes de ver resultados** — é o que garante a validade da meta-avaliação |
| **RC-07** | Spike de `pydantic-ai` vira rabbit hole | Passar de 2 h na Fase 0 | **Timebox rígido.** Estourou, adota loop próprio e segue — a decisão importa menos que o tempo |
| **RC-08** | Langfuse self-host não sobe | Passar de 2 h na Fase 0 | Cloud free tier; se nem isso, `JsonlTraceSink` sozinho. **Não é bloqueio de nada** |
| **RC-09** | Extra iniciado sem caber | Item da §8 pela metade em 06/09 | Descartar o parcial e documentar como Trabalho Futuro. Não levar meia-implementação à apresentação |

---

## 11. Resumo em uma tela

| Data | Foco | Marco |
| :--- | :--- | :--- |
| 24–25/08 | Contratos, portas, **fakes**, invariantes, **Langfuse** | `pytest` verde · trace visível na UI |
| 26/08 | Camada de ferramentas | 18 tools geradas |
| 27/08 | Agente mono + prompt base | um caso ponta a ponta |
| 28/08 | Fila, runner e **guards pré-ação/pré-entrega** | 20 casos, retomada funciona |
| 29–30/08 | Golden dataset e métricas | métricas sobre traces reais |
| 31/08 | Multi-agente | 🚦 **GO / NO-GO** |
| 01–02/09 | 🔄 experimento rodando ‖ ingestão e multi-turno | progresso conforme vazão medida |
| 03/09 | 🔄 ‖ console + chat | núcleo priorizado |
| 04/09 | 🔄 ‖ dashboard de hipóteses | E3/E4 apenas se autorizadas pelo orçamento |
| 05–06/09 | 🔄 ‖ juiz, meta-avaliação, estatística | 594 obrigatórias; até 996 condicionais |
| 07/09 | Análise, README, apresentação | veredito ou não-execução explícita por hipótese |
| **08/09** | **Entrega e apresentação** | |
| — | 🎁 §8 — extras, **só se sobrar tempo** | E-V2 → ToolCorrectness → E-T2 → E-A6 → … |
