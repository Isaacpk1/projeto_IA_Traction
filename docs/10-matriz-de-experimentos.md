# 10 — Matriz de Experimentos

> **Para que serve este documento.** O projeto tem muito mais perguntas testáveis do que orçamento
> para testá-las. Este catálogo lista **todas** as comparações possíveis, com custo e valor, para que
> a escolha do portfólio seja uma decisão consciente e registrada — não o resultado do que sobrou de
> tempo.
>
> Ele também protege contra o erro descrito na §6: rodar tudo e reportar o que deu bom.

---

## 1. A regra que governa este documento

**Hipóteses não competem entre si.** H1, H2, H3 e H4 são perguntas diferentes, cada uma com resposta
independente. É possível terminar com as quatro confirmadas, as quatro refutadas, ou qualquer
combinação. Não existe "a melhor hipótese".

O que pode ser ranqueado são as **configurações** — mono vs multi, overlay cru vs enriquecido. Isso é
uma pergunta de engenharia, e é legítima. Só não é a mesma coisa que testar hipótese.

**Consequência prática:** toda predição deve estar escrita **antes** da execução, e **todas** devem
ser reportadas depois — inclusive as que falharem.

---

## 2. Anatomia de um experimento

Cada entrada deste catálogo declara seis campos:

| Campo | O que responde |
| :--- | :--- |
| **Comparação** | O que muda entre os braços |
| **Constante** | O que é mantido fixo — define o que se pode concluir |
| **Permite concluir** | A afirmação que o experimento sustenta ou refuta |
| **Custo** | Execuções adicionais |
| **Valor** | Alto / médio / baixo, com justificativa |
| **Status** | Declarado · Candidato · Descartado |

---

## 3. Catálogo — Arquitetura de agentes

### E-A1 · Mono vs multi-agente `H1` 🟢 DECLARADO

| | |
| :--- | :--- |
| **Comparação** | Agente único com 18 tools **vs** orquestrador + 3 especialistas |
| **Constante** | Modelo, prompt base, conjunto total de tools, casos, seeds |
| **Permite concluir** | Se isolamento de contexto por especialização melhora a investigação |
| **Custo** | 544 execuções |
| **Valor** | **Alto** — é a pergunta central do projeto |

---

### E-A2 · Multi uniforme vs heterogêneo `H4` 🟢 DECLARADO

| | |
| :--- | :--- |
| **Comparação** | Mesmo modelo em todos os papéis **vs** modelo mais barato nos papéis fáceis |
| **Constante** | **Arquitetura** (ambos multi), prompt, tools, casos, seeds |
| **Permite concluir** | Se dá para baratear papéis fáceis sem perder qualidade |
| **Custo** | +272 execuções |
| **Valor** | **Alto** — é a decisão que uma empresa toma ao pôr um agente em produção |

> **Por que precisa ser B vs C, e não A vs C.** A arquitetura mono tem um agente só — não há papéis
> para diferenciar. "Mono heterogêneo" não existe. Comparar mono uniforme com multi heterogêneo
> mudaria arquitetura **e** modelo ao mesmo tempo, e nenhuma análise separaria os efeitos.

---

### E-A3 · Handoff tipado vs handoff em prosa 🔵 CANDIDATO

| | |
| :--- | :--- |
| **Comparação** | `InvestigationReport` validado **vs** resumo em linguagem natural |
| **Constante** | Arquitetura (ambos multi), modelo, tools, casos |
| **Permite concluir** | Se a perda de evidência na fronteira entre agentes é causada pela compressão textual |
| **Custo** | +272 execuções |
| **Valor** | **Alto** — testa diretamente o princípio P3 e o ADR-05, que hoje são afirmações não verificadas |

> **Este é o candidato mais forte fora do escopo declarado.** A predição P1.4 prevê perda no handoff;
> este experimento diria **se o handoff tipado é o que a evita**. Sem ele, ADR-05 permanece uma
> decisão de projeto plausível, mas não demonstrada.

---

### E-A6 · Verificação adversarial antes de agir 🔵 CANDIDATO ⭐

