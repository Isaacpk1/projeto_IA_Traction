/**
 * Plataforma de agentes industriais — casca da aplicação.
 *
 * Duas fontes de dados, uma interface: quando a API está no ar, a plataforma
 * consulta o BFF; quando o arquivo é servido estático, lê os dados embutidos.
 * O componente não sabe a diferença — é o que permite o mesmo código rodar em
 * `npm run dev`, no GitHub Pages e no artefato publicado sem divergir.
 */
const { useState, useMemo, useCallback, useEffect, createElement: h, Fragment } = React;

const API = (() => {
  const meta = typeof window !== "undefined" ? window.__API_BASE__ : null;
  if (meta) return meta.replace(/\/$/, "");
  if (typeof location !== "undefined" && location.port === "5173") return "http://127.0.0.1:8010";
  return null;
})();
const TEM_API = Boolean(API);

const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toFixed(d);
const pct = (v) => (v === null || v === undefined) ? "—" : (v * 100).toFixed(0) + "%";
const num = (v) => (v === null || v === undefined) ? "—" : Math.round(v).toLocaleString("pt-BR");

const STATUS = {
  sustentada: ["ok", "Sustentada"], refutada: ["no", "Refutada"],
  refutada_direcao_oposta: ["no", "Refutada na direção oposta"],
  inconclusiva: ["unk", "Inconclusiva"], nao_executada: ["unk", "Não executada"],
  done: ["ok", "concluído"], pending: ["warn", "na fila"], leased: ["warn", "executando"],
  failed: ["no", "falhou"], pass: ["ok", "passou"], blocked: ["no", "bloqueado"],
};
const Pill = ({ status }) => {
  const [cls, rot] = STATUS[status] || ["unk", status || "—"];
  return h("span", { className: "pill " + cls }, h("i", null), rot);
};
const Kpi = ({ k, v, n, cor }) => h("div", { className: "kpi" },
  h("div", { className: "k" }, k),
  h("div", { className: "v", style: cor ? { color: cor } : null }, v),
  h("div", { className: "n" }, n));
const Panel = ({ titulo, hint, children }) => h("section", { className: "panel" },
  h("h2", null, titulo, hint && h("span", { className: "hint" }, hint)),
  h("div", { className: "body" }, children));

/* -------------------------------------------------- dados */
function useDados() {
  const [estado, setEstado] = useState({ carregando: TEM_API, erro: null,
    relatorio: window.__RELATORIO__ || null, execucoes: window.__EXECUCOES__ || [] });
  const [runId, setRunId] = useState((window.__RELATORIO__ || {}).run_id || "e1_v1");
  const [runs, setRuns] = useState([]);

  useEffect(() => {
    if (!TEM_API) return;
    let vivo = true;
    setEstado(e => ({ ...e, carregando: true, erro: null }));
    (async () => {
      try {
        const rs = await fetch(`${API}/api/runs`).then(r => r.json());
        if (!vivo) return;
        setRuns(rs);
        const [rel, ex] = await Promise.all([
          fetch(`${API}/api/report?run_id=${runId}&e2_run_id=e2_v1`).then(r => r.json()),
          fetch(`${API}/api/executions?run_id=${runId}`).then(r => r.json()),
        ]);
        if (!vivo) return;
        setEstado({ carregando: false, erro: null, relatorio: rel, execucoes: ex });
      } catch (err) {
        if (vivo) setEstado(e => ({ ...e, carregando: false, erro: String(err) }));
      }
    })();
    return () => { vivo = false; };
  }, [runId]);

  return { ...estado, runId, setRunId, runs };
}

