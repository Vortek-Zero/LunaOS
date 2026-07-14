# Luna AI Desktop

Cliente desktop Tauri + SvelteKit para a assistente pessoal Luna.

## Pré-requisitos

- Node.js 20+
- Rust nightly (para Tauri)
- Backend Luna rodando em `http://localhost:5050`

## Desenvolvimento

```bash
npm install
npm run tauri dev
```

## Build

```bash
npm run tauri build
```

O binário será gerado em `src-tauri/target/release/`.