| | |
| :--- | :--- |
| **Comparação** | Com **vs** sem um segundo agente que, antes de uma ação de impacto, investiga o mesmo caso com enquadramento **adversarial** — instruído a refutar a conclusão |
| **Constante** | Arquitetura, modelo, tools, casos |
| **Permite concluir** | Se verificação independente reduz o falso "agir" — o erro de maior custo do sistema |
| **Custo** | +~300 execuções (dispara em ~30% dos casos, os de decisão `agir`) |
| **Valor** | **Alto** — ataca diretamente o modo de falha central do domínio |

> **Por que encaixa neste domínio especificamente.** O modo de falha central aqui é **confirmação**:
> o agente vê `imbalance, confidence 0.87` e confirma. Um agente instruído a refutar iria procurar o
> `baseline_state_at_detection: invalidated`, o pico em 1× baixo que não sustenta o diagnóstico, e a
> análise conflitante do especialista — que é **exatamente a trajetória do gabarito do TKT-INV-06**.
>
> A ideia não é genérica: ela reproduz o raciocínio que o gabarito considera correto.

**Duas leituras possíveis, e elas custam diferente:**

| Como | Custo | Natureza |
| :--- | :--- | :--- |
| **Quinto braço experimental** | +272 execuções, +1,5 dia | uma **quinta hipótese** — com 4 já declaradas e 7 dias até o núcleo, não cabe |
| **Quarta camada de defesa** (ADR-13) | +~300 execuções | **segurança de produto**, mensurável pela taxa de falso "agir" capturado |

A segunda leitura é mais forte: estende a defesa em camadas com um mecanismo de natureza distinta —
probabilístico, mas **independente** do primeiro julgamento.

```
Composição por tier      antes           determinística
Instrução no prompt      durante         probabilística
Guardrail V1·V2·V3       depois          determinística
Advogado do diabo        antes de AGIR   probabilística e independente  ← E-A6
```

**Status.** Fora do ciclo atual, mas **desenhado por inteiro** — prompt, protocolo de confronto,
critério de desempate e métrica ficam registrados aqui. É o item **#4 da lista de extras** em
[`14-roadmap-e-testes.md`](./14-roadmap-e-testes.md) §8: entra se o go/no-go de 31/08 passar com
folga e se couber inteiro no tempo restante. Se não couber, vai à apresentação como **Trabalho
Futuro com desenho pronto** — o que vale mais que uma implementação apressada e não medida.

---

### E-A4 · Resolução estruturada vs texto livre 🔵 CANDIDATO

| | |
| :--- | :--- |
| **Comparação** | Tool terminal `submit_resolution` **vs** parsing da decisão do texto final |
| **Constante** | Arquitetura, modelo, tools de consulta, casos |
| **Permite concluir** | Quanto da qualidade medida vem do formato de saída, não do raciocínio |
| **Custo** | +272 execuções |
| **Valor** | **Médio** — interessa mais à metodologia de avaliação que ao agente |

---

### E-A5 · Orquestrador central vs cadeia sequencial 🔵 CANDIDATO

| | |
| :--- | :--- |
| **Comparação** | Hub-and-spoke **vs** contextualizar → investigar → executar em sequência |
| **Constante** | Modelo, tools por papel, casos |
| **Permite concluir** | Se a topologia importa além do simples isolamento |
| **Custo** | +272 execuções |
| **Valor** | **Baixo** — expande o espaço arquitetural sem responder pergunta pendente |

---

## 4. Catálogo — Camada de ferramentas

### E-T1 · Overlay cru vs enriquecido `H3` 🟡 DECLARADO (amostra)

| | |
| :--- | :--- |
| **Comparação** | Tools geradas direto do OpenAPI **vs** descrições com semântica de domínio |
| **Constante** | Arquitetura, modelo, casos |
| **Permite concluir** | Quanto vale escrever boas descrições de tool |
| **Custo** | ~130 execuções (amostra) |
| **Valor** | **Alto** — poucos projetos quantificam isso, e o resultado é reutilizável fora deste domínio |

---

### E-T2 · Isolamento de ferramenta sem isolamento de agente 🔵 CANDIDATO ⭐

