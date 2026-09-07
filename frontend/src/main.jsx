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

window.React = React;
window.ReactDOM = ReactDOM;
// Em desenvolvimento a plataforma fala com o BFF; sem ele, cairia nos dados
// embutidos, que não existem neste modo.
window.__API_BASE__ = import.meta.env.VITE_API_BASE || "http://localhost:8010";
window.__META__ = { gerado: "modo de desenvolvimento" };

// Sem `await` de topo: os globais acima já são atribuídos de forma síncrona antes
// do módulo carregar, e top-level await não passa no alvo de build do Vite.
import("../../src/interfaces/web/app.js");
