# 06 — Matriz de Rastreabilidade

> Este documento é a **fonte autoritativa** de cruzamento entre artefatos. Onde houver divergência
> de numeração com outro documento, esta matriz prevalece.

**Cadeia de rastreabilidade:**

```
Persona → User Story → Requisito → Caso de Uso → Cenário de teste → Métrica → Hipótese
```

Cada elo responde a uma pergunta: *para quem* · *o que quer* · *o que o sistema deve fazer* ·
*como se comporta* · *como se testa* · *como se mede* · *o que se prova*.

---

## 1. Matriz principal — US → RF → UC → Cenário → Métrica

### EP01 — Contextualizar

| US | Requisitos | UC | Chamado | Métricas | Hipótese |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **US01** Procedimento aplicável | RF01, RF02, RF08, RF09, RF11 | UC-01, UC-09 | TKT-CTX-01 | M1, M4, M6, M8, M9 | — |
| **US02** Termo técnico | RF01, RF02, RF08, RF09, RF11 | UC-01, UC-09 | TKT-CTX-02 | M1, M4, M6, M8, M9 | — |
| **US03** Origem do limiar ⚠️ | RF01, RF07, RF08, RF10, RF11 | UC-01, UC-03 | TKT-CTX-03 | M4, **M7**, M8, M10 | **H3** |

### EP02 — Investigar

| US | Requisitos | UC | Chamado | Métricas | Hipótese |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **US04** Falha sem alerta | RF05, RF09, RF11, RF16 | UC-02, UC-04 | TKT-INV-04 | M1, M4, **M5b**, M9 | **H1** |
| **US05** Tendência sem insight | RF05, RF08, RF11 | UC-02, UC-04 | TKT-INV-05 | M1, M4, **M5b**, M8 | **H1** |
| **US06** Falso positivo ⚠️ | RF05, RF08, RF10, RF11 | UC-02, UC-03, UC-04 | TKT-INV-06 | M1, M4, **M5b**, **M8**, M14 | **H1** |
| **US07** Elétrica ou mecânica | RF08, RF09, RF10 | UC-02, UC-03 | TKT-INV-07 | M4, M8, **M9** | H1 |
| **US08** Diagnósticos divergentes | RF08, RF10, RF11 | UC-03, UC-04 | TKT-INV-08 | M4, **M8**, M14 | **H1** |
| **US09** Análise desatualizada | RF05, RF09, RF11, RF15 | UC-02, UC-05 | TKT-INV-09 | M1, M4, **M5b** | H1 |
| **US10** Sinal ruim | RF05, RF08, RF09 | UC-02 | TKT-INV-10 | M4, **M5b**, M8, M9 | **H1** |
| **US11** Cobertura do modelo | RF05, RF08 | UC-02 | TKT-INV-11 | M1, M4, M6 | — |
| **US12** Detecção sem baseline ⚠️ | RF05, **RF06**, RF11 | UC-02 | TKT-INV-11b | M4, **M5b**, M6 | **H1** |

### EP03 — Executar

| US | Requisitos | UC | Chamado | Métricas | Hipótese |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **US13** Reprocessar | RF12, RF13, RF14, RF15 | UC-05, UC-10 | TKT-EXE-12 | M4, **M10**, **M11** | **H2** |
| **US14** Análise especializada | RF13, RF15 | UC-05, UC-10 | TKT-EXE-13 | M4, M10 | H2 |
| **US15** Alterar criticidade | RF12, RF13, **RF14**, RF15 | UC-05, UC-10 | TKT-EXE-14 | M4, **M10**, **M11** | **H2** |
| **US16** Retreinamento | RF12, RF13, RF14, **RF15** | UC-05, UC-10 | TKT-EXE-15 | M4, **M10**, M11 | **H2** |
| **US17** Escalar | RF11, RF13, RF15 | UC-04, UC-05 | TKT-EXE-16 | M4, M11 | — |

### EP06 — Atender *(produto)*

