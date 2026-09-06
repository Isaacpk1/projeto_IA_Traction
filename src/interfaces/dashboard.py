"""Gera o relatório visual do experimento a partir do quadro de análise.

O front é uma **view** do que `analysis.report` calcula, nunca uma segunda
implementação: se o número da tela divergir do número do teste, é bug. Por isso
o HTML recebe o dicionário serializado inteiro e não recalcula nada.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["render_dashboard"]

_CSS = """
:root{
  --ground:#F1F4F4; --surface:#FFFFFF; --sunken:#E7ECEB;
  --ink:#0F191C; --ink-2:#3D4B4E; --ink-3:#6C7A7C; --rule:#D3DBDA;
  --accent:#0A6E6E; --accent-soft:#DCEAE8;
  --arm-a:#3F6C9E; --arm-b:#C2603A;
  --ok:#2E7D57; --no:#B3402F; --unk:#7A7168;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0C1315; --surface:#131E20; --sunken:#0A1113;
    --ink:#E4EDEB; --ink-2:#A9B8B7; --ink-3:#78888A; --rule:#25373A;
    --accent:#4FB0A8; --accent-soft:#152B2C;
    --arm-a:#7FA6D4; --arm-b:#E09266;
    --ok:#5CB98A; --no:#E1705C; --unk:#A99C8C;
  }
}
:root[data-theme="dark"]{
  --ground:#0C1315; --surface:#131E20; --sunken:#0A1113;
  --ink:#E4EDEB; --ink-2:#A9B8B7; --ink-3:#78888A; --rule:#25373A;
  --accent:#4FB0A8; --accent-soft:#152B2C;
  --arm-a:#7FA6D4; --arm-b:#E09266;
  --ok:#5CB98A; --no:#E1705C; --unk:#A99C8C;
}
*{box-sizing:border-box}
body{
  background:var(--ground); color:var(--ink); margin:0;
  font-family:"IBM Plex Sans","Segoe UI",system-ui,sans-serif;
  font-size:16px; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:960px;margin:0 auto;padding:48px 24px 96px}
h1,h2,h3{font-family:"IBM Plex Sans Condensed","IBM Plex Sans",sans-serif;
  text-wrap:balance;margin:0;line-height:1.15}
h1{font-size:clamp(32px,5vw,52px);font-weight:700;letter-spacing:-.015em}
h2{font-size:26px;font-weight:600;margin-top:8px}
h3{font-size:18px;font-weight:600}
p{margin:0 0 14px;max-width:66ch;color:var(--ink-2)}
p.lede{font-size:18px;color:var(--ink)}
a{color:var(--accent)}
code,.mono{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.88em}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--accent);font-weight:600}
header.masthead{border-bottom:2px solid var(--ink);padding-bottom:22px;margin-bottom:8px}
.meta{display:flex;flex-wrap:wrap;gap:8px 22px;margin-top:16px;
  font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--ink-3)}
.meta b{color:var(--ink-2);font-weight:500}
section{margin-top:56px}
.sec-head{display:flex;align-items:baseline;gap:14px;border-bottom:1px solid var(--rule);
  padding-bottom:10px;margin-bottom:22px}
.sec-num{font-family:"IBM Plex Mono",monospace;font-size:13px;color:var(--accent);font-weight:600}

/* leitura principal — o painel de instrumento */
.readout{background:var(--surface);border:1px solid var(--rule);
  border-top:4px solid var(--accent);padding:28px 30px;margin-top:28px}
.readout .verdict{font-family:"IBM Plex Sans Condensed",sans-serif;font-size:clamp(26px,4vw,38px);
  font-weight:700;line-height:1.15;margin:6px 0 12px;text-wrap:balance}
.pill{display:inline-flex;align-items:center;gap:7px;font-family:"IBM Plex Mono",monospace;
  font-size:11px;letter-spacing:.1em;text-transform:uppercase;font-weight:600;
  padding:4px 11px;border:1px solid currentColor;border-radius:2px}
.pill .dot{width:7px;height:7px;border-radius:50%;background:currentColor}
.pill.ok{color:var(--ok)} .pill.no{color:var(--no)} .pill.unk{color:var(--unk)}
.coefs{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:1px;
  background:var(--rule);border:1px solid var(--rule);margin-top:18px}
.coef{background:var(--sunken);padding:15px 17px}
.coef .k{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink-3);font-weight:600}
.coef .v{font-family:"IBM Plex Sans Condensed",sans-serif;font-size:30px;font-weight:700;
  font-variant-numeric:tabular-nums;margin:5px 0 1px;line-height:1}
.coef .ci{font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--ink-3)}
.coef .q{font-size:13px;color:var(--ink-2);margin-top:9px;line-height:1.45}

/* comparação de braços */
.arms{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1px;
  background:var(--rule);border:1px solid var(--rule);margin-top:26px}