| | |
| :--- | :--- |
| **Comparação** | Mono com 18 tools **vs** mono com o subconjunto relevante por fase |
| **Constante** | **Arquitetura** (ambos mono), modelo, casos |
| **Permite concluir** | **Se o efeito de H1 vem do isolamento de contexto ou apenas do catálogo menor** |
| **Custo** | +272 execuções |
| **Valor** | **Alto** — é o único experimento que **resolve a limitação L11** |

> **Por que este é especial.** L11 registra que a arquitetura multi carrega ~21% menos tokens de
> catálogo, e que parte de um eventual ganho pode vir daí, não do isolamento. Esse confundidor foi
> declarado como não-eliminável. **E-T2 o elimina:** se o mono com catálogo reduzido igualar o multi,
> o efeito era catálogo; se não igualar, era isolamento de contexto de verdade.
>
> Transformaria uma limitação declarada em um achado.

---

### E-T3 · Conhecimento como resource vs como tool 🔵 CANDIDATO

| | |
| :--- | :--- |
| **Comparação** | `/knowledge` exposto como MCP resource **vs** como tool |
| **Constante** | Arquitetura, modelo, demais tools |
| **Permite concluir** | Se a primitiva MCP escolhida afeta o uso do conhecimento |
| **Custo** | +130 execuções (só casos CTX) |
| **Valor** | **Baixo** — elegante conceitualmente, pouco impacto no resultado |

---

## 5. Catálogo — Comportamento e política

### E-P1 · Política explícita de pré-condições 🔵 CANDIDATO

| | |
| :--- | :--- |
| **Comparação** | Prompt com instrução explícita de verificar baseline/qualidade/modelo **vs** sem |
| **Constante** | Arquitetura, modelo, tools, casos |
| **Permite concluir** | Se a disciplina de evidência vem do prompt ou da arquitetura |
| **Custo** | +272 execuções |
| **Valor** | **Médio-alto** — foi a hipótese original do projeto, substituída por H1 |

> Combinado com E-A1, formaria um fatorial 2×2 (arquitetura × política) capaz de separar o efeito do
> prompt do efeito da arquitetura. Custo: 4 células em vez de 2.

---

### E-P2 · Limite de passos: 6 vs 8 vs 12 🔵 CANDIDATO

| | |
| :--- | :--- |
| **Comparação** | Três valores de política de parada |
| **Constante** | Arquitetura, modelo, tools, casos |
| **Permite concluir** | Onde está o ponto de retorno decrescente da investigação |
| **Custo** | +544 execuções (2 braços extras) |
| **Valor** | **Médio** — informa RF16, hoje fixado em 8 por argumento de orçamento e não por evidência |

---

### E-P3 · Temperatura 0 vs 0,3 🔵 CANDIDATO

| | |
| :--- | :--- |
| **Comparação** | Determinístico **vs** com variabilidade |
| **Constante** | Todo o resto |
| **Permite concluir** | Se a exploração ajuda ou atrapalha em investigação com política |
| **Custo** | +272 execuções |
| **Valor** | **Baixo** — em tarefa com resposta correta definida, temperatura 0 é a escolha esperada |

---

## 6. Catálogo — Segurança

### E-S1 · Garantia estrutural vs instrução `H2` 🟢 DECLARADO

| | |
| :--- | :--- |
| **Comparação** | `PreActionGuard` **vs** instrução no prompt, sob casos adversariais e em dry-run |
| **Constante** | Arquitetura A, modelo, prompt-base, tools e casos adversariais |
| **Permite concluir** | Com que frequência a instrução falha sob pressão |
| **Custo** | 50 execuções |
| **Valor** | **Alto** — o falso agir é o erro de maior custo do sistema |

> **Nota sobre o conteúdo empírico.** P2.1 (zero efeito externo após o gateway) é verdadeira por
> construção e não é descoberta. O conteúdo empírico está em P2.2 — **quanto** a instrução falha.
> O braço `prompt_only` usa um provider dry-run e nunca chama uma ação externa real.

---

### E-S2 · Política de confirmação em execução automatizada 🔵 CANDIDATO

| | |
| :--- | :--- |
| **Comparação** | Auto-confirmar **vs** auto-recusar quando não há humano |
| **Constante** | Arquitetura, modelo, casos |
| **Permite concluir** | Se a política de confirmação altera o comportamento antes da confirmação |
| **Custo** | +75 execuções |
| **Valor** | **Médio** — controla um artefato do próprio desenho de avaliação |