| US | Requisitos | UC | Métricas |
| :--- | :--- | :--- | :--- |
| **US25** Abrir ticket | RF37, RF42 · RNF18 | UC-11 | — |
| **US26** Prioridade por criticidade | RF38, RF42 | UC-11 | — |
| **US27** Multi-turno | RF40, RF41, **RF43** | UC-11, UC-12 | — |

### EP04 — Avaliar

| US | Requisitos | UC | Métricas | Hipótese |
| :--- | :--- | :--- | :--- | :--- |
| **US18** Executar suíte | RF20, RF22, RF24, RF25, RF28 | UC-06 | todas | H1, H2, H3 |
| **US19** Retomar execução | RF23 | UC-06 | — | — |
| **US20** Rubrica | RF26, RF27 | UC-07 | C1–C8 | H1 |
| **US21** Estabilidade | RF24 | UC-06 | **M12**, **M13** | H1 |

### EP05 — Inspecionar

| US | Requisitos | UC | Métricas |
| :--- | :--- | :--- | :--- |
| **US22** Inspecionar trajetória | RF17, RF18, RF30 | UC-08 | — |
| **US23** Tempo real | RF19, RF29 | UC-08 | — |
| **US24** Comparar | RF28, RF31, RF32 | UC-08 | M1–M15 |

> ⚠️ = caso discriminante da hipótese central. **Negrito** = requisito ou métrica primária daquela linha.

---

## 2. RF → artefatos (cobertura reversa)

Verifica que **todo requisito tem origem e destino**. Requisito sem US é requisito órfão; requisito
sem verificação é intenção.

| RF | Origem (US) | UC | Verificado por |
| :--- | :--- | :--- | :--- |
| RF01 Interpretar NL | US01–US17 | UC-01, UC-02 | Execução sem erro nos 17 casos |
| RF02 Consultar via MCP | US01–US17 | UC-09 | Auditoria de trace: toda chamada via `tools/call` |
| RF03 Gerar tools do OpenAPI | arquitetura | UC-09 | Tools == `operationId` do contrato |
| RF04 Overlay | arquitetura | UC-09 | Contrato base íntegro; descrições enriquecidas |
| RF05 Pré-condições | US04–US06, US09–US12 | UC-02 | **M5b** |
| RF06 Modo de detecção | US12 | UC-02 | **M5b** em TKT-INV-11b |
| RF07 Limiar do baseline | US03 | UC-01 | **M7**, V3 |
| RF08 Evidência rastreável | US01–US10 | UC-01–UC-03 | **M8**, V1 |
| RF09 Declarar lacuna | US04, US07, US10 | UC-01, UC-02 | **M9** |
| RF10 Reconciliar conflito | US03, US06–US08 | UC-03 | M4, M8 em casos `conflict` |
| RF11 Classificar decisão | US04–US17 | UC-04 | **M4** |
| RF12 Restringir por tier | segurança | UC-05 | Teste de composição; **M10** |
| RF13 Validar permissão | US13–US17 | UC-10 | **M11**, V4 |
| RF14 Confirmação | US13, US15, US16 | UC-05 | **V4** |
| RF15 Justificativa fundamentada | US16, US17 | UC-05 | M8 no campo justificativa |
| RF16 Política de parada (8 passos) | robustez + orçamento | UC-02, UC-04 | `stop_reason` registrado |
| RF17 Trace estruturado | US22 | UC-08 | Auditoria de cobertura (RNF07) |
| RF18 Handoffs | US22 | UC-08 | **M14** |
| RF19 Streaming | US23 | UC-08 | RNF08 |
| RF20 Golden dataset | US18 | UC-06 | Validação de schema |
| RF21 Gerar casos | US18 | UC-06 | Derivabilidade auditável |
| RF22 Runner paralelo | US18 | UC-06 | RNF12 |
| RF23 Checkpoint | US19 | UC-06 | Teste de interrupção (RNF03) |
| RF24 Métricas determinísticas | US18, US21 | UC-06 | Reprodutibilidade sobre mesmos traces |
| RF25 Alucinação | US03, US06 | UC-06 | **V1**, V2 |
| RF26 Rubrica | US20 | UC-07 | Estrutura de veredito válida |
| RF27 Meta-avaliação | US20 | UC-07 | Relatório de kappa |
| RF28 Comparar arquiteturas | US18, US24 | UC-06 | Relatório comparativo |
| RF29 Submeter na UI | US23 | UC-08 | Trace equivalente ao da CLI |
| RF30 Inspecionar na UI | US22 | UC-08 | Todo campo acessível |
| RF31 Dashboard | US18, US24 | UC-08 | Valores == suíte |
| RF32 Lado a lado | US24 | UC-08 | Divergências == suíte |
| RF33 Braços de modelo válidos | validade experimental | — | Runner valida a combinação (arquitetura, atribuição) |
| RF34 Métricas recomputáveis | US18 | UC-06 | Alterar definição e recomputar sem reexecutar |
| RF35 Aplicabilidade explícita | validade experimental | UC-06, UC-07 | M14 em mono retorna `applicable=0`, não `value=0` |
| RF36 Cache de julgamentos | US20 | UC-07 | Rejulgar mesma combinação não emite requisições |
| RF37 Ingestão de tickets | US25 | UC-11 | `202` em < 200 ms (RNF18) |
| RF38 Prioridade derivada | US26 | UC-11 | Ativo crítico ultrapassa na fila |
| RF39 Caminho único ticket/suíte | integridade | UC-11 | Sem ramo por `kind` dentro do agente |
| RF40 Sessão multi-turno | US27 | UC-12 | Segunda mensagem não repete consultas |
| RF41 Solicitar informação | US27 | UC-12 | Estado `awaiting_user` e retomada |
| RF42 Console de atendimento | US25, US26 | UC-11 | Todo estado visível e navegável |
| RF43 Agente sem estado | US27 | UC-12 | Retomada por worker diferente, contexto íntegro |
| RF44 Guardrail na entrega | segurança de produto | UC-04 | **M16** · resolução com evidência forjada não é entregue |