.arm{background:var(--surface);padding:20px 22px}
.arm .tag{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;font-weight:600;display:flex;align-items:center;gap:8px}
.arm .tag i{width:10px;height:10px;border-radius:2px;display:inline-block}
.arm .big{font-family:"IBM Plex Sans Condensed",sans-serif;font-size:40px;font-weight:700;
  font-variant-numeric:tabular-nums;margin:10px 0 2px;line-height:1}
.arm .unit{font-size:13px;color:var(--ink-3)}
.arm dl{display:grid;grid-template-columns:1fr auto;gap:5px 14px;margin:16px 0 0;
  font-family:"IBM Plex Mono",monospace;font-size:12.5px}
.arm dt{color:var(--ink-3)} .arm dd{margin:0;font-variant-numeric:tabular-nums;color:var(--ink-2)}

/* gráfico */
figure{margin:26px 0 0;background:var(--surface);border:1px solid var(--rule);padding:22px}
figcaption{font-size:13.5px;color:var(--ink-3);margin-top:14px;max-width:70ch}
.legend{display:flex;gap:20px;flex-wrap:wrap;font-family:"IBM Plex Mono",monospace;
  font-size:12px;margin-bottom:14px}
.legend span{display:flex;align-items:center;gap:7px;color:var(--ink-2)}
.legend i{width:14px;height:3px;display:inline-block}
.chart-scroll{overflow-x:auto}
svg{display:block;max-width:100%;height:auto}

/* tabelas */
.tbl-scroll{overflow-x:auto;border:1px solid var(--rule);background:var(--surface);margin-top:22px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:9px 14px;text-align:left;border-bottom:1px solid var(--rule);white-space:nowrap}
th{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink-3);font-weight:600;background:var(--sunken)}
td.num{text-align:right;font-variant-numeric:tabular-nums;font-family:"IBM Plex Mono",monospace}
tr:last-child td{border-bottom:none}
td .mid{color:var(--ink-3)}
.win-a{color:var(--arm-a);font-weight:600} .win-b{color:var(--arm-b);font-weight:600}
.note{border-left:3px solid var(--accent);background:var(--accent-soft);
  padding:14px 18px;margin-top:22px;font-size:14.5px}
.note p{margin:0;color:var(--ink-2);max-width:none}
.note p+p{margin-top:9px}
.caveat{border-left-color:var(--unk);background:transparent;border-left:3px solid var(--unk)}
ul.plain{margin:14px 0 0;padding-left:20px;color:var(--ink-2);font-size:15px;max-width:70ch}
ul.plain li{margin-bottom:9px}
footer{margin-top:72px;padding-top:20px;border-top:1px solid var(--rule);
  font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--ink-3)}

/* explorador de trajetórias */
.filtros{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0 14px;align-items:center}
.filtros select,.filtros input{font-family:"IBM Plex Mono",monospace;font-size:12.5px;
  padding:6px 9px;border:1px solid var(--rule);background:var(--surface);color:var(--ink);border-radius:2px}
.filtros input{min-width:190px}
.filtros .cont{font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--ink-3);margin-left:auto}
.exec-list{border:1px solid var(--rule);background:var(--surface);max-height:520px;overflow-y:auto}
.exec{display:grid;grid-template-columns:14px 1fr auto auto auto;gap:12px;align-items:center;
  padding:9px 14px;border-bottom:1px solid var(--rule);cursor:pointer;font-size:13.5px}
.exec:last-child{border-bottom:none}
.exec:hover,.exec:focus-visible{background:var(--sunken);outline:none}
.exec[aria-expanded="true"]{background:var(--sunken)}
.exec .bar{width:5px;height:26px;border-radius:1px}
.exec .cid{font-family:"IBM Plex Mono",monospace;color:var(--ink)}
.exec .tag2{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--ink-3)}
.exec .dec{font-family:"IBM Plex Mono",monospace;font-size:11.5px;font-weight:600}
.detalhe{border-bottom:1px solid var(--rule);background:var(--ground);padding:18px 20px}
.detalhe h4{margin:0 0 10px;font-family:"IBM Plex Sans Condensed",sans-serif;font-size:15px;
  text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3)}
.detalhe h4+h4{margin-top:22px}
.passo{display:grid;grid-template-columns:38px 118px 1fr;gap:12px;padding:7px 0;
  border-bottom:1px dashed var(--rule);font-size:13px}
.passo:last-child{border-bottom:none}
.passo .n{font-family:"IBM Plex Mono",monospace;color:var(--ink-3);font-size:12px}
.passo .who{font-family:"IBM Plex Mono",monospace;font-size:11.5px;color:var(--accent);font-weight:600}
.passo .what{min-width:0}
.passo .tool{font-family:"IBM Plex Mono",monospace;font-weight:600;color:var(--ink)}
.passo .args,.passo .res{font-family:"IBM Plex Mono",monospace;font-size:11.5px;color:var(--ink-3);
  overflow-wrap:anywhere;margin-top:3px}