/* -------------------------------------------------- gráficos */
function DoseChart({ pontos }) {
  if (!pontos || !pontos.length) return h("div", { className: "vazio" }, "Sem dados de dose.");
  const W = 720, H = 300, m = { t: 16, r: 20, b: 48, l: 50 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const xs = pontos.map(p => p.intensidade);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const sx = v => m.l + (x1 === x0 ? iw / 2 : (v - x0) / (x1 - x0) * iw);
  const sy = v => m.t + ih - v * ih;
  const mono = "IBM Plex Mono, monospace", k = [];
  for (let g = 0; g <= 4; g++) {
    const y = sy(g / 4);
    k.push(h("line", { key: "g" + g, x1: m.l, x2: m.l + iw, y1: y, y2: y, stroke: "var(--rule)" }));
    k.push(h("text", { key: "gl" + g, x: m.l - 9, y: y + 4, fill: "var(--ink-3)", fontSize: 10.5,
      textAnchor: "end", fontFamily: mono }, (g / 4).toFixed(2)));
  }
  pontos.forEach((p, i) => {
    const x = sx(p.intensidade);
    k.push(h("text", { key: "x" + i, x, y: m.t + ih + 18, fill: "var(--ink-2)", fontSize: 10.5,
      textAnchor: "middle", fontFamily: mono }, p.intensidade.toFixed(2)));
    k.push(h("text", { key: "s" + i, x, y: m.t + ih + 32, fill: "var(--ink-3)", fontSize: 9.5,
      textAnchor: "middle", fontFamily: mono }, p.seed));
  });
  k.push(h("text", { key: "yl", x: m.l - 9, y: m.t - 3, fill: "var(--ink-3)", fontSize: 10.5,
    textAnchor: "end", fontFamily: mono }, "M4"));
  k.push(h("text", { key: "xl", x: m.l + iw / 2, y: H - 4, fill: "var(--ink-3)", fontSize: 11,
    textAnchor: "middle" }, "intensidade de degradação →"));
  [["A", "var(--arm-a)"], ["B", "var(--arm-b)"]].forEach(([arm, cor]) => {
    const pts = pontos.filter(p => p.por_braco[arm] != null);
    if (!pts.length) return;
    k.push(h("polyline", { key: "p" + arm, fill: "none", stroke: cor, strokeWidth: 2.4,
      strokeLinejoin: "round", points: pts.map(p => `${sx(p.intensidade)},${sy(p.por_braco[arm])}`).join(" ") }));
    pts.forEach((p, i) => k.push(h("circle", { key: `c${arm}${i}`, cx: sx(p.intensidade),
      cy: sy(p.por_braco[arm]), r: 4.5, fill: cor, stroke: "var(--surface)", strokeWidth: 2 })));
  });
  return h("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Acerto de decisão por intensidade de degradação em cada braço" }, k);
}

function CasosChart({ pareado }) {
  if (!pareado) return h("div", { className: "vazio" }, "Sem pares por caso.");
  const ent = Object.entries(pareado.por_caso);
  const W = 720, lin = 19, m = { t: 8, r: 16, b: 26, l: 150 };
  const H = m.t + ent.length * lin + m.b, iw = W - m.l - m.r;
  const lim = Math.max(0.3, ...ent.map(([, v]) => Math.abs(v)));
  const sx = v => m.l + (v + lim) / (2 * lim) * iw, zero = sx(0);
  const mono = "IBM Plex Mono, monospace";
  const k = [h("line", { key: "z", x1: zero, x2: zero, y1: m.t, y2: m.t + ent.length * lin,
    stroke: "var(--ink-3)", strokeWidth: 1.3 })];
  ent.forEach(([c, v], i) => {
    const y = m.t + i * lin + lin / 2;
    k.push(h("rect", { key: "r" + i, x: Math.min(zero, sx(v)), y: y - 5.5,
      width: Math.abs(sx(v) - zero) || 1.4, height: 11,
      fill: v > 0 ? "var(--arm-b)" : v < 0 ? "var(--arm-a)" : "var(--ink-3)", rx: 1 }));
    k.push(h("text", { key: "t" + i, x: m.l - 10, y: y + 3.5, fill: "var(--ink-2)", fontSize: 10.5,
      textAnchor: "end", fontFamily: mono }, c.replace("case_tkt_", "").replace("case_", "")));
  });
  k.push(h("text", { key: "a", x: m.l, y: H - 7, fill: "var(--arm-a)", fontSize: 10.5, fontFamily: mono },
    "← mono acerta mais"));
  k.push(h("text", { key: "b", x: W - m.r, y: H - 7, fill: "var(--arm-b)", fontSize: 10.5,
    textAnchor: "end", fontFamily: mono }, "multi acerta mais →"));
  return h("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Diferença de acerto entre multi e mono por caso" }, k);
}

/* -------------------------------------------------- visão geral */
const META = (typeof window !== "undefined" && window.__META__) || {};

function AvisoParcial() {
  if (!META.aviso) return null;
  return h("div", { className: "note caveat" }, h("p", null, META.aviso));
}

