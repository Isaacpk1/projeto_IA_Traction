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
| O experimento leva **5,5 dias de execução** a 187/dia | Não é trabalho, é **espera**. Não acelera com esforço |
| O julgamento roda **1 dia atrás** do agente | Termina ~1 dia depois da última execução |
| A análise precisa dos resultados | Só começa quando o experimento acaba |

**Portanto:**

> ### 🚦 Tudo que o experimento precisa para rodar tem que estar pronto até **31/08**.

São **7 dias** para construir: contratos, camada de ferramentas, agente mono, agente multi, fila,
runner, golden dataset e métricas.

O que vem depois — ingestão de tickets, console, BFF, front, juiz, estatística — é construído
**enquanto o experimento roda em segundo plano**. Essa é a única forma de caber.

---

## 2. As duas trilhas

```
        ├──────── CONSTRUÇÃO DO NÚCLEO ────────┤
24/08 ──┤ contratos · tools · agente · fila     ├── 31/08  🚦 GO/NO-GO
        │ métricas · golden dataset             │
        └───────────────────────────────────────┘
                                                 │
01/09 ──┬─ TRILHA A (fundo) ── experimento executando ──────────┬── 06/09
        │                       1.021 execuções · 5,5 dias      │
        │                                                        │
        └─ TRILHA B (frente) ── ingestão · console · BFF ────────┘
                                front · juiz · estatística

07/09 ── análise dos resultados · README · apresentação
08/09 ── ENTREGA
```

**A trilha A não exige atenção.** O runner é CLI, roda sozinho, retoma se cair, pausa na cota e
prossegue. Você olha o progresso pelo console uma vez por dia.

---

## 3. Fases

### Fase 0 — Fundação · **24–25/08** (2 dias)

| Entrega | Detalhe |
| :--- | :--- |
| `pyproject.toml` + estrutura de pastas | conforme [`13`](./13-padroes-e-estrutura.md) |
| `core/contracts/` | `ExecutionTrace`, `Resolution`, `EvidenceRef`, `InvestigationReport`, `GoldenCase`, `MetricResult`, `Task` |
| `core/ports/` | `LLMClient`, `ToolProvider`, `WorkQueue`, `TraceSink` |
| **`tests/fakes/`** | **`FakeLLMClient`, `FakeToolProvider`, `InMemoryQueue`** |
| `tests/test_architecture.py` | regra de dependência |
| Script de medição de cota | valida os 187/dia |

> **Os fakes vêm primeiro, antes de qualquer implementação real.** Sem `FakeLLMClient`, não existe
> TDD do agente — só teste de integração caro e não-determinístico. Ver §5.

**DoD:** `pytest` verde · regra de dependência falhando quando violada de propósito · cota medida.

---

### Fase 1 — Camada de ferramentas · **26/08** (1 dia)

`openapi_parser` · `overlay` merge · `tool_factory` · `http_executor` · `tier_registry`

**DoD:** 18 tools geradas do contrato real, com descrição enriquecida e `tier` correto · varredura de
domínio em `tools/core/` passa (RNF06) · teste de composição por `tier` passa (RF12).

---

### Fase 2 — Agente mono · **27/08** (1 dia)

`react.py` · `tracer.py` · `submit_resolution` · prompt base (`prompts/base.md`) · adaptador Gemini

**DoD:** um caso completo com `FakeLLMClient` (determinístico, em milissegundos) · **depois** o mesmo
caso contra Gemini real e API local · trace válido gravado.

---

### Fase 3 — Fila e runner · **28/08** (1 dia)

`queue_sqlite.py` · `worker.py` · `rate_limiter.py` · `isolation_guard.py`

**DoD:** 20 casos executam · interromper com `Ctrl-C` e reexecutar retoma sem reprocessar · guarda de
isolamento aborta quando o gabarito é exposto de propósito (RNF02).

---

### Fase 4 — Golden dataset e métricas · **29–30/08** (fim de semana, 2 dias)

`base_cases.json` formalizado dos 17 · `adversarial_cases.json` (A1–A5) · scorers M1–M15

**DoD:** cada métrica com teste sobre trace sintético · métricas calculadas sobre as execuções da
Fase 3 · `applicable` correto (M14 em mono retorna `applicable=0`, não zero — RF35).

---

### Fase 5 — Multi-agente · **31/08** (1 dia)

Orquestrador · 3 papéis · handoff tipado · grafo LangGraph · composição por `tier`

**DoD:** braço B executa um caso · handoff registrado no trace · **teste de RF12 confirma que o
Investigador não possui tool de `tier: impact`**.