---

## 7. Catálogo — Metodologia de avaliação

> O TAP autoriza explicitamente hipóteses sobre **como avaliar**, não apenas sobre o agente:
> *"A hipótese pode tratar do agente em si ou de como ele deve ser avaliado."*

### E-V1 · Concordância juiz × humano 🟢 DECLARADO — obrigatório

| | |
| :--- | :--- |
| **Comparação** | Vereditos do LLM-juiz **vs** rotulação humana cega, em amostra |
| **Custo** | 40 rotulações manuais: 10 de calibração + 30 de validação, sem sobreposição |
| **Permite concluir** | Se as métricas de rubrica são confiáveis |
| **Valor** | **Alto** — sem isso, toda métrica de rubrica tem erro desconhecido |

---

### E-V2 · Rubrica binária vs escala Likert 🔵 CANDIDATO ⭐

| | |
| :--- | :--- |
| **Comparação** | 8 critérios binários **vs** nota holística de 1 a 5 |
| **Constante** | Mesmas execuções, mesmo juiz |
| **Permite concluir** | Se a decomposição binária realmente aumenta a concordância com humano |
| **Custo** | +594 julgamentos (não são execuções — muito mais barato) |
| **Valor** | **Alto** — testa uma decisão metodológica do próprio projeto, com custo baixo |

> **Melhor relação custo-benefício do catálogo.** Não exige reexecutar o agente: aplica dois juízes
> aos traces que já existem. E responde uma pergunta sobre avaliação de LLMs que vale além deste
> domínio.

---

### E-V3 · Juiz único vs painel de três 🔵 CANDIDATO

| | |
| :--- | :--- |
| **Comparação** | Um juiz **vs** três juízes com voto majoritário |
| **Custo** | +1.188 julgamentos |
| **Permite concluir** | Se a redundância de juízes melhora a concordância com humano |
| **Valor** | **Médio** — caro em cota de julgamento; ganho previsível |

---

### E-V4 · Casos base vs casos gerados 🔵 CANDIDATO

| | |
| :--- | :--- |
| **Comparação** | Os 17 chamados originais **vs** variantes geradas por combinação |
| **Permite concluir** | Se casos sintéticos reproduzem a dificuldade dos originais |
| **Custo** | +272 execuções |
| **Valor** | **Médio-alto** — valida a ampliação do dataset (RF21) antes de confiar nela |

> Sem este experimento, ampliar o dataset é um ato de fé: não se sabe se os casos gerados são
> genuinamente difíceis ou trivialmente resolvíveis.

---

## 8. Custo × valor — visão consolidada

```
   ALTO │  E-T2 ⭐        E-A3         E-A1 (H1)
        │  E-V2 ⭐        E-T1 (H3)    E-A2 (H4)
 V      │  E-V1           E-S1 (H2)
 A      │
 L  MÉD │  E-S2           E-P1         E-P2
 O      │                 E-V4         E-V3
 R      │
   BAIXO│  E-T3           E-A4         E-A5
        │                 E-P3
        └────────────────────────────────────────
            BAIXO         MÉDIO        ALTO
                        CUSTO
```

**Quadrante superior esquerdo** — alto valor, baixo custo. É onde estão as oportunidades ainda não
aproveitadas: **E-T2** e **E-V2**.

---

## 9. Portfólio

### 9.1 Declarado — núcleo e máximo condicional

| Exp. | Hipótese | Execuções | Julgamentos |
| :--- | :--- | ---: | ---: |
| E-A1 | H1 — arquitetura | 544 | 544 |
| E-S1 | H2 — segurança | 50 | 50 |
| | **Núcleo obrigatório** | **594** | **594** |
| E-A2 | H4 — heterogeneidade de modelo, condicional | +272 | +272 |
| E-T1 | H3 — overlay (amostra), condicional | +130 | +130 |
| E-V1 | Meta-avaliação | — | 40 humanas |
| | **Máximo condicional** | **996** | **996** |

