/**
 * Entrada do modo de desenvolvimento.
 *
 * O componente não vive aqui: vive em `src/interfaces/web/app.js`, a mesma fonte
 * que o gerador Python embute no HTML estático. Este arquivo só monta o ambiente
 * que aquele código espera — React nos globais e a origem da API — e o importa.
 * Duplicar o componente aqui criaria duas verdades.
 */
import React from "react";
import ReactDOM from "react-dom/client";

import "../../src/interfaces/web/app.css";

import relatorio from "./data/relatorio.json";
import execucoes from "./data/execucoes.json";

window.React = React;
window.ReactDOM = ReactDOM;

// O BFF só entra quando alguém o declara. Antes esta linha apontava para
// localhost:8010 incondicionalmente, e como o BFF não existe o front abria com
// "Failed to fetch" — enquanto os JSON que `npm run dados` gera ficavam sem uso.
// O componente já sabe ler dados embutidos (`__RELATORIO__`/`__EXECUCOES__`); é o
// mesmo caminho do HTML estático, então dev e artefato publicado mostram o mesmo.
// Os dados gerados ficam sempre disponíveis: se o BFF cair, o relatório continua de pé.
// `__API_BASE__` tem precedência no app.js, então declarar o BFF ativa console e triagem
// sem perder essa reserva.
window.__RELATORIO__ = relatorio;
window.__EXECUCOES__ = execucoes;
const base = import.meta.env.VITE_API_BASE;
if (base) window.__API_BASE__ = base;
window.__META__ = {
  gerado: base ? "modo de desenvolvimento (BFF)" : `dados de ${relatorio.run_id}`,
};

// Sem `await` de topo: os globais acima já são atribuídos de forma síncrona antes
// do módulo carregar, e top-level await não passa no alvo de build do Vite.
import("../../src/interfaces/web/app.js");