**Resultado: 44 de 44 RF com origem e verificação definidas. Zero órfãos.**

---

## 3. RNF → mecanismo → verificação

| RNF | Mecanismo arquitetural | Componente | Verificação |
| :--- | :--- | :--- | :--- |
| RNF01 Reprodutibilidade | `temperature=0` + seed da API (que é determinística) | C3, C5 | ≥95% trajetórias idênticas em 10 repetições |
| RNF02 Isolamento 🛑 | `IsolationGuard` bloqueante | C5 | Teste que aborta a suíte; zero tolerância |
| RNF03 Durabilidade | **Fila com lease** em SQLite (ADR-07) | C5, C6 | Interrupção em 3 pontos; ≤1 caso reprocessado |
| RNF04 Falha transitória | `RetryPolicy` com recuo exponencial | C4, C5 | Injeção de falha simulada |
| RNF05 Menor privilégio | Composição por `tier` do overlay | C3, C4 | Interseção vazia validada na inicialização |
| RNF06 Portabilidade | Núcleo genérico sem domínio | C4 | Varredura de código; segundo contrato OpenAPI |
| RNF07 Observabilidade | `TraceEmitter` no servidor MCP | C4 | Contagem cruzada chamadas × registros |
| RNF08 Latência SSE | Streaming no BFF | C2 | p95 ≤ 1000 ms |
| RNF09 Independência do juiz | Asserção de modelo distinto | C5 | Aborta se coincidirem |
| RNF10 Neutralidade de ordem | Comparação nas duas ordens | C5 | Assimetria reportada |
| RNF11 Custo | Contabilização de tokens | C3, C5 | Relatório de consumo (M15) |
| RNF12 Tempo | Token bucket na taxa do provedor (ADR-09) | C5 | Núcleo (1.021 execuções) em ≈ 5,5 dias a 187/dia |
| RNF13 Validação de contratos | Pydantic em toda fronteira | C3, C4, C5 | Testes com objetos malformados |
| RNF14 Ambiente reprodutível | Dependências fixadas | todos | Execução em ambiente limpo |
| RNF15 Configuração registrada | Metadados no trace | C3, C5 | Completude validada na suíte |
| RNF16 Guarda de cota | Pausa de lease + contador em Redis | C5, C7 | Teste com cota reduzida; zero requisições além do teto |
| RNF17 Coordenação efêmera | Redis para pub/sub, rate limit e cota (ADR-11) | C7 | Teste com Redis derrubado: zero perda em `queue.db` e `traces/` |
| RNF18 Latência de aceitação | Enfileiramento assíncrono | C2, C6 | p95 ≤ 200 ms sob fila carregada |
| RNF19 Continuidade sob pico | Fila durável com prioridade | C5, C6 | Rajada 10× acima da vazão: zero perdas |

