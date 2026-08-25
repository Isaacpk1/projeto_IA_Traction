# 08 — Glossário

> Duas seções: **domínio industrial** (o vocabulário da manutenção preditiva, sem o qual os retornos
> da API são ilegíveis) e **engenharia de agentes** (o vocabulário da solução). Termos marcados ⚠️
> são aqueles cujo entendimento incorreto produz erro de diagnóstico.

---

# Parte I — Domínio industrial

## Sinais e medição

### RMS *(Root Mean Square)* ⚠️
Raiz do valor quadrático médio. Resume um sinal oscilante de vibração em **um único número** que
representa a energia da vibração, expresso em **mm/s**.

$$\text{RMS} = \sqrt{\frac{1}{n}\sum_{i=1}^{n} x_i^2}$$

A elevação ao quadrado elimina o sinal negativo — a média simples de uma oscilação em torno de zero
resultaria em zero, sem informação. É o principal indicador de tendência do ativo, coletado
periodicamente.

*Na API:* `GET /assets/{id}/rms` → série temporal `{ts, value}`.

---

### Espectro / FFT *(Fast Fourier Transform)*
Decomposição do sinal de vibração em suas frequências componentes. Enquanto o RMS diz **quanto** a
máquina vibra, o espectro diz **em que frequências** — e é a frequência que identifica a falha.

*Na API:* `GET /assets/{id}/spectrum` → `{peaks: [{freq_hz, amplitude_mm_s, note}], bands_missing}`.

O campo `bands_missing` indica faixas de frequência ausentes da coleta. Se a banda ausente for
justamente a diagnóstica, a inferência é impossível — e declarar isso é o comportamento correto.

---

### Frequências características ⚠️
Cada modo de falha produz energia numa frequência previsível, derivada da geometria e da rotação do
ativo. É o que torna o espectro diagnóstico e não apenas descritivo.

| Assinatura | Falha indicada |
| :--- | :--- |
| **1×** rotação | Desbalanceamento |
| **2×** rotação | Desalinhamento |
| **BPFO** | Falha na pista externa do rolamento |
| **BPFI** | Falha na pista interna do rolamento |
| **BSF** | Falha no elemento rolante (esfera/rolo) |
| **FTF** | Falha na gaiola do rolamento |
| **2×** frequência de linha | Falha de origem elétrica |
| Subharmônicos | Folga mecânica (*looseness*) |

**"1×"** significa uma vez a frequência de rotação: um ativo a 1780 rpm gira a 29,67 Hz, logo seu 1×
está em ~29,67 Hz e seu 2× em ~59,3 Hz.

*Na API:* as frequências de rolamento estão em `AssetConfig.bearing_specs` (`bpfo_hz`, `bpfi_hz`,
`bsf_hz`, `ftf_hz`); a frequência de linha em `line_frequency_hz`.

---

### Qualidade e frescor dos dados
Três medidas que determinam se o sinal é utilizável:

| Campo | Significado |
| :--- | :--- |
| `completeness` | Proporção de amostras efetivamente coletadas (0–1) |
| `snr_db` | Relação sinal-ruído em decibéis — quanto do sinal é informação e quanto é ruído |
| `freshness_minutes` | Minutos desde a última amostra válida |
| `staleness_flag` | Marcador de obsolescência |

⚠️ **Estes valores só têm significado quando comparados aos requisitos do modelo**
(`min_completeness`, `min_snr_db`). "SNR de 12 dB" não é bom nem ruim isoladamente.

*Na API:* `GET /assets/{id}/data-quality`.

---

## Baseline e detecção

### Baseline ⚠️ *(conceito central)*
O **estado normal aprendido do próprio ativo**, construído a partir do histórico dele quando
saudável. Não é um valor de norma nem uma referência de classe: é específico daquele equipamento.

*Na API:* `GET /assets/{id}/baseline` → `{state, detection_mode, learnable, features, ...}`, onde
`features` é uma lista de `{feature, reference, tolerance}`.

---

### Estados do baseline ⚠️

| Estado | Significado | Consequência |
| :--- | :--- | :--- |
| `learning` | Histórico insuficiente para estabelecer a referência | **Não há limiar confiável.** Detecção por desvio é impossível |
| `established` | Referência aprendida e utilizável | Detecção por desvio válida |
| `invalidated` | Manutenção ou mudança de configuração alterou o "normal" | Referência anterior não vale mais; exige reaprendizado. **Insights gerados neste estado são suspeitos** |

O campo `invalidation_reason` distingue `maintenance_intervention` de `config_change`.

---

### Limiar de alarme de RMS ⚠️ *(a armadilha do domínio)*
O valor de RMS acima do qual se gera alerta. **Deriva do baseline do próprio ativo:**