.passo .res.err{color:var(--no)}
.resol{background:var(--surface);border:1px solid var(--rule);padding:15px 17px;margin-top:10px}
.resol .just{font-size:14px;color:var(--ink-2);margin:8px 0 0;white-space:pre-wrap}
.evid{display:grid;grid-template-columns:auto 1fr auto;gap:8px 12px;margin-top:12px;
  font-family:"IBM Plex Mono",monospace;font-size:11.5px;align-items:baseline}
.evid .sim{color:var(--ok);font-weight:600} .evid .nao{color:var(--no);font-weight:600}
.hoff{font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--ink-2);padding:5px 0}
.vazio{padding:26px;text-align:center;color:var(--ink-3);font-size:14px}
@media (max-width:640px){ .wrap{padding:32px 16px 64px} th,td{padding:8px 10px}
  .exec{grid-template-columns:14px 1fr auto} .passo{grid-template-columns:32px 1fr} }
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

_JS = r"""
const R = window.__RELATORIO__;
const fmt = (v, d = 2) => (v === null || v === undefined) ? "—" : Number(v).toFixed(d);
const pct = (v) => (v === null || v === undefined) ? "—" : (v * 100).toFixed(0) + "%";
const el = (t, a = {}, ...kids) => {
  const n = document.createElement(t);
  for (const [k, v] of Object.entries(a)) {
    if (k === "class") n.className = v; else if (k === "html") n.innerHTML = v; else n.setAttribute(k, v);
  }
  kids.filter(Boolean).forEach(c => n.append(c.nodeType ? c : document.createTextNode(c)));
  return n;
};
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

/* ---------- curva dose-resposta: um plot de espectro ---------- */
function desenharDose(host, pontos) {
  if (!pontos.length) { host.append(el("p", {}, "Sem dados de dose ainda.")); return; }
  const W = 860, H = 340, m = { t: 18, r: 24, b: 52, l: 56 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const xs = pontos.map(p => p.intensidade);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const sx = v => m.l + (x1 === x0 ? iw / 2 : (v - x0) / (x1 - x0) * iw);
  const sy = v => m.t + ih - v * ih;                 // M4 sempre 0..1
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Acerto de decisão por intensidade de degradação, em cada braço");
  const add = (t, a) => { const n = document.createElementNS(ns, t);
    for (const [k, v] of Object.entries(a)) n.setAttribute(k, v); svg.append(n); return n; };
  const txt = (x, y, s, a) => { const n = add("text", { x, y, ...a }); n.textContent = s; return n; };

  const rule = css("--rule"), ink3 = css("--ink-3"), ink2 = css("--ink-2");
  for (let g = 0; g <= 4; g++) {                      // grade horizontal, 0 a 1
    const v = g / 4, y = sy(v);
    add("line", { x1: m.l, x2: m.l + iw, y1: y, y2: y, stroke: rule, "stroke-width": 1 });
    txt(m.l - 10, y + 4, v.toFixed(2), { fill: ink3, "font-size": 11, "text-anchor": "end",
      "font-family": "IBM Plex Mono, monospace" });
  }
  pontos.forEach(p => {                               // marca de cada nível de dose
    const x = sx(p.intensidade);
    add("line", { x1: x, x2: x, y1: m.t + ih, y2: m.t + ih + 5, stroke: ink3, "stroke-width": 1 });
    txt(x, m.t + ih + 20, p.intensidade.toFixed(2), { fill: ink2, "font-size": 11,
      "text-anchor": "middle", "font-family": "IBM Plex Mono, monospace" });
    txt(x, m.t + ih + 35, p.seed, { fill: ink3, "font-size": 10, "text-anchor": "middle",
      "font-family": "IBM Plex Mono, monospace" });
  });
  txt(m.l - 10, m.t - 4, "M4", { fill: ink3, "font-size": 11, "text-anchor": "end",
    "font-family": "IBM Plex Mono, monospace" });
  txt(m.l + iw / 2, H - 6, "intensidade de degradação  →  evidência pior", { fill: ink3,
    "font-size": 11.5, "text-anchor": "middle" });

  [["A", css("--arm-a")], ["B", css("--arm-b")]].forEach(([arm, cor]) => {
    const pts = pontos.filter(p => p.por_braco[arm] !== null && p.por_braco[arm] !== undefined);
    if (!pts.length) return;
    add("polyline", { points: pts.map(p => `${sx(p.intensidade)},${sy(p.por_braco[arm])}`).join(" "),
      fill: "none", stroke: cor, "stroke-width": 2.5, "stroke-linejoin": "round" });
    pts.forEach(p => add("circle", { cx: sx(p.intensidade), cy: sy(p.por_braco[arm]), r: 5,
      fill: cor, stroke: css("--surface"), "stroke-width": 2 }));
  });
  host.append(svg);
}

/* ---------- diferença por caso ---------- */
function desenharCasos(host, pareado) {
  if (!pareado) return;
  const entradas = Object.entries(pareado.por_caso);
  const W = 860, linha = 21, m = { t: 10, r: 20, b: 30, l: 170 };
  const H = m.t + entradas.length * linha + m.b, iw = W - m.l - m.r;
  const lim = Math.max(0.35, ...entradas.map(([, v]) => Math.abs(v)));
  const sx = v => m.l + (v + lim) / (2 * lim) * iw;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Diferença de acerto entre multi e mono, por caso");
  const add = (t, a) => { const n = document.createElementNS(ns, t);
    for (const [k, v] of Object.entries(a)) n.setAttribute(k, v); svg.append(n); return n; };
  const txt = (x, y, s, a) => { const n = add("text", { x, y, ...a }); n.textContent = s; return n; };
  const zero = sx(0);
  add("line", { x1: zero, x2: zero, y1: m.t, y2: m.t + entradas.length * linha,
    stroke: css("--ink-3"), "stroke-width": 1.5 });
  entradas.forEach(([caso, v], i) => {
    const y = m.t + i * linha + linha / 2;
    const cor = v > 0 ? css("--arm-b") : v < 0 ? css("--arm-a") : css("--ink-3");
    add("rect", { x: Math.min(zero, sx(v)), y: y - 6, width: Math.abs(sx(v) - zero) || 1.5,
      height: 12, fill: cor, rx: 1 });
    txt(m.l - 12, y + 4, caso.replace("case_tkt_", "").replace("case_", ""),
      { fill: css("--ink-2"), "font-size": 11, "text-anchor": "end",
        "font-family": "IBM Plex Mono, monospace" });
  });
  txt(m.l, H - 8, `← mono acerta mais`, { fill: css("--arm-a"), "font-size": 11,
    "font-family": "IBM Plex Mono, monospace" });
  txt(W - m.r, H - 8, `multi acerta mais →`, { fill: css("--arm-b"), "font-size": 11,
    "text-anchor": "end", "font-family": "IBM Plex Mono, monospace" });
  host.append(svg);
}
"""