function VisaoGeral({ R }) {
  const m4 = R.metricas.find(m => m.id === "M4") || { por_braco: {} };
  const h1 = R.hipoteses.find(x => x.id === "H1");
  const h2 = R.hipoteses.find(x => x.id === "H2");
  const p = R.pareado_por_caso;
  const A = R.bracos.A || {}, B = R.bracos.B || {};
  const conf = (A.n && B.n) ? ((A.concluidas + B.concluidas) / (A.n + B.n)) : null;
  const indistinguivel = !p || p.ic_low == null || (p.ic_low <= 0 && p.ic_high >= 0);

  return h(Fragment, null,
    h(AvisoParcial, null),
    h("div", { className: "kpis" },
      h(Kpi, { k: "Execuções analisadas", v: R.execucoes, n: `${A.n || 0} mono · ${B.n || 0} multi` }),
      h(Kpi, { k: "Acerto de decisão · mono", v: pct(m4.por_braco.A), n: "M4", cor: "var(--arm-a)" }),
      h(Kpi, { k: "Acerto de decisão · multi", v: pct(m4.por_braco.B), n: "M4", cor: "var(--arm-b)" }),
      h(Kpi, { k: "Conformidade", v: pct(conf), n: "execuções concluídas sem erro" })),

    h(Panel, { titulo: "Veredito da pergunta central", hint: "H1 · P1.1" },
      h("p", { style: { fontSize: 17, color: "var(--ink)" } },
        indistinguivel
          ? "Mono e multi não se distinguem nesta amostra."
          : `A arquitetura ${p.diferenca_media > 0 ? "multi" : "mono"}-agente acerta mais.`),
      h("p", null, indistinguivel
        ? `A diferença pareada por caso é ${fmt(p && p.diferenca_media)} com IC95 ` +
          `[${fmt(p && p.ic_low)} · ${fmt(p && p.ic_high)}] — cruza o zero.`
        : `Diferença pareada de ${fmt(p.diferenca_media)}, IC95 [${fmt(p.ic_low)} · ${fmt(p.ic_high)}].`),
      h("div", { style: { display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 } },
        h1 && h(Pill, { status: h1.status }), h2 && h(Pill, { status: h2.status }),
        h("span", { className: "mono mid", style: { fontSize: 12 } },
          `H1 n=${h1 ? h1.n : "—"} · H2 n=${h2 ? h2.n : "—"}`)),
      h1 && h1.detalhe && h1.detalhe.efeito_principal && h1.estimativa > 0 &&
        h1.detalhe.efeito_principal.coef < 0 &&
        h("div", { className: "note caveat" }, h("p", null,
          h("b", null, "Atenção à leitura: "),
          "a interação positiva significa que a multi ", h("b", null, "encurta a distância"),
          " com a degradação — não que ela lidera. O efeito principal é negativo."))),

    h("div", { className: "grid2" },
      h(Panel, { titulo: "Dose-resposta", hint: "M4 × intensidade" },
        h("div", { className: "legend" },
          h("span", null, h("i", { style: { background: "var(--arm-a)" } }), "mono"),
          h("span", null, h("i", { style: { background: "var(--arm-b)" } }), "multi")),
        h(DoseChart, { pontos: R.dose_resposta })),
      h(Panel, { titulo: "Custo por execução" },
        h("table", null, h("tbody", null,
          [["Chamadas de LLM", fmt(A.llm_calls, 1), fmt(B.llm_calls, 1)],
           ["Tokens de entrada", num(A.tokens_in), num(B.tokens_in)],
           ["Duração média (s)", fmt(A.duracao_s, 1), fmt(B.duracao_s, 1)],
           ["Erro de comportamento", A.erro_comportamento, B.erro_comportamento],
           ["Erro de contrato", A.erro_contrato, B.erro_contrato]].map((l, i) =>
            h("tr", { key: i }, h("td", null, l[0]),
              h("td", { className: "num win-a" }, l[1]), h("td", { className: "num win-b" }, l[2])))))))
  );
}