---

## 4. Hipótese → predição → métrica → cenário

Esta é a matriz que conecta a documentação de engenharia ao experimento. Sem ela, as duas partes do
projeto ficariam desconectadas.

### H1 — Isolamento de contexto e perda no handoff

| Predição | Métrica | Cenários discriminantes | Requisito instrumentado |
| :--- | :--- | :--- | :--- |
| **P1.1** Vantagem cresce com a intensidade de degradação (dose-resposta) | M4 × intensidade | Todos, 8 configurações de seed | RF11 |
| **P1.2** Maior verificação de pré-condição | **M5b** | TKT-INV-04, 05, 06, 09, 10, 11b | **RF05, RF06** |
| **P1.3** Menor alucinação em conflito | **M8** | TKT-INV-06, 08, TKT-CTX-03 | **RF08, RF10** |
| **P1.4** Maior perda no handoff | **M14** | TKT-INV-06, 08 | **RF18** |

### H2 — Garantia estrutural versus instrução

| Predição | Métrica | Cenários discriminantes | Requisito instrumentado |
| :--- | :--- | :--- | :--- |
| **P2.1** Zero execução indevida na multi | M10 | A1, A2, A4, A5 | **RF12** |
| **P2.2** Taxa não nula na mono | **M10** | A1, A2, A4 (peso alto) | RF13, RF14 |
| **P2.3** Diferença cresce com insistência | M10 | A2 (insistência) | RF14, RF15 |

### H3 — Enriquecimento semântico

| Predição | Métrica | Cenários discriminantes | Requisito instrumentado |
| :--- | :--- | :--- | :--- |
| **P3.1** Maior cobertura de trajetória | M1 | Todos | RF03, RF04 |
| **P3.2** Menor afirmação vedada | **M7** | TKT-CTX-03 | **RF07** |
| **P3.3** Efeito maior em modelo menor | M1, M7 | Todos × modelo | RF04 |

---

## 5. Modo de degradação → cenários → fluxos → métricas

| Modo | Chamados | Fluxos de exceção | Métricas sensíveis | n |
| :--- | :--- | :--- | :--- | ---: |
| `complete` | todos (regime seed) | fluxos principais | M1, M4, M8 | 17 |
| `partial` | CTX-01, CTX-02, INV-07, INV-11b | FE-01.1, FE-02.1, FE-03.2 | **M9**, M8 | 4 |
| `inconclusive` | INV-04 | FE-02.2 | **M9**, M4 | 1 |
| `conflict` | CTX-03, INV-06, INV-08 | UC-03, FE-03.1 | **M8**, M4, M14 | 3 |
| `unavailable` | INV-04 | FE-01.2, FE-02.3 | **M9** | 1 |
| `stale` | INV-09 | FE-02.4 | M5a/M5b, M4 | 1 |
| `pending` | INV-05 | FA-02.4 | M4, M5b | 1 |

> ⚠️ **Limitação L9 evidenciada aqui.** Os modos `inconclusive`, `unavailable`, `stale` e `pending`
> possuem **n = 1** no dataset base. Conclusões por modo têm confiança muito desigual. Esta é a
> principal motivação para a ampliação do dataset (RF21) — e, sem ela, os resultados por modo devem
> ser lidos como indicativos, jamais como conclusivos.

---

## 6. Persona → permissão → casos de uso acessíveis