_JS_MONTA = r"""
/* ---------- montagem ---------- */
const A = R.bracos.A || {}, B = R.bracos.B || {};
const m4 = R.metricas.find(m => m.id === "M4") || { por_braco: {} };
const h1 = R.hipoteses.find(h => h.id === "H1");
const h2 = R.hipoteses.find(h => h.id === "H2");

const STATUS = {
  sustentada: ["ok", "Sustentada"], refutada: ["no", "Refutada"],
  refutada_direcao_oposta: ["no", "Refutada na direção oposta"],
  inconclusiva: ["unk", "Inconclusiva"], nao_executada: ["unk", "Não executada"],
};
function pill(status) {
  const [cls, rot] = STATUS[status] || ["unk", status];
  return el("span", { class: "pill " + cls }, el("i", { class: "dot" }), rot);
}

/* leitura principal */
(function () {
  const host = document.getElementById("readout");
  const a = m4.por_braco.A, b = m4.por_braco.B;
  let frase, detalhe;
  if (a === null || b === null || a === undefined || b === undefined) {
    frase = "Ainda sem acerto de decisão nos dois braços.";
    detalhe = "A rodada precisa concluir execuções em mono e multi antes de comparar.";
  } else {
    const p = R.pareado_por_caso;
    const inconclusivo = !p || p.ic_low === null || (p.ic_low <= 0 && p.ic_high >= 0);
    if (inconclusivo) {
      frase = "Mono e multi não se distinguem nesta amostra.";
      detalhe = "A diferença pareada por caso tem intervalo de confiança que cruza o zero: " +
        "os dados não sustentam dizer que uma arquitetura acerta mais que a outra.";
    } else {
      const venceu = p.diferenca_media > 0 ? "multi-agente" : "mono-agente";
      frase = `A arquitetura ${venceu} acerta mais.`;
      detalhe = `Diferença pareada por caso de ${fmt(p.diferenca_media)} em M4, ` +
        `IC95 [${fmt(p.ic_low)} · ${fmt(p.ic_high)}], reamostrando casos.`;
    }
  }
  host.append(
    el("div", { class: "eyebrow" }, "Pergunta central · H1"),
    el("div", { class: "verdict" }, frase),
    el("p", {}, detalhe)
  );

  /* Dois coeficientes, duas perguntas diferentes. Mostrar so a interacao deixaria
     "sustentada" ser lido como "a multi venceu", que nao e o que ela diz. */
  if (h1 && h1.estimativa !== null) {
    const ef = (h1.detalhe || {}).efeito_principal;
    const cr = (h1.detalhe || {}).cruzamento;
    const grid = el("div", { class: "coefs" });
    grid.append(
      el("div", { class: "coef" },
        el("div", { class: "k" }, "Interação  intensidade × braço"),
        el("div", { class: "v" }, fmt(h1.estimativa)),
        el("div", { class: "ci" }, `IC95 [${fmt(h1.ci_low)} · ${fmt(h1.ci_high)}]`),
        el("div", { class: "q" }, "A distância entre os braços muda com a degradação? " +
          "Positivo = a multi encurta. É o teste pré-registrado de P1.1.")),
      ef ? el("div", { class: "coef" },
        el("div", { class: "k" }, "Efeito principal  braço multi"),
        el("div", { class: "v" }, fmt(ef.coef)),
        el("div", { class: "ci" }, `IC95 [${fmt(ef.ci_low)} · ${fmt(ef.ci_high)}]`),
        el("div", { class: "q" }, "Quem está na frente com evidência íntegra? " +
          "Negativo = a multi está atrás.")) : null
    );
    host.append(
      el("div", { style: "margin-top:18px;display:flex;gap:12px;align-items:center;flex-wrap:wrap" },
        pill(h1.status),
        el("span", { class: "mono", style: "color:var(--ink-3);font-size:12.5px" },
          `P1.1 · dose-resposta · n=${h1.n}`)),
      grid
    );
    if (ef && ef.coef < 0 && h1.estimativa > 0) {
      const dentro = cr && cr.dentro_da_faixa;
      host.append(el("div", { class: "note caveat", style: "margin-top:18px" },
        el("p", { html:
          "<b>“Sustentada” aqui não quer dizer que a multi venceu.</b> Os dois coeficientes " +
          "contam uma história só: a multi começa <b>atrás</b> e encurta a distância conforme a " +
          "evidência piora. O teste pré-registrado é sobre a inclinação, não sobre quem lidera." })
      ));
      if (cr) host.append(el("p", { class: "mono", style: "font-size:12.5px;color:var(--ink-3);margin-top:10px",
        html: `Empate estimado em intensidade ${fmt(cr.intensidade)} — ` +
          (dentro ? "dentro" : "fora") + ` da faixa observada [${fmt(cr.faixa_observada[0])} · ` +
          `${fmt(cr.faixa_observada[1])}]. É extrapolação do ajuste, não observação direta.` }));
    }
  }
})();

/* braços */
(function () {
  const host = document.getElementById("arms");
  [["A", "Mono-agente", A, "--arm-a"], ["B", "Multi-agente", B, "--arm-b"]].forEach(([k, nome, d, cor]) => {
    if (!d.n) return;
    host.append(el("div", { class: "arm" },
      el("div", { class: "tag" }, el("i", { style: `background:var(${cor})` }), nome),
      el("div", { class: "big" }, pct(m4.por_braco[k])),
      el("div", { class: "unit" }, "acerto de decisão (M4)"),
      el("dl", { html:
        `<dt>execuções</dt><dd>${d.n}</dd>` +
        `<dt>concluídas sem erro</dt><dd>${d.concluidas} (${pct(d.conformidade)})</dd>` +
        `<dt>erro de comportamento</dt><dd>${d.erro_comportamento}</dd>` +
        `<dt>erro de contrato</dt><dd>${d.erro_contrato}</dd>` +
        `<dt>chamadas de LLM (média)</dt><dd>${fmt(d.llm_calls, 1)}</dd>` +
        `<dt>tokens de entrada (média)</dt><dd>${d.tokens_in ? Math.round(d.tokens_in).toLocaleString("pt-BR") : "—"}</dd>` +
        `<dt>duração (média)</dt><dd>${fmt(d.duracao_s, 1)} s</dd>`
      })
    ));
  });
})();

desenharDose(document.getElementById("dose"), R.dose_resposta);
desenharCasos(document.getElementById("casos"), R.pareado_por_caso);

/* tabela de métricas */
(function () {
  const tb = document.getElementById("metricas");
  R.metricas.forEach(m => {
    const a = m.por_braco.A, b = m.por_braco.B, d = m.diferenca;
    let cls = "", seta = "";
    if (d !== null && d !== undefined && Math.abs(d) > 1e-9) {
      const multiMelhor = m.menor_e_melhor ? d < 0 : d > 0;
      cls = multiMelhor ? "win-b" : "win-a";
      seta = multiMelhor ? "multi" : "mono";
    }
    tb.append(el("tr", { html:
      `<td class="mono">${m.id}</td><td>${m.nome}${m.menor_e_melhor ? ' <span class="mid">(menor é melhor)</span>' : ""}</td>` +
      `<td class="num">${fmt(a)}</td><td class="num">${fmt(b)}</td>` +
      `<td class="num ${cls}">${d === null || d === undefined ? "—" : (d > 0 ? "+" : "") + fmt(d)}</td>` +
      `<td class="mono mid">${seta || "—"}</td>` +
      `<td class="num mid">${m.aplicavel.A ?? 0}/${m.aplicavel.B ?? 0}</td>`
    }));
  });
})();

/* hipóteses */
(function () {
  const tb = document.getElementById("hipoteses");
  R.hipoteses.forEach(h => {
    const tr = el("tr");
    tr.append(
      el("td", { class: "mono" }, h.id + " / " + h.predicao),
      el("td", {}, h.teste),
      el("td", { class: "mono" }, h.metrica),
      el("td", { class: "num" }, String(h.n)),
      el("td", { class: "num" }, h.estimativa === null ? "—" : fmt(h.estimativa, 3)),
      el("td", { class: "num" }, h.ci_low === null ? "—" : `[${fmt(h.ci_low, 2)} · ${fmt(h.ci_high, 2)}]`),
      el("td", {}, pill(h.status)),
    );
    tb.append(tr);
  });
})();
"""