$$\text{alarm\_threshold} = \text{reference} + \text{tolerance}$$

> ⛔ **O limiar NÃO vem de norma ISO 10816/20816 nem de tabela por classe de máquina.**

Essa é a confusão mais provável e mais custosa. Um modelo de linguagem treinado em literatura de
manutenção "sabe" que a ISO 10816 define zonas de severidade por classe — e essa é justamente a
resposta errada aqui.

**Por quê.** A norma é genérica: vale para qualquer motor de 15 kW do mundo. Mas um compressor antigo
pode operar saudável a 5 mm/s por anos, enquanto um motor de precisão pode estar em falha a 1,5 mm/s.
A tabela genérica desconhece *aquela* máquina; o baseline a conhece.

*Instrumentado por:* RF07 · *Medido por:* M7 · *Testado em:* TKT-CTX-03

---

### Modo de detecção ⚠️

| Modo | Mecanismo | Exige baseline? | Exemplos |
| :--- | :--- | :--- | :--- |
| `baseline` | **Por desvio** — compara o estado atual com o normal aprendido | **Sim**, `established` | Desbalanceamento, desalinhamento, falha de rolamento, falha elétrica |
| `symptom` | **Sintomática** — a presença da assinatura já indica a falha | **Não** | Lubrificação |

**A distinção que separa dois casos aparentemente idênticos:**

Se o cliente pergunta *"por que não detectaram falha de rolamento?"* e o baseline está em `learning`
→ a resposta é que detecção por desvio era tecnicamente impossível.

Se o cliente pergunta *"como detectaram falta de lubrificação sem histórico?"* no mesmo ativo →
"baseline em learning" **não é** argumento válido: detecção sintomática independe de baseline.

Um agente que aplica a regra de pré-condição mecanicamente, sem checar o modo, erra o segundo caso.

*Instrumentado por:* RF05, RF06 · *Testado em:* TKT-INV-04 (desvio) e TKT-INV-11b (sintomática)

---

### `learnable` e `can_learn_baseline`
Indicam se o modelo consegue aprender baseline para aquele ativo ou subtipo. Com `false`, existe
apenas detecção sintomática — independentemente de o tipo estar formalmente "suportado".

⚠️ **"Tipo suportado" ≠ "consegue aprender baseline".** É a distinção que TKT-INV-11 testa.

---

## Análises e modelos

### Análise / Insight
Diagnóstico automático emitido pelo modelo.

| Campo | Conteúdo |
| :--- | :--- |
| `type` | Tipo de falha detectada |
| `severity` | `none` · `low` · `medium` · `high` · `critical` |
| `confidence` | 0,0 – 1,0 |
| `detection_mode` | `baseline` · `symptom` |
| `baseline_state_at_detection` ⚠️ | Estado do baseline **no momento da detecção** |
| `evidence` | Métricas que sustentam o diagnóstico |
| `limitations` | Limitações declaradas pelo próprio modelo |
| `status` | `current` · `stale` · `pending` · `inconclusive` |

⚠️ **`baseline_state_at_detection` é o campo mais importante da análise.** Uma confiança de 0,87
gerada sobre baseline `invalidated` não é uma confiança de 0,87 — é um número calculado contra uma
referência inválida.

---

### Estados da análise

| Status | Significado |
| :--- | :--- |
| `current` | Vigente e válida |
| `stale` | Desatualizada — tipicamente porque houve intervenção posterior |
| `pending` | Aguardando processamento |
| `inconclusive` | Processada sem conclusão |

---

### Estado de processamento do modelo ⚠️
`idle` · `running` · `pending` · `delayed` · `failed`

**Distinção crítica:** um modelo em `delayed` significa **"não processou ainda"** — que é diferente
de **"processou e não encontrou falha"**. Confundir os dois faz o agente tranquilizar o cliente
quando deveria explicar um atraso operacional. É a essência de TKT-INV-05.

---

### Cobertura do modelo
Lista de `{machine_type, supported, can_learn_baseline, note}`, mais os requisitos mínimos de
qualidade (`min_completeness`, `min_snr_db`, `min_rotation_rpm`) que o sinal deve satisfazer para
que a inferência seja válida.

---

## Ativos e organização

### Ativo *(asset)*
Equipamento monitorado. Possui `machine_type`, `rotation_rpm`, `bearing_specs`, `line_frequency_hz`
e criticidade.

### Ponto *(point)*
Posição física de medição no ativo. Um ativo pode ter vários — por exemplo, lado acoplado e lado
oposto ao acoplamento. Baseline, RMS e espectro são por ponto, não por ativo.