/* -------------------------------------------------- experimentos */
function Experimentos({ R }) {
  return h(Fragment, null,
    h(Panel, { titulo: "Métricas determinísticas", hint: "M1–M16 sobre o trace persistido" },
      h("div", { className: "scroll" }, h("table", null,
        h("thead", null, h("tr", null, h("th", null, "ID"), h("th", null, "Métrica"),
          h("th", { style: { textAlign: "right" } }, "Mono"),
          h("th", { style: { textAlign: "right" } }, "Multi"),
          h("th", { style: { textAlign: "right" } }, "Δ"), h("th", null, "Favorece"),
          h("th", { style: { textAlign: "right" } }, "n A/B"))),
        h("tbody", null, R.metricas.map(m => {
          const d = m.diferenca;
          let cls = "", quem = "—";
          if (d != null && Math.abs(d) > 1e-9) {
            const mb = m.menor_e_melhor ? d < 0 : d > 0;
            cls = mb ? "win-b" : "win-a"; quem = mb ? "multi" : "mono";
          }
          return h("tr", { key: m.id },
            h("td", { className: "mono" }, m.id),
            h("td", null, m.nome, m.menor_e_melhor && h("span", { className: "mid" }, " ↓ melhor")),
            h("td", { className: "num" }, fmt(m.por_braco.A)),
            h("td", { className: "num" }, fmt(m.por_braco.B)),
            h("td", { className: "num " + cls }, d == null ? "—" : (d > 0 ? "+" : "") + fmt(d)),
            h("td", { className: "mono mid" }, quem),
            h("td", { className: "num mid" }, `${m.aplicavel.A || 0}/${m.aplicavel.B || 0}`));
        })))),
      h("div", { className: "note caveat" }, h("p", null,
        h("b", null, "“Não aplicável” nunca é zero. "),
        "M14 não existe na arquitetura mono. A coluna n A/B mostra sobre quantas execuções cada ",
        "média foi calculada."))),

    h(Panel, { titulo: "Vereditos das hipóteses", hint: "todos os testes declarados antes da execução" },
      h("table", null,
        h("thead", null, h("tr", null, h("th", null, "Hipótese"), h("th", null, "Teste"),
          h("th", null, "Métrica"), h("th", { style: { textAlign: "right" } }, "n"),
          h("th", { style: { textAlign: "right" } }, "Estimativa"),
          h("th", { style: { textAlign: "right" } }, "IC95"), h("th", null, "Veredito"))),
        h("tbody", null, R.hipoteses.map((x, i) => h("tr", { key: i },
          h("td", { className: "mono" }, `${x.id}/${x.predicao}`),
          h("td", null, x.teste), h("td", { className: "mono" }, x.metrica),
          h("td", { className: "num" }, x.n),
          h("td", { className: "num" }, x.estimativa == null ? "—" : fmt(x.estimativa, 3)),
          h("td", { className: "num" }, x.ic_low == null ? "—" : `[${fmt(x.ic_low, 2)} · ${fmt(x.ic_high, 2)}]`),
          h("td", null, h(Pill, { status: x.status })))))),
      h("div", { className: "note" }, h("p", null,
        h("b", null, "H3 e H4 não foram executados"),
        " e nenhum veredito é emitido para eles. Não-execução não é resultado inconclusivo."))),

    h(Panel, { titulo: "Divergência por chamado", hint: "o caso é a unidade de amostragem" },
      h(CasosChart, { pareado: R.pareado_por_caso })));
}

/* -------------------------------------------------- execuções */
const rotArm = a => a === "A" ? "mono" : a === "B" ? "multi" : a;

function Detalhe({ e }) {
  const r = e.resolucao;
  return h("div", { className: "detalhe" },
    e.handoffs.length > 0 && h(Fragment, null,
      h("h4", null, `Handoffs (${e.handoffs.length})`),
      e.handoffs.map((x, i) => h("div", { className: "hoff", key: i },
        `${x.de} → ${x.para} · após passo ${x.apos_passo}`))),
    h("h4", null, `Trajetória — ${e.passos.length} passos`),
    e.passos.map((p, i) => h("div", { className: "passo", key: i },
      h("div", { className: "n" }, String(p.step)),
      h("div", { className: "who" }, p.agent),
      h("div", null,
        p.tool && h("span", { className: "tool" }, p.tool),
        p.reasoning && h("div", { className: "d" }, p.reasoning),
        p.args && Object.keys(p.args).length > 0 && h("div", { className: "d" }, JSON.stringify(p.args)),
        p.erro ? h("div", { className: "d err" }, "erro: " + p.erro)
               : p.resultado && h("div", { className: "d" }, p.resultado)))),
    h("h4", null, "Resolução"),
    !r ? h("div", { className: "resol" },
          h("div", { className: "just" }, "O agente terminou sem chamar submit_resolution."))
       : h("div", { className: "resol" },
          h("div", { className: "mono", style: { fontWeight: 600 } }, "decisão: " + r.decision),
          h("div", { className: "just" }, r.justification || "—"),
          r.evidencias.length > 0 && h("div", { className: "evid" },
            r.evidencias.map((ev, i) => h(Fragment, { key: i },
              h("span", { className: ev.resolve ? "s" : "x" }, ev.resolve ? "resolve" : "não resolve"),
              h("span", null, `${ev.tool} · ${ev.field}`),
              h("span", { className: "mid" }, "step " + ev.step)))),
          r.unverified.length > 0 && h("div", { className: "d", style: { marginTop: 9 } },
            "lacunas: " + r.unverified.join(" · ")),
          e.guard.verdict === "blocked" && h("div", { className: "d err", style: { marginTop: 9 } },
            `guardrail bloqueou (${e.guard.failed.join(", ")}) e entregou "${e.guard.decision}"`)));
}

