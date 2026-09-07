# Front da plataforma

React 18 + Vite. O componente **não vive aqui**: vive em
[`src/interfaces/web/app.js`](../src/interfaces/web/app.js), que é a mesma fonte que o gerador
Python embute no HTML estático. `src/main.jsx` só monta o ambiente e o importa — duplicar o
componente criaria duas verdades sobre os mesmos números.

## Rodar local

Dois processos. Primeiro o BFF, na raiz do repositório:

```bash
uv run uvicorn src.interfaces.api:app --port 8010 --reload
```

Depois o front, nesta pasta:

```bash
npm install     # 1x
npm run dev     # http://localhost:5173
```

A plataforma detecta a porta 5173 e passa a consultar o BFF em `http://localhost:8010`.
Para apontar para outro host, defina `VITE_API_BASE`.

## Gerar o estático

```bash
npm run dados   # regenera docs/relatorio/index.html a partir dos traces
```

O estático não precisa de backend: os dados vão embutidos e o console de atendimento aparece
desabilitado, com a instrução de como subir o BFF.

## Console de atendimento

Abrir um chamado pela interface **enfileira** a tarefa. Quem executa é o worker:

```bash
uv run agentes run --run-id console
```

Cada execução consome cota do Gemini.