_JS_EXEC = r"""
/* ---------- explorador de trajetórias ---------- */
(function () {
  const E = window.__EXECUCOES__ || [];
  const lista = document.getElementById("execs");
  const conta = document.getElementById("conta-exec");
  if (!E.length) { lista.append(el("div", { class: "vazio" }, "Sem execuções carregadas.")); return; }

  const fArm = document.getElementById("f-arm");
  const fDec = document.getElementById("f-dec");
  const fGuard = document.getElementById("f-guard");
  const fBusca = document.getElementById("f-busca");

  const decisoes = [...new Set(E.map(e => (e.resolucao || {}).decision).filter(Boolean))].sort();
  decisoes.forEach(d => fDec.append(el("option", { value: d }, d)));

  const COR = { A: "--arm-a", B: "--arm-b" };
  const rotuloArm = a => a === "A" ? "mono" : a === "B" ? "multi" : a;

  function detalhe(e) {
    const box = el("div", { class: "detalhe" });
    if (e.handoffs.length) {
      box.append(el("h4", {}, `Handoffs (${e.handoffs.length})`));
      e.handoffs.forEach(h => box.append(el("div", { class: "hoff" },
        `${h.de} → ${h.para}  ·  após passo ${h.apos_passo}`)));
    }
    box.append(el("h4", {}, `Trajetória — ${e.passos.length} passos`));
    e.passos.forEach(p => {
      const what = el("div", { class: "what" });
      if (p.tool) what.append(el("span", { class: "tool" }, p.tool));
      if (p.reasoning) what.append(el("div", { class: "args" }, p.reasoning));
      if (p.args && Object.keys(p.args).length)
        what.append(el("div", { class: "args" }, JSON.stringify(p.args)));
      if (p.erro) what.append(el("div", { class: "res err" }, "erro: " + p.erro));
      else if (p.resultado) what.append(el("div", { class: "res" }, p.resultado));
      box.append(el("div", { class: "passo" },
        el("div", { class: "n" }, String(p.step)),
        el("div", { class: "who" }, p.agent),
        what));
    });

    const r = e.resolucao;
    box.append(el("h4", {}, "Resolução entregue"));
    if (!r) {
      box.append(el("div", { class: "resol" },
        el("div", { class: "just" }, "O agente terminou sem chamar submit_resolution.")));
    } else {
      const caixa = el("div", { class: "resol" },
        el("div", { class: "dec", style: "font-family:IBM Plex Mono,monospace;font-weight:600" },
          "decisão: " + r.decision),
        el("div", { class: "just" }, r.justification || "—"));
      if (r.evidencias.length) {
        const g = el("div", { class: "evid" });
        r.evidencias.forEach(ev => {
          g.append(
            el("span", { class: ev.resolve ? "sim" : "nao" }, ev.resolve ? "resolve" : "não resolve"),
            el("span", {}, `${ev.tool} · ${ev.field}`),
            el("span", { style: "color:var(--ink-3)" }, "step " + ev.step));
        });
        caixa.append(g);
      }
      if (r.unverified.length)
        caixa.append(el("div", { class: "args", style: "margin-top:10px" },
          "lacunas declaradas: " + r.unverified.join(" · ")));
      if (e.guard.verdict === "blocked")
        caixa.append(el("div", { class: "args", style: "margin-top:10px;color:var(--no)" },
          `guardrail bloqueou (${e.guard.failed.join(", ")}) e entregou "${e.guard.decision}"`));
      box.append(caixa);
    }
    return box;
  }

  function render() {
    lista.textContent = "";
    const termo = fBusca.value.trim().toLowerCase();
    const vis = E.filter(e =>
      (!fArm.value || e.arm === fArm.value) &&
      (!fDec.value || (e.resolucao || {}).decision === fDec.value) &&
      (!fGuard.value || (e.guard.verdict || "—") === fGuard.value) &&
      (!termo || e.case_id.toLowerCase().includes(termo)));
    conta.textContent = `${vis.length} de ${E.length}`;
    if (!vis.length) { lista.append(el("div", { class: "vazio" }, "Nenhuma execução com esses filtros.")); return; }
    vis.forEach(e => {
      const dec = (e.resolucao || {}).decision;
      const linha = el("div", { class: "exec", role: "button", tabindex: "0", "aria-expanded": "false" },
        el("div", { class: "bar", style: `background:var(${COR[e.arm] || "--ink-3"})` }),
        el("div", { class: "cid" }, e.case_id.replace("case_tkt_", "").replace("case_", "")),
        el("div", { class: "tag2" }, `${rotuloArm(e.arm)} · ${e.seed || "—"} · ${e.passos.length} passos`),
        el("div", { class: "dec", style: dec ? "" : "color:var(--unk)" }, dec || "sem resolução"),
        el("div", { class: "tag2", style: e.guard.verdict === "blocked" ? "color:var(--no)" : "" },
          e.guard.verdict || "—"));
      let aberto = null;
      const alterna = () => {
        if (aberto) { aberto.remove(); aberto = null; linha.setAttribute("aria-expanded", "false"); }
        else { aberto = detalhe(e); linha.after(aberto); linha.setAttribute("aria-expanded", "true"); }
      };
      linha.addEventListener("click", alterna);
      linha.addEventListener("keydown", ev => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); alterna(); }
      });
      lista.append(linha);
    });
  }
  [fArm, fDec, fGuard].forEach(c => c.addEventListener("change", render));
  fBusca.addEventListener("input", render);
  render();
})();
"""

