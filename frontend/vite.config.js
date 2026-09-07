import { defineConfig } from "vite";

// O app vive em src/interfaces/web/app.js, fora desta pasta: e a MESMA fonte que o
// gerador Python embute no HTML estatico. `fs.allow` libera a leitura para o Vite,
// e assim `npm run dev` e o artefato publicado nunca divergem.
export default defineConfig({
  server: { port: 5173, open: true, fs: { allow: [".."] } },
  build: { outDir: "dist" },
});
