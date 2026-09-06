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

/* navegação da aplicação */
.nav{position:sticky;top:0;z-index:10;background:var(--ground);border-bottom:1px solid var(--rule);
  margin:0 -24px 0;padding:0 24px;display:flex;gap:2px;overflow-x:auto}
.nav button{appearance:none;background:none;border:none;border-bottom:2px solid transparent;
  font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.06em;text-transform:uppercase;
  font-weight:600;color:var(--ink-3);padding:14px 14px 11px;cursor:pointer;white-space:nowrap}
.nav button:hover{color:var(--ink-2)}
.nav button[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent)}
.nav button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.view{animation:entra .18s ease-out}
@keyframes entra{from{opacity:.4}to{opacity:1}}
@media (prefers-reduced-motion:reduce){.view{animation:none}}
@media (max-width:640px){.nav{margin:0 -16px;padding:0 16px}}
@media (max-width:640px){ .wrap{padding:32px 16px 64px} th,td{padding:8px 10px}
  .exec{grid-template-columns:14px 1fr auto} .passo{grid-template-columns:32px 1fr} }
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

_JS = r"""
const { useState, useMemo, useCallback, createElement: h, Fragment } = React;
const R = window.__RELATORIO__, E = window.__EXECUCOES__ || [];

const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? "—" : Number(v).toFixed(d);
const pct = (v) => (v === null || v === undefined) ? "—" : (v * 100).toFixed(0) + "%";
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

const STATUS = {
  sustentada: ["ok", "Sustentada"], refutada: ["no", "Refutada"],
  refutada_direcao_oposta: ["no", "Refutada na direção oposta"],
  inconclusiva: ["unk", "Inconclusiva"], nao_executada: ["unk", "Não executada"],
};
const Pill = ({ status }) => {
  const [cls, rot] = STATUS[status] || ["unk", status];
  return h("span", { className: "pill " + cls }, h("i", { className: "dot" }), rot);
};
const SecHead = ({ num, children }) =>
  h("div", { className: "sec-head" }, h("span", { className: "sec-num" }, num), h("h2", null, children));

/* ---------------- gráficos ---------------- */
function DoseChart({ pontos }) {
  if (!pontos.length) return h("p", null, "Sem dados de dose ainda.");
  const W = 860, H = 340, m = { t: 18, r: 24, b: 52, l: 56 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const xs = pontos.map(p => p.intensidade);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const sx = v => m.l + (x1 === x0 ? iw / 2 : (v - x0) / (x1 - x0) * iw);
  const sy = v => m.t + ih - v * ih;
  const mono = "IBM Plex Mono, monospace";
  const kids = [];
  for (let g = 0; g <= 4; g++) {
    const v = g / 4, y = sy(v);
    kids.push(h("line", { key: "g" + g, x1: m.l, x2: m.l + iw, y1: y, y2: y, stroke: "var(--rule)", strokeWidth: 1 }));
    kids.push(h("text", { key: "gl" + g, x: m.l - 10, y: y + 4, fill: "var(--ink-3)", fontSize: 11,
      textAnchor: "end", fontFamily: mono }, v.toFixed(2)));
  }
  pontos.forEach((p, i) => {
    const x = sx(p.intensidade);
    kids.push(h("line", { key: "t" + i, x1: x, x2: x, y1: m.t + ih, y2: m.t + ih + 5, stroke: "var(--ink-3)" }));
    kids.push(h("text", { key: "tv" + i, x, y: m.t + ih + 20, fill: "var(--ink-2)", fontSize: 11,
      textAnchor: "middle", fontFamily: mono }, p.intensidade.toFixed(2)));
    kids.push(h("text", { key: "ts" + i, x, y: m.t + ih + 35, fill: "var(--ink-3)", fontSize: 10,
      textAnchor: "middle", fontFamily: mono }, p.seed));
  });
  kids.push(h("text", { key: "ylab", x: m.l - 10, y: m.t - 4, fill: "var(--ink-3)", fontSize: 11,
    textAnchor: "end", fontFamily: mono }, "M4"));
  kids.push(h("text", { key: "xlab", x: m.l + iw / 2, y: H - 6, fill: "var(--ink-3)", fontSize: 11.5,
    textAnchor: "middle" }, "intensidade de degradação  →  evidência pior"));
  [["A", "var(--arm-a)"], ["B", "var(--arm-b)"]].forEach(([arm, cor]) => {
    const pts = pontos.filter(p => p.por_braco[arm] !== null && p.por_braco[arm] !== undefined);
    if (!pts.length) return;
    kids.push(h("polyline", { key: "l" + arm, fill: "none", stroke: cor, strokeWidth: 2.5,
      strokeLinejoin: "round", points: pts.map(p => `${sx(p.intensidade)},${sy(p.por_braco[arm])}`).join(" ") }));
    pts.forEach((p, i) => kids.push(h("circle", { key: `c${arm}${i}`, cx: sx(p.intensidade),
      cy: sy(p.por_braco[arm]), r: 5, fill: cor, stroke: "var(--surface)", strokeWidth: 2 })));
  });
  return h("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Acerto de decisão por intensidade de degradação, em cada braço" }, kids);
}

function CasosChart({ pareado }) {
  if (!pareado) return null;
  const entradas = Object.entries(pareado.por_caso);
  const W = 860, linha = 21, m = { t: 10, r: 20, b: 30, l: 170 };
  const H = m.t + entradas.length * linha + m.b, iw = W - m.l - m.r;
  const lim = Math.max(0.35, ...entradas.map(([, v]) => Math.abs(v)));
  const sx = v => m.l + (v + lim) / (2 * lim) * iw;
  const zero = sx(0), mono = "IBM Plex Mono, monospace";
  const kids = [h("line", { key: "z", x1: zero, x2: zero, y1: m.t, y2: m.t + entradas.length * linha,
    stroke: "var(--ink-3)", strokeWidth: 1.5 })];
  entradas.forEach(([caso, v], i) => {
    const y = m.t + i * linha + linha / 2;
    const cor = v > 0 ? "var(--arm-b)" : v < 0 ? "var(--arm-a)" : "var(--ink-3)";
    kids.push(h("rect", { key: "r" + i, x: Math.min(zero, sx(v)), y: y - 6,
      width: Math.abs(sx(v) - zero) || 1.5, height: 12, fill: cor, rx: 1 }));
    kids.push(h("text", { key: "n" + i, x: m.l - 12, y: y + 4, fill: "var(--ink-2)", fontSize: 11,
      textAnchor: "end", fontFamily: mono }, caso.replace("case_tkt_", "").replace("case_", "")));
  });
  kids.push(h("text", { key: "la", x: m.l, y: H - 8, fill: "var(--arm-a)", fontSize: 11, fontFamily: mono },
    "← mono acerta mais"));
  kids.push(h("text", { key: "lb", x: W - m.r, y: H - 8, fill: "var(--arm-b)", fontSize: 11,
    textAnchor: "end", fontFamily: mono }, "multi acerta mais →"));
  return h("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Diferença de acerto entre multi e mono, por caso" }, kids);
}

/* ---------------- visão: resumo ---------------- */
function Resumo() {
  const m4 = R.metricas.find(m => m.id === "M4") || { por_braco: {} };
  const h1 = R.hipoteses.find(x => x.id === "H1");
  const p = R.pareado_por_caso;
  const a = m4.por_braco.A, b = m4.por_braco.B;

  let frase, detalhe;
  if (a == null || b == null) {
    frase = "Ainda sem acerto de decisão nos dois braços.";
    detalhe = "A rodada precisa concluir execuções em mono e multi antes de comparar.";
  } else if (!p || p.ic_low === null || (p.ic_low <= 0 && p.ic_high >= 0)) {
    frase = "Mono e multi não se distinguem nesta amostra.";
    detalhe = "A diferença pareada por caso tem intervalo de confiança que cruza o zero: os dados " +
      "não sustentam dizer que uma arquitetura acerta mais que a outra.";
  } else {
    frase = `A arquitetura ${p.diferenca_media > 0 ? "multi-agente" : "mono-agente"} acerta mais.`;
    detalhe = `Diferença pareada por caso de ${fmt(p.diferenca_media)} em M4, IC95 ` +
      `[${fmt(p.ic_low)} · ${fmt(p.ic_high)}], reamostrando casos.`;
  }

  const ef = h1 && h1.detalhe ? h1.detalhe.efeito_principal : null;
  const cr = h1 && h1.detalhe ? h1.detalhe.cruzamento : null;

  return h("div", { className: "view" },
    h("div", { className: "readout" },
      h("div", { className: "eyebrow" }, "Pergunta central · H1"),
      h("div", { className: "verdict" }, frase),
      h("p", null, detalhe),
      h1 && h1.estimativa !== null && h(Fragment, null,
        h("div", { style: { marginTop: 18, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" } },
          h(Pill, { status: h1.status }),
          h("span", { className: "mono", style: { color: "var(--ink-3)", fontSize: 12.5 } },
            `P1.1 · dose-resposta · n=${h1.n}`)),
        h("div", { className: "coefs" },
          h("div", { className: "coef" },
            h("div", { className: "k" }, "Interação  intensidade × braço"),
            h("div", { className: "v" }, fmt(h1.estimativa)),
            h("div", { className: "ci" }, `IC95 [${fmt(h1.ci_low)} · ${fmt(h1.ci_high)}]`),
            h("div", { className: "q" }, "A distância entre os braços muda com a degradação? " +
              "Positivo = a multi encurta. É o teste pré-registrado de P1.1.")),
          ef && h("div", { className: "coef" },
            h("div", { className: "k" }, "Efeito principal  braço multi"),
            h("div", { className: "v" }, fmt(ef.coef)),
            h("div", { className: "ci" }, `IC95 [${fmt(ef.ci_low)} · ${fmt(ef.ci_high)}]`),
            h("div", { className: "q" }, "Quem está na frente com evidência íntegra? " +
              "Negativo = a multi está atrás."))),
        ef && ef.coef < 0 && h1.estimativa > 0 && h(Fragment, null,
          h("div", { className: "note caveat", style: { marginTop: 18 } },
            h("p", null,
              h("b", null, "“Sustentada” aqui não quer dizer que a multi venceu."),
              " Os dois coeficientes contam uma história só: a multi começa ",
              h("b", null, "atrás"), " e encurta a distância conforme a evidência piora. ",
              "O teste pré-registrado é sobre a inclinação, não sobre quem lidera.")),
          cr && h("p", { className: "mono", style: { fontSize: 12.5, color: "var(--ink-3)", marginTop: 10 } },
            `Empate estimado em intensidade ${fmt(cr.intensidade)} — ` +
            (cr.dentro_da_faixa ? "dentro" : "fora") +
            ` da faixa observada [${fmt(cr.faixa_observada[0])} · ${fmt(cr.faixa_observada[1])}]. ` +
            "É extrapolação do ajuste, não observação direta.")))),

    h("section", null,
      h(SecHead, { num: "6.2a" }, "Os dois braços"),
      h("p", null, "Mesmos 17 chamados, mesmos seeds, mesmo modelo em todos os papéis (RF33). ",
        "O que muda é apenas a arquitetura — é isso que permite atribuir a diferença a ela."),
      h("div", { className: "arms" },
        [["A", "Mono-agente", "--arm-a"], ["B", "Multi-agente", "--arm-b"]].map(([k, nome, cor]) => {
          const d = R.bracos[k]; if (!d || !d.n) return null;
          return h("div", { className: "arm", key: k },
            h("div", { className: "tag" }, h("i", { style: { background: `var(${cor})` } }), nome),
            h("div", { className: "big" }, pct(m4.por_braco[k])),
            h("div", { className: "unit" }, "acerto de decisão (M4)"),
            h("dl", null,
              h("dt", null, "execuções"), h("dd", null, d.n),
              h("dt", null, "concluídas sem erro"), h("dd", null, `${d.concluidas} (${pct(d.conformidade)})`),
              h("dt", null, "erro de comportamento"), h("dd", null, d.erro_comportamento),
              h("dt", null, "erro de contrato"), h("dd", null, d.erro_contrato),
              h("dt", null, "chamadas de LLM (média)"), h("dd", null, fmt(d.llm_calls, 1)),
              h("dt", null, "tokens de entrada (média)"),
              h("dd", null, d.tokens_in ? Math.round(d.tokens_in).toLocaleString("pt-BR") : "—"),
              h("dt", null, "duração (média)"), h("dd", null, fmt(d.duracao_s, 1) + " s")));
        }))));
}

/* ---------------- visão: dose-resposta ---------------- */
function Dose() {
  return h("div", { className: "view" },
    h("section", { style: { marginTop: 28 } },
      h(SecHead, { num: "6.2b" }, "Dose-resposta"),
      h("p", null, "H1 não afirma que a multi é melhor. Afirma que ",
        h("b", null, "a vantagem da multi cresce conforme a evidência piora"),
        ". Por isso o teste é o coeficiente de interação de ",
        h("span", { className: "mono" }, "M4 ~ intensidade × braço"),
        ", e não um contraste entre duas médias: dose-resposta mostra que a diferença acompanha a ",
        "causa proposta, o que é evidência de mecanismo, não só de associação."),
      h("figure", null,
        h("div", { className: "legend" },
          h("span", null, h("i", { style: { background: "var(--arm-a)" } }), "Mono-agente"),
          h("span", null, h("i", { style: { background: "var(--arm-b)" } }), "Multi-agente")),
        h("div", { className: "chart-scroll" }, h(DoseChart, { pontos: R.dose_resposta })),
        h("figcaption", null, "Acerto de decisão (M4) em cada nível de degradação. A intensidade é ",
          "medida ", h("b", null, "antes"), " da execução, sobre o conjunto fixo de recursos declarado ",
          "no gabarito — nunca sobre as ferramentas que o agente escolheu chamar, o que deixaria a ",
          "arquitetura alterar a própria variável explicativa."))),
    h("section", null,
      h(SecHead, { num: "6.2c" }, "Onde as arquiteturas divergiram"),
      h("p", null, "Diferença de acerto entre multi e mono dentro de cada chamado. O caso é a ",
        "unidade de amostragem: tratar oito seeds do mesmo chamado como oito observações ",
        "independentes subestimaria o erro."),
      h("figure", null,
        h("div", { className: "chart-scroll" }, h(CasosChart, { pareado: R.pareado_por_caso })),
        h("figcaption", null, "Barra à direita, a multi acertou mais naquele chamado; à esquerda, a mono."))));
}

/* ---------------- visão: métricas ---------------- */
function Metricas() {
  return h("div", { className: "view" },
    h("section", { style: { marginTop: 28 } },
      h(SecHead, { num: "6.2d" }, "Métricas M1–M16"),
      h("p", null, "Todas as métricas determinísticas, calculadas sobre o trace persistido. ",
        "Nenhuma depende de juiz LLM — o juiz não foi executado, e nenhuma métrica de rubrica é reportada."),
      h("div", { className: "tbl-scroll" },
        h("table", null,
          h("thead", null, h("tr", null,
            h("th", null, "ID"), h("th", null, "Métrica"),
            h("th", { style: { textAlign: "right" } }, "Mono"),
            h("th", { style: { textAlign: "right" } }, "Multi"),
            h("th", { style: { textAlign: "right" } }, "Δ"),
            h("th", null, "Favorece"),
            h("th", { style: { textAlign: "right" } }, "n aplicável A/B"))),
          h("tbody", null, R.metricas.map(m => {
            const d = m.diferenca;
            let cls = "", quem = "—";
            if (d != null && Math.abs(d) > 1e-9) {
              const multiMelhor = m.menor_e_melhor ? d < 0 : d > 0;
              cls = multiMelhor ? "win-b" : "win-a";
              quem = multiMelhor ? "multi" : "mono";
            }
            return h("tr", { key: m.id },
              h("td", { className: "mono" }, m.id),
              h("td", null, m.nome, m.menor_e_melhor &&
                h("span", { className: "mid" }, " (menor é melhor)")),
              h("td", { className: "num" }, fmt(m.por_braco.A)),
              h("td", { className: "num" }, fmt(m.por_braco.B)),
              h("td", { className: "num " + cls }, d == null ? "—" : (d > 0 ? "+" : "") + fmt(d)),
              h("td", { className: "mono mid" }, quem),
              h("td", { className: "num mid" }, `${m.aplicavel.A || 0}/${m.aplicavel.B || 0}`));
          })))),
      h("div", { className: "note caveat" },
        h("p", null, h("b", null, "“Não aplicável” nunca é zero."),
          " M14 mede perda de evidência no handoff e não existe na arquitetura mono; M5a/M5b não ",
          "se aplicam à detecção sintomática. Colapsar isso em zero premiaria quem não tem a etapa. ",
          "A coluna ", h("span", { className: "mono" }, "n aplicável"),
          " mostra sobre quantas execuções cada média foi calculada."))),
    h("section", null,
      h(SecHead, { num: "6.3" }, "Vereditos"),
      h("div", { className: "tbl-scroll" },
        h("table", null,
          h("thead", null, h("tr", null,
            h("th", null, "Hipótese"), h("th", null, "Teste"), h("th", null, "Métrica"),
            h("th", { style: { textAlign: "right" } }, "n"),
            h("th", { style: { textAlign: "right" } }, "Estimativa"),
            h("th", { style: { textAlign: "right" } }, "IC95"), h("th", null, "Veredito"))),
          h("tbody", null, R.hipoteses.map((x, i) => h("tr", { key: i },
            h("td", { className: "mono" }, `${x.id} / ${x.predicao}`),
            h("td", null, x.teste),
            h("td", { className: "mono" }, x.metrica),
            h("td", { className: "num" }, x.n),
            h("td", { className: "num" }, x.estimativa == null ? "—" : fmt(x.estimativa, 3)),
            h("td", { className: "num" }, x.ci_low == null ? "—" : `[${fmt(x.ci_low, 2)} · ${fmt(x.ci_high, 2)}]`),
            h("td", null, h(Pill, { status: x.status }))))))),
      h("div", { className: "note" },
        h("p", null, h("b", null, "Todos os testes foram declarados antes da execução."),
          " Nenhum foi escolhido depois de ver os dados — é o que separa este resultado de uma ",
          "torcida com números."),
        h("p", null, h("b", null, "H3 e H4 não foram executados"),
          ", e nenhum veredito é emitido para eles. Não-execução não é resultado inconclusivo: ",
          "são categorias distintas."))));
}

/* ---------------- visão: trajetórias ---------------- */
const rotuloArm = a => a === "A" ? "mono" : a === "B" ? "multi" : a;

function Passo({ p }) {
  return h("div", { className: "passo" },
    h("div", { className: "n" }, String(p.step)),
    h("div", { className: "who" }, p.agent),
    h("div", { className: "what" },
      p.tool && h("span", { className: "tool" }, p.tool),
      p.reasoning && h("div", { className: "args" }, p.reasoning),
      p.args && Object.keys(p.args).length > 0 && h("div", { className: "args" }, JSON.stringify(p.args)),
      p.erro
        ? h("div", { className: "res err" }, "erro: " + p.erro)
        : p.resultado && h("div", { className: "res" }, p.resultado)));
}

function Detalhe({ e }) {
  const r = e.resolucao;
  return h("div", { className: "detalhe" },
    e.handoffs.length > 0 && h(Fragment, null,
      h("h4", null, `Handoffs (${e.handoffs.length})`),
      e.handoffs.map((x, i) => h("div", { className: "hoff", key: i },
        `${x.de} → ${x.para}  ·  após passo ${x.apos_passo}`))),
    h("h4", null, `Trajetória — ${e.passos.length} passos`),
    e.passos.map((p, i) => h(Passo, { p, key: i })),
    h("h4", null, "Resolução entregue"),
    !r
      ? h("div", { className: "resol" },
          h("div", { className: "just" }, "O agente terminou sem chamar submit_resolution."))
      : h("div", { className: "resol" },
          h("div", { className: "mono", style: { fontWeight: 600 } }, "decisão: " + r.decision),
          h("div", { className: "just" }, r.justification || "—"),
          r.evidencias.length > 0 && h("div", { className: "evid" },
            r.evidencias.map((ev, i) => h(Fragment, { key: i },
              h("span", { className: ev.resolve ? "sim" : "nao" }, ev.resolve ? "resolve" : "não resolve"),
              h("span", null, `${ev.tool} · ${ev.field}`),
              h("span", { style: { color: "var(--ink-3)" } }, "step " + ev.step)))),
          r.unverified.length > 0 && h("div", { className: "args", style: { marginTop: 10 } },
            "lacunas declaradas: " + r.unverified.join(" · ")),
          e.guard.verdict === "blocked" && h("div", { className: "args",
            style: { marginTop: 10, color: "var(--no)" } },
            `guardrail bloqueou (${e.guard.failed.join(", ")}) e entregou "${e.guard.decision}"`)));
}

function Linha({ e }) {
  const [aberto, setAberto] = useState(false);
  const dec = (e.resolucao || {}).decision;
  const alterna = useCallback(() => setAberto(v => !v), []);
  return h(Fragment, null,
    h("div", { className: "exec", role: "button", tabIndex: 0, "aria-expanded": aberto,
      onClick: alterna,
      onKeyDown: ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); alterna(); } } },
      h("div", { className: "bar", style: { background: `var(--arm-${e.arm === "A" ? "a" : "b"})` } }),
      h("div", { className: "cid" }, e.case_id.replace("case_tkt_", "").replace("case_", "")),
      h("div", { className: "tag2" }, `${rotuloArm(e.arm)} · ${e.seed || "—"} · ${e.passos.length} passos`),
      h("div", { className: "dec", style: dec ? null : { color: "var(--unk)" } }, dec || "sem resolução"),
      h("div", { className: "tag2", style: e.guard.verdict === "blocked" ? { color: "var(--no)" } : null },
        e.guard.verdict || "—")),
    aberto && h(Detalhe, { e }));
}

function Trajetorias() {
  const [arm, setArm] = useState("");
  const [dec, setDec] = useState("");
  const [guard, setGuard] = useState("");
  const [busca, setBusca] = useState("");
  const decisoes = useMemo(
    () => [...new Set(E.map(e => (e.resolucao || {}).decision).filter(Boolean))].sort(), []);
  const vis = useMemo(() => {
    const t = busca.trim().toLowerCase();
    return E.filter(e =>
      (!arm || e.arm === arm) &&
      (!dec || (e.resolucao || {}).decision === dec) &&
      (!guard || (e.guard.verdict || "—") === guard) &&
      (!t || e.case_id.toLowerCase().includes(t)));
  }, [arm, dec, guard, busca]);

  return h("div", { className: "view" },
    h("section", { style: { marginTop: 28 } },
      h(SecHead, { num: "6.4" }, "O que cada agente respondeu"),
      h("p", null, "A trajetória completa de cada execução: o que o agente chamou, o que a API ",
        "devolveu, o que ele concluiu e se a evidência citada resolve. É a pergunta que o trace ",
        "canônico sempre pôde responder e que nenhuma interface expunha — clique numa linha para abrir."),
      h("div", { className: "filtros" },
        h("select", { value: arm, onChange: e => setArm(e.target.value), "aria-label": "Filtrar por braço" },
          h("option", { value: "" }, "todos os braços"),
          h("option", { value: "A" }, "mono"), h("option", { value: "B" }, "multi")),
        h("select", { value: dec, onChange: e => setDec(e.target.value), "aria-label": "Filtrar por decisão" },
          h("option", { value: "" }, "todas as decisões"),
          decisoes.map(d => h("option", { key: d, value: d }, d))),
        h("select", { value: guard, onChange: e => setGuard(e.target.value), "aria-label": "Filtrar por guardrail" },
          h("option", { value: "" }, "guardrail: qualquer"),
          h("option", { value: "pass" }, "passou"), h("option", { value: "blocked" }, "bloqueado")),
        h("input", { type: "search", value: busca, onChange: e => setBusca(e.target.value),
          placeholder: "filtrar por chamado…", "aria-label": "Filtrar por chamado" }),
        h("span", { className: "cont" }, `${vis.length} de ${E.length}`)),
      h("div", { className: "exec-list" },
        vis.length === 0
          ? h("div", { className: "vazio" }, "Nenhuma execução com esses filtros.")
          : vis.map(e => h(Linha, { e, key: e.id })))));
}

/* ---------------- visão: limitações ---------------- */
function Limitacoes() {
  const itens = [
    ["A intensidade varia mais entre chamados do que entre seeds.",
      "A dose-resposta apoia-se em heterogeneidade entre casos, o que é mais fraco que variação dentro do mesmo caso."],
    ["A escala de severidade é decisão analítica, não medida.",
      "Os pesos por modo foram declarados antes de olhar o resultado, mas outra escala plausível daria outro coeficiente. Nenhuma análise de sensibilidade foi executada."],
    ["Falha de protocolo confunde-se com erro de decisão em M4.",
      "Execuções que terminam sem submit_resolution entram como zero, misturando “não decidiu” com “decidiu errado”."],
    ["A citação de evidência tem contrato subespecificado.",
      "Mesmo após a correção do comparador, a maioria das referências não resolve — parte é o agente errando, parte é ambiguidade do contrato, e os dois não estão separados."],
    ["No braço multi, o índice do passo é inalcançável.",
      "Cada papel conta passos no seu próprio loop enquanto o trace numera globalmente. M6 penaliza o braço B por um motivo que não é arquitetura."],
    ["A multi consome mais computação.",
      "Um eventual ganho pode vir do isolamento de contexto ou de mais chamadas de LLM. Quantificado, não isolado."],
    ["Poder estatístico limitado.",
      "17 chamados base. Ausência de significância não é evidência de ausência de efeito."],
    ["O juiz LLM não foi executado.",
      "Nenhuma métrica de rubrica é reportada. Métrica de rubrica sem meta-avaliação tem erro desconhecido; em vez de reportá-la com ressalva, não se reporta."],
  ];
  return h("div", { className: "view" },
    h("section", { style: { marginTop: 28 } },
      h(SecHead, { num: "6.5" }, "O que este relatório não sustenta"),
      h("p", null, "Registradas porque um resultado sem os seus limites declarados é mais frágil, ",
        "não mais forte."),
      h("ul", { className: "plain" }, itens.map(([t, d], i) =>
        h("li", { key: i }, h("b", null, t), " ", d)))));
}

/* ---------------- aplicação ---------------- */
const VIEWS = [
  ["resumo", "Resumo", Resumo],
  ["dose", "Dose-resposta", Dose],
  ["metricas", "Métricas e vereditos", Metricas],
  ["trajetorias", `Trajetórias (${E.length})`, Trajetorias],
  ["limites", "Limitações", Limitacoes],
];

function App() {
  const [ativa, setAtiva] = useState("resumo");
  const Atual = (VIEWS.find(v => v[0] === ativa) || VIEWS[0])[2];
  return h(Fragment, null,
    h("nav", { className: "nav", role: "tablist", "aria-label": "Seções do relatório" },
      VIEWS.map(([id, rot]) => h("button", { key: id, role: "tab", "aria-selected": ativa === id,
        onClick: () => setAtiva(id) }, rot))),
    h(Atual, null));
}

ReactDOM.createRoot(document.getElementById("app")).render(h(App));
"""

_HTML = """<title>Mono ou Multi-Agente</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{css}</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js"></script>
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
  {aviso}
  <div id="app"></div>
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
        .replace("{js}", _JS)
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