_HTML = """<title>Mono ou Multi-Agente</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{css}</style>
<div class="wrap">
  <header class="masthead">
    <div class="eyebrow">Experimento E1 · arquitetura de agentes</div>
    <h1>Mono ou multi-agente?</h1>
    <p class="lede">Suporte técnico industrial sobre análise de vibração. Um agente com 18
    ferramentas contra um orquestrador com três especialistas, nos mesmos chamados, sob os mesmos
    níveis de degradação de evidência.</p>
    <div class="meta">
      <span><b>rodada</b> <span class="mono">{run_id}</span></span>
      <span><b>execuções</b> <span class="mono">{execucoes}</span></span>
      <span><b>modelo</b> <span class="mono">gemini-2.5-flash · temp 0</span></span>
      <span><b>prompt</b> <span class="mono">{prompt_version}</span></span>
      <span><b>commit</b> <span class="mono">{commit}</span></span>
      <span><b>gerado</b> <span class="mono">{gerado}</span></span>
    </div>
  </header>

  <div class="readout" id="readout"></div>
  {aviso}

  <section>
    <div class="sec-head"><span class="sec-num">6.2a</span><h2>Os dois braços</h2></div>
    <p>Mesmos 17 chamados, mesmos seeds, mesmo modelo em todos os papéis (RF33). O que muda é
    apenas a arquitetura — é isso que permite atribuir a diferença a ela.</p>
    <div class="arms" id="arms"></div>
  </section>

  <section>
    <div class="sec-head"><span class="sec-num">6.2b</span><h2>Dose-resposta</h2></div>
    <p>H1 não afirma que a multi é melhor. Afirma que <b>a vantagem da multi cresce conforme a
    evidência piora</b>. Por isso o teste é o coeficiente de interação de
    <span class="mono">M4 ~ intensidade × braço</span>, e não um contraste entre duas médias:
    dose-resposta mostra que a diferença acompanha a causa proposta, o que é evidência de
    mecanismo, não só de associação.</p>
    <figure>
      <div class="legend">
        <span><i style="background:var(--arm-a)"></i>Mono-agente</span>
        <span><i style="background:var(--arm-b)"></i>Multi-agente</span>
      </div>
      <div class="chart-scroll" id="dose"></div>
      <figcaption>Acerto de decisão (M4) em cada nível de degradação. A intensidade é medida
      <b>antes</b> da execução, sobre o conjunto fixo de recursos declarado no gabarito — nunca
      sobre as ferramentas que o agente escolheu chamar, o que deixaria a arquitetura alterar a
      própria variável explicativa.</figcaption>
    </figure>
  </section>

  <section>
    <div class="sec-head"><span class="sec-num">6.2c</span><h2>Onde as arquiteturas divergiram</h2></div>
    <p>Diferença de acerto entre multi e mono dentro de cada chamado. O caso é a unidade de
    amostragem: tratar oito seeds do mesmo chamado como oito observações independentes
    subestimaria o erro.</p>
    <figure>
      <div class="chart-scroll" id="casos"></div>
      <figcaption>Barra à direita, a multi acertou mais naquele chamado; à esquerda, a mono.</figcaption>
    </figure>
  </section>

  <section>
    <div class="sec-head"><span class="sec-num">6.2d</span><h2>Métricas M1–M16</h2></div>
    <p>Todas as métricas determinísticas, calculadas sobre o trace persistido. Nenhuma depende de
    juiz LLM — o juiz não foi executado, e nenhuma métrica de rubrica é reportada.</p>
    <div class="tbl-scroll">
      <table>
        <thead><tr><th>ID</th><th>Métrica</th><th style="text-align:right">Mono</th>
        <th style="text-align:right">Multi</th><th style="text-align:right">Δ</th><th>Favorece</th>
        <th style="text-align:right">n aplicável A/B</th></tr></thead>
        <tbody id="metricas"></tbody>
      </table>
    </div>
    <div class="note caveat">
      <p><b>“Não aplicável” nunca é zero.</b> M14 mede perda de evidência no handoff e não existe
      na arquitetura mono; M5a/M5b não se aplicam à detecção sintomática. Colapsar isso em zero
      premiaria quem não tem a etapa. A coluna <span class="mono">n aplicável</span> mostra sobre
      quantas execuções cada média foi calculada.</p>
    </div>
  </section>

  <section>
    <div class="sec-head"><span class="sec-num">6.3</span><h2>Vereditos</h2></div>
    <div class="tbl-scroll">
      <table>
        <thead><tr><th>Hipótese</th><th>Teste</th><th>Métrica</th><th style="text-align:right">n</th>
        <th style="text-align:right">Estimativa</th><th style="text-align:right">IC95</th>
        <th>Veredito</th></tr></thead>
        <tbody id="hipoteses"></tbody>
      </table>
    </div>
    <div class="note">
      <p><b>Todos os testes foram declarados antes da execução.</b> Nenhum foi escolhido depois de
      ver os dados — é o que separa este resultado de uma torcida com números.</p>
      <p><b>H3 e H4 não foram executados</b>, e nenhum veredito é emitido para eles. Não-execução
      não é resultado inconclusivo: são categorias distintas.</p>
    </div>
  </section>

  <section>
    <div class="sec-head"><span class="sec-num">6.4</span><h2>O que cada agente respondeu</h2></div>
    <p>A trajetória completa de cada execução: o que o agente chamou, o que a API devolveu, o que
    ele concluiu e se a evidência citada resolve. É a pergunta que o trace canônico sempre pôde
    responder e que nenhuma interface expunha — clique numa linha para abrir.</p>
    <div class="filtros">
      <select id="f-arm" aria-label="Filtrar por braço">
        <option value="">todos os braços</option><option value="A">mono</option><option value="B">multi</option>
      </select>
      <select id="f-dec" aria-label="Filtrar por decisão"><option value="">todas as decisões</option></select>
      <select id="f-guard" aria-label="Filtrar por guardrail">
        <option value="">guardrail: qualquer</option><option value="pass">passou</option>
        <option value="blocked">bloqueado</option>
      </select>
      <input id="f-busca" type="search" placeholder="filtrar por chamado…" aria-label="Filtrar por chamado">
      <span class="cont" id="conta-exec"></span>
    </div>
    <div class="exec-list" id="execs"></div>
  </section>

  <section>
    <div class="sec-head"><span class="sec-num">6.5</span><h2>O que este relatório não sustenta</h2></div>
    <ul class="plain">
      <li><b>A intensidade varia mais entre chamados do que entre seeds.</b> A dose-resposta
      apoia-se em heterogeneidade entre casos, o que é mais fraco que variação dentro do mesmo caso.</li>
      <li><b>A escala de severidade é decisão analítica, não medida.</b> Os pesos por modo foram
      declarados antes de olhar o resultado, mas outra escala plausível daria outro coeficiente.
      Nenhuma análise de sensibilidade foi executada.</li>
      <li><b>Falha de protocolo confunde-se com erro de decisão em M4.</b> Execuções que terminam
      sem <span class="mono">submit_resolution</span> entram como zero, misturando “não decidiu”
      com “decidiu errado”.</li>
      <li><b>A multi consome mais computação.</b> Um eventual ganho pode vir do isolamento de
      contexto <b>ou</b> de mais chamadas de LLM. Quantificado, não isolado.</li>
      <li><b>Poder estatístico limitado.</b> 17 chamados base. Ausência de significância não é
      evidência de ausência de efeito.</li>
    </ul>
  </section>

  <footer>
    Gerado por <span class="mono">agentes dashboard</span> a partir dos traces JSONL e do SQLite de
    métricas. A camada de análise não importa SDK de LLM nem exige chave de API — quem tem os
    artefatos reproduz estes números.
  </footer>
</div>
<script>window.__RELATORIO__ = {dados};
window.__EXECUCOES__ = {execucoes};</script>
<script>{js}</script>
"""