**Viabilidade:** calculada depois do piloto como `RPD / p95(chamadas por execução)` para cada braço.
E3 e E4 só são habilitados se o orçamento medido preservar a conclusão do núcleo e a análise.

### 9.2 Extensões, em ordem de prioridade

Executar **apenas** se o cronograma real permitir, e sempre com predições escritas antes:

| Ordem | Exp. | Custo | Por que primeiro |
| ---: | :--- | ---: | :--- |
| 1 | **E-V2** | +594 julgamentos | Não exige reexecutar o agente. Custo mais baixo do catálogo |
| 2 | **E-T2** | +272 execuções | Resolve L11 — converte uma limitação declarada em achado |
| 3 | **E-A6** | +~300 execuções | Ataca o modo de falha central do domínio; estende a defesa em camadas |
| 4 | **E-A3** | +272 execuções | Valida o ADR-05, hoje uma decisão não demonstrada |
| 5 | E-V4 | +272 execuções | Valida a ampliação do dataset antes de confiar nela |
| 6 | E-P1 | +272 execuções | Separa efeito de prompt de efeito de arquitetura |

### 9.3 Descartados — e por quê

| Exp. | Motivo |
| :--- | :--- |
| E-A5 topologia | Expande o espaço sem responder pergunta pendente |
| E-P3 temperatura | Em tarefa com resposta correta, temperatura 0 é a escolha esperada |
| E-T3 resource vs tool | Elegante, mas o efeito previsível é pequeno |
| E-A4 saída estruturada | Interessa à metodologia, mas não altera conclusão sobre o agente |
| E-V3 painel de juízes | Custo alto em cota de julgamento; ganho previsível |

> Registrar o descarte importa tanto quanto registrar a escolha. Omitir faz parecer que a opção não
> foi considerada.

---

## 10. Proteção contra comparações múltiplas

Com 3 arquiteturas, 8 seeds, 16 métricas e 4 hipóteses, o número de comparações possíveis é grande o
suficiente para que **algo pareça significativo por acaso**. Isso é matemática, não azar.

Três regras que tornam o resultado defensável:

**① Predições escritas antes.** Toda hipótese declara direção esperada antes da execução —
P1.1–P1.4, P2.1–P2.2, P3.1–P3.3, P4.1–P4.3 já estão em
[`07-plano-experimental.md`](./07-plano-experimental.md). Nenhuma predição é adicionada depois de
ver os dados.

**② Métrica primária declarada por hipótese.** Cada hipótese tem **uma** métrica que decide o
veredito. As demais são secundárias e reportadas como exploratórias.

| Hipótese | Métrica primária |
| :--- | :--- |
| H1 | M4 × intensidade de degradação (dose-resposta) |
| H2 | M10 — tentativa insegura antes do gateway |
| H3 | M7 — afirmação vedada |
| H4 | M4 — acerto de decisão, a custo reduzido |

**③ Reportar tudo.** Todas as predições aparecem no relatório final, confirmadas ou não. Uma
predição refutada é resultado; uma predição omitida é viés.

> ❌ *"A multi com overlay enriquecido deu 12% melhor no seed 3."*
> ✅ *"Prevemos que a vantagem da multi cresceria com a degradação (P1.1) — confirmado.
>    Prevemos maior perda no handoff (P1.4) — **não confirmado**: o handoff tipado preservou a
>    evidência melhor do que o esperado."*

---

## 11. Registro de decisões

| Data | Decisão | Motivo |
| :--- | :--- | :--- |
| 24/08 | E-A1, E-S1, E-T1, E-V1 no núcleo | Cobrem as hipóteses declaradas originalmente |
| 24/08 | E-A2 (H4) promovido a declarado condicional | Executar apenas se o piloto confirmar cota separada e prazo para +272 execuções |
| 24/08 | E-T2 e E-V2 identificados como melhores candidatos | Alto valor, custo baixo; E-T2 resolve L11 |
| 24/08 | **E-A6** (verificação adversarial) registrado como candidato prioritário | Encaixe direto no modo de falha do domínio; entra se houver folga, não agora |
| 24/08 | E-A5, E-P3, E-T3, E-A4, E-V3 descartados | Custo desproporcional ao que acrescentam |
