# 01 — Documento de Visão

| | |
| :--- | :--- |
| **Projeto** | Engenharia e Avaliação de Agentes Industriais |
| **Parceiro** | TRACTIAN |
| **Instituição** | Inteli |
| **Formato** | Individual |
| **Autor** | Isaac Nicolas Alves da Silva |
| **Período** | 13/08/2026 – 08/09/2026 |
| **Versão** | 1.0 |

---

## 1. Contexto do negócio

A TRACTIAN atua em **monitoramento de condição** (*condition monitoring*) de ativos industriais e
gestão de manutenção. Sensores instalados em máquinas coletam vibração continuamente; modelos
processam esses sinais e emitem **insights** — diagnósticos automáticos de falha incipiente, antes
que o equipamento quebre.

Entre o insight e a decisão de manutenção existe um time de suporte técnico. Quando um cliente
questiona um diagnóstico, reclama de um alerta que não veio, ou pede uma ação na plataforma, um
analista precisa reconstruir a investigação: consultar o cadastro do ativo, o histórico de análises,
o estado do baseline, a qualidade do sinal, a cobertura do modelo — e só então responder, agir ou
encaminhar.

Essa investigação é **estruturada, repetitiva e intensiva em consulta**. É exatamente o perfil de
trabalho que um agente de IA com ferramentas pode organizar.

## 2. Problema

> Uma solicitação de suporte técnico em monitoramento de condição exige o cruzamento de múltiplas
> fontes — ativo, análises, sinais, baseline, qualidade de dados, cobertura de modelo — antes de
> qualquer conclusão. Fazer isso manualmente é lento; fazer isso com um LLM sem disciplina de
> evidência produz respostas confiantes e erradas, que num contexto industrial se traduzem em
> intervenção desnecessária ou, pior, em falha não detectada.

O problema deste projeto **não é** conectar um LLM a uma API. É construir um agente cujo
comportamento seja **confiável o suficiente** para operar sobre um sistema industrial, e —
igualmente importante — **provar** essa confiabilidade com método.

### 2.1 Por que é difícil

Quatro dificuldades específicas do domínio, todas materializadas no ambiente fornecido:

**① O conhecimento genérico do modelo está errado aqui.** Um LLM treinado em literatura de
manutenção "sabe" que a norma ISO 10816 define limiares de vibração por classe de máquina. Neste
domínio isso é **falso**: o limiar de alarme deriva do baseline aprendido do próprio ativo
(`reference + tolerance`). O agente precisa suprimir seu prior e ancorar na evidência da API.

**② A evidência tem pré-condições.** Um insight só é confiável se as condições em que ele foi gerado
eram válidas. Um diagnóstico de desbalanceamento produzido com o baseline em `invalidated` é
suspeito — mas o insight em si não diz isso de forma óbvia. O agente precisa **verificar antes de
confiar**.

**③ A informação frequentemente é incompleta.** A API é deliberadamente probabilística: retorna
dados completos, parciais, inconclusivos, conflitantes ou indisponíveis. O comportamento correto
diante de uma lacuna é **declará-la**, não preenchê-la por inferência.

**④ Algumas ações são irreversíveis.** Reprocessar uma análise, alterar configuração técnica ou
solicitar retreinamento têm impacto real e exigem justificativa e permissão. Agir quando se deveria
apenas orientar é o erro mais caro do sistema.

## 3. Pergunta norteadora

> Como construir e avaliar agentes de IA capazes de usar sistemas industriais com precisão,
> interpretar evidências e executar ações adequadas ao contexto?

## 4. Solução proposta

Um **sistema de suporte técnico industrial em nível de produto** — recebe tickets continuamente,
investiga com agentes de IA integrados à API da TRACTIAN por uma camada de tools, e decide entre orientar,
agir ou escalar — acompanhado do **arnês de avaliação** que mede sua confiabilidade.

> **O enquadramento define tudo o que segue.** Este não é um experimento acadêmico com 17 casos.
> É um sistema de atendimento, e os 17 chamados fornecidos pela TRACTIAN são a sua **suíte de
> regressão** — o mesmo worker que processa um ticket de cliente processa um caso da suíte, pelo
> mesmo caminho de código. É isso que garante que a avaliação mede o comportamento real do produto,
> e não um caminho paralelo construído para ser medido.

### 4.0 Por que produto, e por que isso fortalece o experimento

As quatro hipóteses deixam de ser perguntas acadêmicas e passam a ser **decisões que qualquer um que
coloque um agente em produção precisa tomar**:

| Hipótese | Como decisão de produto |
| :--- | :--- |
| **H1** mono vs multi-agente | *Que arquitetura eu coloco em produção?* |
| **H2** garantia estrutural vs instrução | *Como bloqueio uma ação indevida antes de qualquer efeito externo?* |
| **H3** overlay semântico | *Quanto a descrição das ferramentas muda o comportamento?* |
| **H4** modelo por papel | *Quanto economizo baixando o modelo nos papéis fáceis?* |

Responder isso com evidência, e não com opinião, é o diferencial declarado do projeto.

A solução tem cinco componentes:

| # | Componente | Descrição |
| :-- | :--- | :--- |
| **1** | **Camada de ferramentas** | Biblioteca em duas camadas: núcleo genérico que converte contrato OpenAPI em tools e *overlay* declarativo que injeta semântica de domínio. Um envelope MCP é opcional e não participa do caminho padrão. |
| **2** | **Sistema de agentes** | Grafo com orquestrador e três agentes especializados — Contextualizador, Investigador e Executor — espelhando as três modalidades de atendimento do enunciado. A separação garante, por construção, que agentes de investigação não possam executar ações. |
| **3** | **Framework de avaliação** | Golden dataset derivado e ampliado a partir dos 17 chamados; runner durável e paralelo; métricas determinísticas de trajetória, argumentos e decisão; e rubrica binária avaliada por LLM-as-judge com meta-avaliação contra rotulação humana. |
| **4** | **Ingestão e fila de atendimento** | Ponto de entrada para tickets (`POST /tickets`), fila durável com prioridade derivada da criticidade do ativo, e sessão multi-turno por ticket. O mesmo worker atende ticket de cliente e caso da suíte. |
| **5** | **Interface web** | Aplicação React com **console de atendimento**, chat com o agente, inspetor de trajetória passo a passo em streaming, e dashboard de avaliação. |

### 4.1 Contexto de uso declarado

O sistema opera como **plataforma de atendimento de suporte técnico**. Tickets chegam continuamente
por API ou pela interface, entram numa fila priorizada, e são atendidos por agentes que investigam de
forma autônoma e produzem uma resolução — orientação, ação executada ou escalonamento — sempre com
trajetória auditável. Ações de impacto exigem confirmação explícita.

O TAP admite os três modos de operação — *"atendimento direto, como copiloto ou em fluxos autônomos
com escopo definido"*. Este projeto declara **fluxo autônomo com escopo definido**: o agente conduz
o atendimento sozinho até a resolução, com escalonamento humano como saída explícita.

### 4.2 Hipótese central

> **A arquitetura multi-agente especializada apresentará maior acerto que a mono conforme a
> degradação aumenta, ao custo potencial de perda de informação no handoff.**

O contraste principal compara **arquiteturas completas**. Ele não atribui sozinho eventual diferença
exclusivamente ao isolamento de contexto, porque catálogo de tools, quantidade de chamadas e
handoffs também mudam. Experimentos de mecanismo são extensões separadas.

O detalhamento das hipóteses, variáveis e método está em
[`07-plano-experimental.md`](./07-plano-experimental.md).

## 5. Escopo

### 5.1 Dentro do escopo

- **Ingestão contínua de tickets** por API e interface, com fila durável priorizada
- **Sessão multi-turno** por ticket — o cliente responde, o agente continua com contexto
- **Console de atendimento** — fila, tickets em curso, resoluções
- Camada MCP genérica sobre contrato OpenAPI, com overlay de domínio para a API TRACTIAN
- Duas arquiteturas de agente comparáveis: mono-agente ReAct e multi-agente especializado
- Cobertura dos 17 chamados nas três modalidades (Contextualizar, Investigar, Executar)
- Decisão explícita e justificada entre **orientar / agir / escalar**
- Guardrail estrutural em ações de impacto (separação de autoridade + confirmação)
- Trace estruturado e completo de toda execução
- Golden dataset formalizado a partir do gabarito, com ampliação combinatória
- Suíte de avaliação: métricas determinísticas + rubrica binária com LLM-as-judge
- Meta-avaliação do juiz contra rotulação humana em amostra
- Interface React: atendimento, inspeção de trace, dashboard de resultados

### 5.2 Fora do escopo