_AVISO = """<div class="note caveat"><p><b>Rodada em andamento.</b> {feitas} de {alvo} execuções
concluídas. Os números abaixo são parciais e mudam até o fim da rodada.</p></div>"""


def render_dashboard(
    relatorio: dict,
    *,
    execucoes: list[dict] | None = None,
    commit: str = "unknown",
    prompt_version: str = "1.1.0",
    gerado: str = "",
    alvo: int | None = None,
) -> str:
    """Devolve o HTML completo com o relatório embutido."""
    aviso = ""
    if alvo is not None and relatorio.get("execucoes", 0) < alvo:
        aviso = _AVISO.format(feitas=relatorio.get("execucoes", 0), alvo=alvo)
    return (
        _HTML.replace("{css}", _CSS)
        .replace("{js}", _JS + _JS_MONTA + _JS_EXEC)
        .replace("{dados}", json.dumps(relatorio, ensure_ascii=False))
        .replace("{execucoes}", json.dumps(execucoes or [], ensure_ascii=False))
        .replace("{run_id}", str(relatorio.get("run_id") or "—"))
        .replace("{execucoes}", str(relatorio.get("execucoes", 0)))
        .replace("{commit}", commit)
        .replace("{prompt_version}", prompt_version)
        .replace("{gerado}", gerado)
        .replace("{aviso}", aviso)
    )


def escrever_dashboard(destino: str | Path, html: str) -> Path:
    caminho = Path(destino)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(html, encoding="utf-8")
    return caminho