---

## 🚦 4. GO / NO-GO — 31 de agosto

Checklist objetivo. Se algum item falhar, **corte pela lista da §8** — não empurre o prazo.

- [ ] Um caso executa de ponta a ponta nos braços A e B
- [ ] Fila retoma após interrupção
- [ ] Guarda de isolamento bloqueia (RNF02)
- [ ] Métricas calculam sobre traces reais
- [ ] Golden dataset com `forbidden_claims` e `required_preconditions`
- [ ] Cota real medida e vazão confirmada
- [ ] Rotulação humana cega dos 30 casos **feita**

> A rotulação humana precisa acontecer **antes** de ver qualquer resultado agregado. Se escorregar
> para depois do experimento, a meta-avaliação do juiz fica contaminada por viés de confirmação.

---

### Fase 6 — Experimento + produto · **01–06/09**

**Trilha A — fundo, sem atenção:**

| Dia | Execuções acumuladas |
| :--- | ---: |
| 01/09 | 187 |
| 02/09 | 374 |
| 03/09 | 561 |
| 04/09 | 748 |
| 05/09 | 935 |
| 06/09 | **1.021 ✓** |

Julgamento roda em paralelo, ~1 dia atrás, a 250/dia.

**Trilha B — construção:**

| Dias | Entrega |
| :--- | :--- |
| 01–02/09 | Ingestão (`POST /tickets`), prioridade, sessão multi-turno (RF37–RF43) |
| 03–04/09 | BFF + front: console de atendimento, chat com streaming, inspetor de trace |
| 05–06/09 | Juiz + rubrica + meta-avaliação (kappa) + camada estatística |

---

### Fase 7 — Fechamento · **07/09** (1 dia)

Análise dos resultados · teste das 13 predições · dashboard com dados reais · README com Resultados
e Limitações · apresentação.

**DoD:** veredito escrito para H1, H2, H3 e H4 — incluindo os **inconclusivos**.

---

## 5. Estratégia de TDD

### 5.1 Por que os fakes vêm primeiro

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

### 5.2 O que se testa como

| Componente | Determinístico? | Abordagem | TDD real? |
| :--- | :---: | :--- | :---: |
| Scorers (M1–M15) | ✅ | função pura sobre trace sintético | ✅ **ideal** |
| Fila (lease, prioridade, idempotência) | ✅ | SQLite em memória | ✅ **ideal** |
| `openapi_parser` + overlay | ✅ | contrato real como fixture | ✅ **ideal** |
| Prioritizer | ✅ | criticidade → prioridade | ✅ **ideal** |
| Sessão multi-turno (RF43) | ✅ | persistir e restaurar | ✅ **ideal** |
| Invariantes (RNF02, RNF05, RF33, RF12) | ✅ | asserção estrutural | ✅ **ideal** |
| Loop ReAct | ⚠️ | `FakeLLMClient` roteirizado | ✅ **sim, com duplo** |
| Handoff tipado | ⚠️ | fake + validação Pydantic | ✅ **sim, com duplo** |
| `http_executor` | ⚠️ | transporte mock do httpx | ✅ **sim, com duplo** |
| Comportamento do agente com LLM real | ❌ | **é o experimento, não teste** | ❌ |
| Qualidade da resolução | ❌ | rubrica + juiz | ❌ |

> **A linha divisória.** Testes verificam que o **sistema funciona**. O experimento mede se o
> **agente raciocina bem**. Confundir os dois leva a testes frágeis que quebram porque o modelo
> respondeu diferente — e isso não é bug.

### 5.3 A pirâmide

```
         ╱ E2E ╲              2–3 testes · LLM real · CONSOME COTA
       ╱ integração ╲         ~20 · fakes + API local
     ╱     unidade     ╲      ~150 · puro, milissegundos
   ╱   invariantes      ╲     ~8 · bloqueiam o build
```

**Os testes de invariante são os mais importantes do projeto**, e não estão no topo por acaso — eles
não medem comportamento, eles **impedem** que o projeto se invalide:

| Teste | Bloqueia |
| :--- | :--- |
| Isolamento do gabarito | RNF02 — vazamento invalida **todos** os resultados |
| Composição por `tier` | RF12 / RNF05 — Investigador sem tool de impacto |
| Braço de modelo válido | RF33 — A vs C torna H1 ininterpretável |
| Regra de dependência | `analysis/` não importa `agents/` |
| Núcleo sem domínio | RNF06 |
| Retomada por lease | RNF03 |
| Aplicabilidade ≠ zero | RF35 |
| Caminho único ticket/suíte | RF39 |