function LinhaExec({ e }) {
  const [ab, setAb] = useState(false);
  const dec = (e.resolucao || {}).decision;
  const alterna = useCallback(() => setAb(v => !v), []);
  return h(Fragment, null,
    h("div", { className: "exec", role: "button", tabIndex: 0, "aria-expanded": ab, onClick: alterna,
      onKeyDown: ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); alterna(); } } },
      h("div", { className: "bar", style: { background: `var(--arm-${e.arm === "A" ? "a" : "b"})` } }),
      h("div", { className: "cid" }, e.case_id.replace("case_tkt_", "").replace("case_", "")),
      h("div", { className: "t" }, `${rotArm(e.arm)} · ${e.seed || "—"} · ${e.passos.length} passos`),
      h("div", { className: "mono", style: dec ? null : { color: "var(--unk)" } }, dec || "sem resolução"),
      h(Pill, { status: e.guard.verdict })),
    ab && h(Detalhe, { e }));
}

function Execucoes({ execucoes }) {
  const [arm, setArm] = useState(""), [dec, setDec] = useState("");
  const [guard, setGuard] = useState(""), [busca, setBusca] = useState("");
  const decisoes = useMemo(
    () => [...new Set(execucoes.map(e => (e.resolucao || {}).decision).filter(Boolean))].sort(),
    [execucoes]);
  const vis = useMemo(() => {
    const t = busca.trim().toLowerCase();
    return execucoes.filter(e =>
      (!arm || e.arm === arm) && (!dec || (e.resolucao || {}).decision === dec) &&
      (!guard || (e.guard.verdict || "") === guard) &&
      (!t || e.case_id.toLowerCase().includes(t)));
  }, [execucoes, arm, dec, guard, busca]);

  return h("section", { className: "panel", style: { marginTop: 0 } },
    h("div", { className: "filtros" },
      h("select", { value: arm, onChange: e => setArm(e.target.value), "aria-label": "Braço" },
        h("option", { value: "" }, "todos os braços"), h("option", { value: "A" }, "mono"),
        h("option", { value: "B" }, "multi")),
      h("select", { value: dec, onChange: e => setDec(e.target.value), "aria-label": "Decisão" },
        h("option", { value: "" }, "todas as decisões"),
        decisoes.map(d => h("option", { key: d, value: d }, d))),
      h("select", { value: guard, onChange: e => setGuard(e.target.value), "aria-label": "Guardrail" },
        h("option", { value: "" }, "guardrail: qualquer"), h("option", { value: "pass" }, "passou"),
        h("option", { value: "blocked" }, "bloqueado")),
      h("input", { type: "search", value: busca, onChange: e => setBusca(e.target.value),
        placeholder: "filtrar chamado…", "aria-label": "Filtrar por chamado" }),
      h("span", { className: "cont" }, `${vis.length} de ${execucoes.length}`)),
    h("div", { style: { maxHeight: "68vh", overflow: "auto" } },
      vis.length === 0 ? h("div", { className: "vazio" }, "Nenhuma execução com esses filtros.")
                       : vis.map(e => h(LinhaExec, { e, key: e.id }))));
}