| Item | Justificativa |
| :--- | :--- |
| Modificar a API da TRACTIAN | Material fornecido, tratado como sistema externo imutável |
| Treinar ou ajustar modelos de vibração | O domínio é simulado; os modelos são representados por metadados |
| Fine-tuning de LLM | Inviável no prazo e desnecessário para a hipótese |
| Autenticação e multi-tenancy | O sistema é de produto, mas roda em ambiente controlado; identidade vem do header `x-user-id`, como a API fornecida define |
| Ingestão por Slack, e-mail ou webhook externo | A porta `POST /tickets` existe; cada origem é um adaptador fino. Registrado como evolução (ADR-12) |
| Escalonamento notificando sistemas externos | Hoje o escalonamento chama o endpoint da API fornecida. Notificar Slack ou abrir item no Jira passaria pela porta `ToolProvider`, sem reforma. Evolução (ADR-12) |
| Painel administrativo e gestão de SLA | Fora do que a rubrica avalia; o custo não se justifica no prazo |
| Deploy em nuvem | Execução local via Compose |
| Dados reais de clientes | O material é sintético por design |
| Ingestão de sinal bruto de sensor | A API já entrega sinais em formato didático |

> **Fronteira de confiança.** Sem autenticação, `x-user-id`, `company_id` e `asset_id` são entradas
> confiáveis apenas no ambiente acadêmico controlado. A demonstração não deve ser descrita como
> pronta para produção nem exposta em rede não confiável. Em produção, identidade autenticada,
> vínculo usuário–empresa, autorização no backend, proteção de segredos, redaction e retenção de
> traces são pré-requisitos — não extras cosméticos.

## 6. Restrições

| ID | Restrição | Origem |
| :--- | :--- | :--- |
| RES-01 | Prazo de entrega: 08/09/2026 | Cronograma acadêmico |
| RES-02 | Projeto individual | Formato definido no TAP |
| RES-03 | Modelos abertos ou roteadores gratuitos | Referência de viabilidade do TAP |
| RES-04 | O gabarito não pode entrar no contexto do agente | Integridade da avaliação |
| RES-05 | Execução local, sem infraestrutura paga | Restrição de custo |
| RES-06 | Rate limits da free tier do provedor de LLM | Limita volume de execuções |

## 7. Premissas

- A API fornecida está funcional e estável durante todo o desenvolvimento
- O parâmetro `seed` torna o comportamento da API determinístico e reprodutível
- Os dados sintéticos são internamente consistentes: o gabarito é sustentado pelos dados
- O gabarito `eval/expected-paths.json` representa a trajetória de investigação correta
- O provedor de LLM mantém disponibilidade suficiente para as execuções planejadas

## 8. Riscos

| ID | Risco | Impacto | Prob. | Mitigação |
| :--- | :--- | :--- | :--- | :--- |
| RSC-01 | Rate limit do provedor interrompe execuções longas | Alto | Alta | Runner com checkpoint; retomada sem reexecutar casos concluídos (RNF03) |
| RSC-02 | Escopo amplo demais para 15 dias úteis | Alto | Alta | Priorização declarada; entregáveis marcados como núcleo vs. extensão |
| RSC-03 | Modelo aberto com tool calling instável | Alto | Média | Avaliar 2–3 modelos na primeira semana; fixar o mais estável como baseline |
| RSC-04 | LLM-as-judge com baixa concordância humana | Médio | Média | Meta-avaliação em amostra; fallback para métricas determinísticas |
| RSC-05 | Front React consome tempo do núcleo experimental | Médio | Média | Backend e contratos de API definidos antes do front; front construído por incrementos |
| RSC-06 | Ampliação do golden dataset gera casos sem resposta correta verificável | Médio | Média | Geração combinatória apenas sobre dimensões cuja resposta é derivável por construção |

## 9. Critérios de sucesso

O projeto é bem-sucedido se:

1. O agente executa os 17 chamados de ponta a ponta com trajetória auditável
2. A avaliação produz métricas reprodutíveis sobre as duas arquiteturas
3. A hipótese central é sustentada **ou refutada** com evidência quantitativa
4. As limitações do experimento estão explicitamente registradas
5. Um terceiro consegue reproduzir a execução completa a partir do README

> O critério 3 é indiferente à direção do resultado. Refutar a hipótese com método sólido é um
> desfecho tão válido quanto confirmá-la.

## 10. Documentos relacionados

| Doc | Conteúdo |
| :--- | :--- |
| [`02-personas-user-stories.md`](./02-personas-user-stories.md) | Perfis de usuário e histórias |
| [`03-requisitos.md`](./03-requisitos.md) | RF e RNF |
| [`04-casos-de-uso.md`](./04-casos-de-uso.md) | Casos de uso UML |
| [`05-arquitetura.md`](./05-arquitetura.md) | C4, grafo de agentes, stack |
| [`06-matriz-rastreabilidade.md`](./06-matriz-rastreabilidade.md) | RF → UC → cenário → métrica |
| [`07-plano-experimental.md`](./07-plano-experimental.md) | Hipóteses, método, rubricas |
| [`08-glossario.md`](./08-glossario.md) | Glossário de domínio |