### Criticidade
Importância do ativo para a produção. Governa priorização de atendimento. Alterá-la é ação de
impacto (`action_high`).

---

## Modos de falha

| Falha | Assinatura espectral | Modo de detecção |
| :--- | :--- | :--- |
| **Desbalanceamento** | Pico dominante em 1× | `baseline` |
| **Desalinhamento** | Pico em 2×, às vezes 3× | `baseline` |
| **Falha de rolamento** | BPFO / BPFI / BSF / FTF | `baseline` |
| **Falha elétrica** | 2× frequência de linha | `baseline` |
| **Folga** *(looseness)* | Subharmônicos e múltiplos | `baseline` |
| **Lubrificação** | Alta frequência, atrito/choque | `symptom` |

---

# Parte II — Engenharia de agentes

## Padrões de agente

### ReAct *(Reasoning + Acting)*
Padrão em que o modelo **intercala** raciocínio e ação, em vez de fazer só um dos dois.

```
Thought → Action → Observation → Thought → Action → Observation → ... → Resposta
```

Resolve duas falhas conhecidas: raciocínio puro (*Chain of Thought*) produz conclusões desconectadas
de evidência real; ação pura produz coleta sem plano. A alternância faz cada observação corrigir o
raciocínio seguinte.

Nas APIs modernas de *tool calling*, os três elementos são nativos: **Thought** é o texto de
raciocínio, **Action** é o `tool_call` estruturado, **Observation** é a mensagem de resultado.

### Política de parada
Critério que encerra o loop: suficiência de evidência, limite de passos, ou orçamento esgotado. O
motivo é registrado em `stop_reason`. Ausência de política produz loops infinitos; política frouxa
produz parada prematura — concluir com evidência insuficiente.

### Trajetória
A sequência de chamadas que o agente efetuou. É o objeto primário de avaliação: **como** o agente
chegou à resposta importa tanto quanto a resposta.

### Trace
Registro estruturado completo da execução — por passo: agente, raciocínio, tool, argumentos,
retorno, erro, latência. Neste projeto o trace **não é log**: é o dado experimental.

---

## Multi-agente

### Handoff ⚠️
Transferência de controle e informação entre agentes. Cada handoff é um ponto de **potencial perda
de informação**: se a transferência for textual, o agente receptor decide sobre um resumo, não sobre
os dados.

Neste projeto os handoffs são **objetos tipados** com evidência ancorada em passos do trace,
justamente para tornar a perda mensurável (M14) em vez de invisível.

### Isolamento de contexto
Dar a cada agente apenas a informação e as ferramentas necessárias ao seu papel. Reduz deriva de
atenção e espaço de escolha de função — ao custo de introduzir handoffs.

### Separação de autoridade
Distribuir ferramentas entre agentes de modo que capacidades de impacto sejam estruturalmente
inacessíveis a agentes de investigação. Diferente de instruir o agente a se conter: a ferramenta
não existe no schema dele.

---

## MCP *(Model Context Protocol)*

### MCP
Protocolo aberto que padroniza a comunicação entre aplicações de IA e sistemas externos. Baseado em
**JSON-RPC 2.0**.

⚠️ **O modelo de linguagem nunca vê MCP.** A conversa MCP ocorre entre a aplicação e o servidor de
ferramentas; a aplicação traduz o catálogo obtido para o formato de tool calling que o modelo
entende.

### Host · Client · Server

| Papel | Função |
| :--- | :--- |
| **Host** | A aplicação. Conversa com o LLM e contém o client |
| **Client** | Mantém conexão 1:1 com um servidor |
| **Server** | Expõe capacidades. Neste projeto, envolve a API TRACTIAN |

### Handshake
Troca inicial em que client e servidor negociam versão de protocolo e capacidades, antes de qualquer
uso: `initialize` → resposta → notificação `initialized`. Impede que um lado assuma capacidades que
o outro não possui.

### Transporte

| Modo | Uso |
| :--- | :--- |
| **stdio** | Servidor como subprocesso; comunicação por entrada/saída padrão. Local, sem rede. Usado neste projeto |
| **Streamable HTTP** | Servidor remoto com endpoint HTTP e streaming opcional. Exige autenticação |

### Primitivas de servidor

| Primitiva | Controlada por | Uso |
| :--- | :--- | :--- |
| **Tools** | o modelo decide invocar | Os 18 endpoints da API |
| **Resources** | a aplicação injeta | Dados de leitura endereçáveis por URI |
| **Prompts** | o usuário invoca | Templates de fluxo |

### Primitivas de cliente