/* -------------------------------------------------- console */
function Console() {
  const [casos, setCasos] = useState([]);
  const [fila, setFila] = useState([]);
  const [form, setForm] = useState({ case_id: "", architecture: "mono", seed: "complete", criticality: "medium" });
  const [msg, setMsg] = useState(null);
  const [enviando, setEnviando] = useState(false);

  const recarregar = useCallback(async () => {
    if (!TEM_API) return;
    try {
      const [cs, ts] = await Promise.all([
        fetch(`${API}/api/cases`).then(r => r.json()),
        fetch(`${API}/api/tickets?limite=60`).then(r => r.json()),
      ]);
      setCasos(cs); setFila(ts);
      setForm(f => f.case_id ? f : { ...f, case_id: cs.length ? cs[0].case_id : "" });
    } catch (e) { setMsg({ erro: true, texto: String(e) }); }
  }, []);
  useEffect(() => { recarregar(); const t = setInterval(recarregar, 5000); return () => clearInterval(t); },
    [recarregar]);

  if (!TEM_API) return h(Panel, { titulo: "Console de atendimento" },
    h("div", { className: "note caveat" }, h("p", null,
      h("b", null, "Disponível apenas com o BFF no ar. "),
      "Suba com ", h("code", null, "uv run uvicorn src.interfaces.api:app --port 8010"),
      " e abra a plataforma em modo de desenvolvimento.")));

  const enviar = async (ev) => {
    ev.preventDefault(); setEnviando(true); setMsg(null);
    try {
      const r = await fetch(`${API}/api/tickets`, { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      const b = await r.json();
      if (!r.ok) throw new Error(b.detail || r.statusText);
      setMsg({ texto: `chamado ${b.task_id.slice(0, 10)}… enfileirado com prioridade ${b.priority}` });
      recarregar();
    } catch (e) { setMsg({ erro: true, texto: String(e) }); }
    finally { setEnviando(false); }
  };

  const caso = casos.find(c => c.case_id === form.case_id);
  return h(Fragment, null,
    h("div", { className: "grid2" },
      h(Panel, { titulo: "Abrir chamado", hint: "RF29" },
        h("form", { className: "form", onSubmit: enviar },
          h("label", null, "Chamado",
            h("select", { value: form.case_id, onChange: e => setForm({ ...form, case_id: e.target.value }) },
              casos.map(c => h("option", { key: c.case_id, value: c.case_id },
                `${c.ticket_id} · ${c.case_id.replace("case_", "")}`)))),
          h("label", null, "Arquitetura",
            h("select", { value: form.architecture, onChange: e => setForm({ ...form, architecture: e.target.value }) },
              h("option", { value: "mono" }, "mono-agente"), h("option", { value: "multi" }, "multi-agente"))),
          h("label", null, "Regime de evidência (seed)",
            h("select", { value: form.seed, onChange: e => setForm({ ...form, seed: e.target.value }) },
              ["complete", "s10", "x1", "s13"].map(s => h("option", { key: s, value: s }, s)))),
          h("label", null, "Criticidade do ativo",
            h("select", { value: form.criticality, onChange: e => setForm({ ...form, criticality: e.target.value }) },
              ["critical", "high", "medium", "low"].map(s => h("option", { key: s, value: s }, s)))),
          h("button", { className: "btn", type: "submit", disabled: enviando || !form.case_id },
            enviando ? "enfileirando…" : "Abrir chamado"),
          msg && h("div", { className: "msg", style: { color: msg.erro ? "var(--no)" : "var(--ok)" } }, msg.texto)),
        caso && h("div", { className: "note" }, h("p", null,
          h("b", null, caso.ticket_id + " · "), caso.message))),
      h(Panel, { titulo: "Fila de atendimento", hint: "atualiza a cada 5 s" },
        h("div", { className: "scroll" }, h("table", null,
          h("thead", null, h("tr", null, h("th", null, "Chamado"), h("th", null, "Arq."),
            h("th", null, "Estado"), h("th", null, "Erro"))),
          h("tbody", null, fila.length === 0
            ? h("tr", null, h("td", { colSpan: 4, className: "vazio" }, "Fila vazia."))
            : fila.map(t => h("tr", { key: t.task_id },
                h("td", { className: "mono" }, t.case_id.replace("case_tkt_", "").replace("case_", "")),
                h("td", { className: "mono mid" }, rotArm(t.arm)),
                h("td", null, h(Pill, { status: t.state })),
                h("td", { className: "mono mid" }, t.error_class || "—")))))))),
    h("div", { className: "note caveat" }, h("p", null,
      h("b", null, "O chamado entra na fila; quem executa é o worker. "),
      "Rode ", h("code", null, "uv run agentes run --run-id console"),
      " para atendê-lo — cada execução consome cota do Gemini.")));
}


/* -------------------------------------------------- triagem */
const URG_ROT = { alta: ["no", "urgência alta"], media: ["warn", "urgência média"],
                  baixa: ["unk", "urgência baixa"] };
const ORDEM_URG = { alta: 0, media: 1, baixa: 2 };

/** Marca **negrito** vindo do briefing sem interpretar HTML de dado. */
function comEnfase(texto) {
  return texto.split(/\*\*(.+?)\*\*/g).map((parte, i) =>
    i % 2 ? h("b", { key: i }, parte) : parte);
}

function CartaoTriagem({ e }) {
  const t = e.triagem;
  const [ab, setAb] = useState(false);
  const [cls, rot] = URG_ROT[t.urgencia] || URG_ROT.baixa;
  return h("div", { className: "tri" },
    h("div", { className: "faixa urg-" + t.urgencia }),
    h("div", { className: "corpo" },
      h("div", { className: "cab" },
        h("h3", null, t.titulo),
        h("span", { className: "pill " + cls }, h("i", null), rot),
        h("span", { className: "cid" },
          `${e.case_id.replace("case_tkt_", "").replace("case_", "")} · ${rotArm(e.arm)} · ${e.seed || "—"}`)),
      h("ul", { className: "porque" }, t.porque.map((b, i) => h("li", { key: i }, comEnfase(b)))),
      h("dl", { className: "linhas" },
        t.verificado.length > 0 && h(Fragment, null,
          h("dt", null, "já verificado"), h("dd", null, t.verificado.join(" · "))),
        t.evidencia_frouxa.length > 0 && h(Fragment, null,
          h("dt", null, "evidência frouxa"), h("dd", null, t.evidencia_frouxa.join(" · "))),
        t.conflitos.length > 0 && h(Fragment, null,
          h("dt", null, "conflitos"), h("dd", null, t.conflitos.join(" · ")))),
      h("div", { className: "decidir" }, h("b", null, "o que decidir"), t.decidir),
      h("button", { className: "abrir", onClick: () => setAb(v => !v), "aria-expanded": ab },
        ab ? "esconder trajetória" : "ver trajetória completa"),
      ab && h(Detalhe, { e })));
}

function Triagem({ execucoes }) {
  const [urg, setUrg] = useState("");
  const [motivo, setMotivo] = useState("");
  const pendentes = useMemo(
    () => execucoes.filter(e => e.triagem && e.triagem.precisa_humano)
      .sort((a, b) => ORDEM_URG[a.triagem.urgencia] - ORDEM_URG[b.triagem.urgencia]),
    [execucoes]);
  const motivos = useMemo(
    () => [...new Set(pendentes.map(e => e.triagem.motivo))].sort(), [pendentes]);
  const vis = useMemo(() => pendentes.filter(e =>
    (!urg || e.triagem.urgencia === urg) && (!motivo || e.triagem.motivo === motivo)),
    [pendentes, urg, motivo]);
  const conta = u => pendentes.filter(e => e.triagem.urgencia === u).length;

  return h(Fragment, null,
    h("div", { className: "kpis" },
      h(Kpi, { k: "Precisam de humano", v: pendentes.length,
        n: `de ${execucoes.length} atendimentos` }),
      h(Kpi, { k: "Urgência alta", v: conta("alta"), n: "ação bloqueada ou sem resolução",
        cor: "var(--no)" }),
      h(Kpi, { k: "Urgência média", v: conta("media"), n: "conclusão não verificável ou conflito",
        cor: "var(--warn)" }),
      h(Kpi, { k: "Resolvidos sozinhos", v: execucoes.length - pendentes.length,
        n: "entregues sem intervenção", cor: "var(--ok)" })),

    h("section", { className: "panel" },
      h("div", { className: "filtros" },
        h("select", { value: urg, onChange: e => setUrg(e.target.value), "aria-label": "Urgência" },
          h("option", { value: "" }, "todas as urgências"),
          ["alta", "media", "baixa"].map(u => h("option", { key: u, value: u }, u))),
        h("select", { value: motivo, onChange: e => setMotivo(e.target.value), "aria-label": "Motivo" },
          h("option", { value: "" }, "todos os motivos"),
          motivos.map(m => h("option", { key: m, value: m }, m.replace(/_/g, " ")))),
        h("span", { className: "cont" }, `${vis.length} de ${pendentes.length}`)),
      h("div", { className: "body", style: { maxHeight: "70vh", overflow: "auto" } },
        vis.length === 0
          ? h("div", { className: "vazio" }, "Nenhum atendimento nesta faixa.")
          : vis.map(e => h(CartaoTriagem, { e, key: e.id })))));
}

/* -------------------------------------------------- tema */
function useTema() {
  const [tema, setTema] = useState(() => {
    try { return localStorage.getItem("tema") || "sistema"; } catch { return "sistema"; }
  });
  useEffect(() => {
    const raiz = document.documentElement;
    if (tema === "sistema") raiz.removeAttribute("data-theme");
    else raiz.setAttribute("data-theme", tema);
    try { localStorage.setItem("tema", tema); } catch { /* modo privado */ }
  }, [tema]);
  return [tema, setTema];
}

/* -------------------------------------------------- aplicação */
const VISOES = [
  { id: "geral", rot: "Visão geral", grupo: "Experimento" },
  { id: "exp", rot: "Métricas e vereditos", grupo: "Experimento" },
  { id: "triagem", rot: "Triagem", grupo: "Operação" },
  { id: "exec", rot: "Execuções", grupo: "Operação" },
  { id: "console", rot: "Console de atendimento", grupo: "Operação" },
];

function App() {
  const { relatorio, execucoes, carregando, erro, runId, setRunId, runs } = useDados();
  const [visao, setVisao] = useState(() => (location.hash || "#geral").slice(1));
  const [tema, setTema] = useTema();
  useEffect(() => {
    const ouvir = () => setVisao((location.hash || "#geral").slice(1));
    addEventListener("hashchange", ouvir); return () => removeEventListener("hashchange", ouvir);
  }, []);
  const ir = id => { location.hash = id; setVisao(id); };
  const atual = VISOES.find(v => v.id === visao) || VISOES[0];

  const corpo = () => {
    if (erro) return h("div", { className: "note erro" }, h("p", null,
      h("b", null, "Não foi possível carregar do BFF. "), erro,
      h("br"), "Confirme que a API está no ar em ", h("code", null, API || "—"), "."));
    if (carregando || !relatorio) return h("div", { className: "vazio" }, "Carregando…");
    switch (atual.id) {
      case "exp": return h(Experimentos, { R: relatorio });
      case "triagem": return h(Triagem, { execucoes });
      case "exec": return h(Execucoes, { execucoes });
      case "console": return h(Console);
      default: return h(VisaoGeral, { R: relatorio });
    }
  };

  const grupos = [...new Set(VISOES.map(v => v.grupo))];
  return h("div", { className: "app" },
    h("aside", { className: "side" },
      h("div", { className: "brand" },
        h("div", { className: "n" }, "Agentes industriais"),
        h("div", { className: "s" }, "Inteli × TRACTIAN")),
      h("nav", { className: "navg" }, grupos.map(g => h(Fragment, { key: g },
        h("div", { className: "grp" }, g),
        VISOES.filter(v => v.grupo === g).map(v => h("button", { key: v.id,
          "aria-current": atual.id === v.id ? "page" : undefined, onClick: () => ir(v.id) },
          v.rot,
          v.id === "exec" && execucoes.length > 0 &&
            h("span", { className: "badge" }, execucoes.length),
          v.id === "triagem" && execucoes.length > 0 &&
            h("span", { className: "badge" },
              execucoes.filter(x => x.triagem && x.triagem.precisa_humano).length)))))),
      h("div", { className: "foot" },
        TEM_API ? "BFF conectado" : "dados embutidos",
        h("br"), relatorio ? `${relatorio.execucoes} execuções` : "—",
        META.commit && h(Fragment, null, h("br"), "commit ", META.commit),
        META.gerado && h(Fragment, null, h("br"), META.gerado))),

    h("div", { className: "main" },
      h("header", { className: "top" },
        h("h1", null, atual.rot),
        h("div", { className: "sp" },
          TEM_API && runs.length > 0 && h("label", { className: "ctrl" }, "rodada",
            h("select", { value: runId, onChange: e => setRunId(e.target.value) },
              runs.map(r => h("option", { key: r.run_id, value: r.run_id },
                `${r.run_id} (${r.execucoes})`)))),
          h("label", { className: "ctrl" }, "tema",
            h("select", { value: tema, onChange: e => setTema(e.target.value), "aria-label": "Tema" },
              h("option", { value: "sistema" }, "sistema"), h("option", { value: "light" }, "claro"),
              h("option", { value: "dark" }, "escuro"))))),
      h("main", { className: "content" }, corpo())));
}

ReactDOM.createRoot(document.getElementById("app")).render(h(App));