| Persona | Permissões | UC acessíveis | Ações habilitadas |
| :--- | :--- | :--- | :--- |
| P01 Operador | `read` | UC-01, UC-02, UC-03, UC-04 | nenhuma |
| P02 Mecânico | `read`, `action_low` | + UC-05 (parcial) | reprocessar, análise especializada |
| P03 Analista | `read`, `action_low` | + UC-05 (parcial) | reprocessar, análise especializada |
| P04 Engenheiro | `read`, `action_low`, `action_high` | + UC-05 (pleno) | + config técnica, retreinamento |
| P05 Eletricista | `read` | UC-01, UC-02, UC-03, UC-04 | nenhuma |
| P06 Coordenador | `read`, `action_low`, `escalate` | + UC-05 (parcial) | reprocessar, especialista, escalar |
| P07 Gerente | todas | todos | todas |
| P08 Avaliador | — | UC-06, UC-07, UC-08 | — |

---

## 7. Componente → requisitos atendidos

| Componente | Requisitos |
| :--- | :--- |
| **C1** Interface Web | RF29, RF30, RF31, RF32 · RNF08 |
| **C2** Backend / BFF | RF19, RF29 · RNF08 |
| **C3** Núcleo do Agente | RF01, RF05–RF11, RF15–RF18 · RNF01, RNF05, RNF13, RNF15 |
| **C4** Servidor MCP | RF02, RF03, RF04, RF12, RF13, RF14, RF17 · RNF04–RNF07, RNF13 |
| **C5** Avaliação | RF20–RF28, RF33 · RNF01–RNF04, RNF09–RNF13, RNF15, RNF16 |
| **C6** Armazenamento durável | RF17, RF20, RF34–RF36 · RNF03 |
| **C7** Coordenação efêmera | RF19 · RNF08, RNF16, RNF17 |

---

## 8. Cobertura consolidada

| Artefato | Total | Rastreado | Cobertura |
| :--- | ---: | ---: | ---: |
| Chamados do material | 17 | 17 | **100%** |
| User stories | 27 | 27 | **100%** |
| Requisitos funcionais | 44 | 44 | **100%** |
| Requisitos não-funcionais | 19 | 19 | **100%** |
| Casos de uso | 12 | 12 | **100%** |
| Modos de degradação | 7 | 7 | **100%** |
| Personas | 8 | 8 | **100%** |
| Métricas | 17 | 17 | **100%** |
| Hipóteses | 4 | 4 | **100%** |

### Requisitos sem métrica quantitativa direta

Nem todo requisito é medido pelo experimento — alguns são verificados por teste, não por métrica.
Registrado para evitar a impressão de que a matriz mede tudo:

| RF | Verificação | Por que não há métrica |
| :--- | :--- | :--- |
| RF03, RF04 | Teste estrutural | Propriedade de construção, não de comportamento |
| RF19, RF29–RF32 | Teste funcional da UI | Interface não é objeto do experimento |
| RF22, RF23 | Teste de interrupção | Propriedade de infraestrutura |

---

## 9. Ordem de implementação sugerida

Derivada das dependências entre componentes. Requisitos marcados 🛑 bloqueiam os seguintes.

| Etapa | Requisitos | Bloqueia |
| :--- | :--- | :--- |
| 1 | RF03, RF04 — servidor MCP com overlay | tudo |
| 2 | 🛑 RF17 — trace estruturado | todo o experimento |
| 3 | RF01, RF02, RF16 — loop ReAct mono | arquitetura A |
| 4 | RF05–RF11 — disciplina de evidência | H1 |
| 5 | RF12–RF15 — segurança e ação | H2 |
| 6 | RF18 — handoffs; arquitetura multi | H1 |
| 7 | 🛑 RNF02 — isolamento | qualquer resultado válido |
| 8 | RF20, RF22–RF25, RNF16 — fila, runner e métricas | E1, E2 |
| 9 | RF26, RF27 — juiz e meta-avaliação | rubrica |
| 10 | RF34–RF36 — camada de análise | resultados |
| 11 | RF19, RF29–RF32 — interface | demonstração |
| 12 | RF21, RF28 — ampliação e comparação | H3 |

> **RF17 e RNF02 são os dois bloqueadores absolutos.** Sem trace estruturado não há dado
> experimental; sem isolamento verificado, nenhum resultado é válido. Ambos precedem qualquer
> execução que produza número reportável.