| Primitiva | Mecanismo | Uso neste projeto |
| :--- | :--- | :--- |
| **Sampling** | O servidor pede ao host que execute uma inferência de LLM | **Não utilizado** — inferência dentro da ferramenta contaminaria a medição do comportamento do agente |
| **Elicitation** | O servidor pede informação adicional ao usuário durante a execução | **Não utilizado no núcleo** — exigiria humano respondendo em avaliação automatizada. Registrado como evolução |

### Tool
Nome + descrição em linguagem natural + JSON Schema de argumentos. A **descrição é o que determina
se o modelo escolhe a ferramenta certa** — daí a existência do overlay.

### Overlay ⚠️
Camada declarativa aplicada **sobre** um documento base sem modificá-lo. Neste projeto, um arquivo
que enriquece cada tool gerada do contrato OpenAPI com semântica de domínio, nível de impacto
(`tier`), exigência de confirmação e permissão requerida.

Mantém o núcleo genérico e portável (RNF06) enquanto entrega ao modelo a informação de domínio que o
contrato técnico não carrega.

### Tier
Classificação de impacto da ferramenta: `read` (consulta) ou `impact` (ação com efeito). Uma
declaração que alimenta três garantias: composição de tools por agente (RF12), exigência de
confirmação (RF14) e validação de permissão (RF13).

---

## Avaliação

### Golden dataset
Conjunto de casos com resposta correta conhecida. Aqui: entrada, trajetória esperada, decisão
esperada, evidências obrigatórias, afirmações vedadas e pré-condições exigidas.

### Gabarito ⚠️
O material de referência que define a resposta correta. **Nunca pode entrar no contexto do agente**
(RNF02): com acesso à resposta, o agente deixa de raciocinar e passa a procurá-la, invalidando a
medição.

### Ablação
Método experimental que remove ou altera **um** componente por vez, mantendo tudo o mais constante,
para atribuir causalmente a diferença observada àquele componente.

### LLM-as-judge
Uso de um modelo de linguagem para avaliar saídas segundo critérios definidos. Exige controles:
modelo distinto do avaliado (viés de auto-preferência), ordem randomizada (viés de posição) e
critérios binários (viés de verbosidade).

### Rubrica binária
Conjunto de critérios de sim/não, em vez de escala numérica. Escalas produzem concentração nos
valores centrais e baixa reprodutibilidade; critérios binários são auditáveis — identificam **qual**
dimensão falhou.

### Meta-avaliação
Avaliação do próprio avaliador: comparar os vereditos do juiz com rotulação humana em amostra e
reportar a concordância. Sem ela, as métricas de rubrica têm erro desconhecido.

### Kappa de Cohen
Medida de concordância entre dois avaliadores que desconta a concordância esperada por acaso.
Interpretação: < 0,40 fraca · 0,40–0,60 moderada · 0,60–0,80 substancial · > 0,80 quase perfeita.

### Ancoragem de evidência *(grounding)*
Verificação de que toda afirmação do agente corresponde a um valor efetivamente presente em algum
retorno registrado no trace. Torna a detecção de alucinação determinística, e não uma leitura
subjetiva do texto.

### Falso "agir" ⚠️
Executar uma ação de impacto quando o comportamento correto seria orientar ou escalar. **É o erro de
maior custo do sistema** — mais caro que uma explicação incorreta, porque produz efeito real na
plataforma do cliente.

### Estabilidade
Grau em que execuções idênticas produzem o mesmo resultado. Neste projeto há **duas fontes de
variação** que precisam ser separadas: o não-determinismo do modelo e o comportamento probabilístico
da API — esta última controlável via `seed`.

---

## Modos de comportamento da API

| Modo | Significado | Comportamento correto do agente |
| :--- | :--- | :--- |
| `complete` | Retorno íntegro | Prosseguir normalmente |
| `partial` | Informação incompleta | Declarar o que falta; não inferir sobre a lacuna |
| `inconclusive` | Sem conclusão | Não substituir por inferência própria |
| `conflict` | Fontes divergentes | Apresentar ambas; buscar desempate físico; se não houver, declarar irresolvido |
| `unavailable` | Recurso indisponível | Registrar como fato da investigação — a ausência é frequentemente a resposta |
| `stale` | Dado obsoleto | Verificar o que mudou desde a geração |
| `pending` / `delayed` | Processamento não concluído | Distinguir de "processou e não achou" |

---

## Decisões do agente

| Decisão | Quando |
| :--- | :--- |
| **Orientar** | A evidência sustenta uma explicação e nenhuma ação é necessária ou autorizada |
| **Agir** | Ação solicitada ou indicada, usuário com permissão, justificativa fundamentada em evidência |
| **Escalar** | Evidência insuficiente, conflito irresolvível, necessidade de inspeção física, ou pedido explícito |