**E2E consome cota.** Cada teste ponta a ponta com LLM real gasta ~8 requisições de um orçamento de
1.500/dia. Dois ou três, rodados manualmente antes de marcos — nunca em CI a cada commit.

### 5.4 O ciclo, na prática

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

## 6. Definition of Done — geral

Vale para toda fase:

- [ ] Testes de unidade escritos **antes** da implementação
- [ ] Testes de invariante passando
- [ ] Contratos Pydantic validados nas fronteiras (RNF13)
- [ ] Sem `import` violando a regra de dependência
- [ ] Documentação atualizada se a decisão mudou

---

## 7. Ferramentas de teste

| Ferramenta | Uso |
| :--- | :--- |
| `pytest` + `pytest-asyncio` | base |
| `pytest-cov` | cobertura — meta 80% em `core/`, `analysis/`, `tools/core/` |
| `respx` ou transporte mock do `httpx` | `http_executor` sem rede |
| SQLite `:memory:` | fila em milissegundos |
| `hypothesis` *(opcional)* | propriedades da fila: lease nunca duplica trabalho |
| `freezegun` | expiração de lease sem esperar |

> **`freezegun` merece destaque.** Testar expiração de lease de 300 segundos sem controlar o relógio
> significaria esperar 5 minutos por teste. Com relógio controlado, milissegundos.

---

## 8. Plano de contingência

Se o GO/NO-GO de 31/08 falhar, **corte nesta ordem**. Cada corte preserva o que a rubrica pesa mais.

| # | Corte | Custo | Perde |
| ---: | :--- | :--- | :--- |
| 1 | **E3** (H3, overlay) | −130 exec | Uma hipótese secundária, já condicional |
| 2 | **Envelope MCP** | −2 h | Interoperabilidade de host (ADR-01 já prevê) |
| 3 | **Multi-turno** (RF40, RF41, RF43) | −1,5 dia | Feature de produto; L10 já declara a lacuna |
| 4 | **Braço C** (H4) | −272 exec | Uma hipótese; A vs B permanece intacto |
| 5 | **Console de atendimento** | −1 dia | Mantém chat + dashboard |
| 6 | **Front React → relatório HTML estático** | −2 dias | Demo ao vivo; resultados continuam |
| 7 | Reduzir seeds de 8 para 4 | −272 exec | Poder da análise dose-resposta |

**Nunca cortar:**

- Experimento A vs B — é a hipótese central
- Guarda de isolamento — sem ela nenhum resultado vale
- Trace estruturado — sem ele não há dado
- Meta-avaliação do juiz — sem ela as métricas de rubrica têm erro desconhecido

---

## 9. Riscos do cronograma

| ID | Risco | Sinal | Resposta |
| :--- | :--- | :--- | :--- |
| **RC-01** | Núcleo não pronto em 31/08 | GO/NO-GO falha | Cortar pela §8 e iniciar o experimento no dia 01 de qualquer forma |
| **RC-02** | Tool calling do Gemini instável | Taxa de `contract` alta na Fase 2 | Trocar de modelo **na Fase 2**, não depois |
| **RC-03** | Cota real abaixo de 187/dia | Script de medição da Fase 0 | Recalcular: menos seeds ou menos repetições |
| **RC-04** | Experimento inicia atrasado | Passar de 01/09 | Cada dia de atraso tira um dia da análise. Após 03/09, cortar o braço C |
| **RC-05** | Bug de métrica descoberto tarde | Valores implausíveis | Recomputação é barata (RF34) — só não reexecute o agente |
| **RC-06** | Rotulação humana empurrada | Não feita até 31/08 | **Fazer mesmo assim antes de ver resultados** — é o que garante a validade da meta-avaliação |

---

## 10. Resumo em uma tela

| Data | Foco | Marco |
| :--- | :--- | :--- |
| 24–25/08 | Contratos, portas, **fakes**, invariantes | `pytest` verde |
| 26/08 | Camada de ferramentas | 18 tools geradas |
| 27/08 | Agente mono | um caso ponta a ponta |
| 28/08 | Fila e runner | 20 casos, retomada funciona |
| 29–30/08 | Golden dataset e métricas | métricas sobre traces reais |
| 31/08 | Multi-agente | 🚦 **GO / NO-GO** |
| 01–06/09 | 🔄 experimento rodando ‖ produto e front | 1.021 execuções |
| 07/09 | Análise, README, apresentação | veredito das 4 hipóteses |
| **08/09** | **Entrega e apresentação** | |
