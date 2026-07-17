# Luna — Guia para Agentes de Código

## Stack

- **Runtime:** Python 3.13 via `uv`
- **Dependency manager:** `uv` (pip compatível)
- **Config:** `pyproject.toml` (Ruff, pytest, mypy)
- **Pre-commit:** Ruff (lint + format) + pytest
- **Entry points:** `app.py`, `api.py`, `luna_terminal.py`

## Comandos essenciais

```bash
uv run python app.py          # iniciar backend completo
uv run python api.py          # iniciar servidor FastAPI
uv run python luna_terminal.py # terminal interativo
uv run pytest                 # rodar testes
uv run ruff check .           # lint
uv run ruff format .          # formatar
uv run mypy .                 # type check
```

## Estrutura

- `luna_core.py` — loop ReAct principal, orquestração
- `brain/` — LLM providers, agent tools, memória, segurança
- `actions/` — tools (sistema, navegador, mídia, etc.)
- `voice/` — TTS + STT
- `vision/` — captura de tela + OCR
- `api.py` — servidor REST FastAPI
- `config/` — JSON de personalidade, apps, dispositivos

## Loop ReAct (multi-step) + Interaction Engine

O método `_run_autonomous_loop` em `luna_core.py` executa até `MAX_STEPS`. O LLM gera **objetivos**, e o **Interaction Router** decide a melhor ferramenta.

### Arquitetura
```
┌──────────────────────────────────────────────┐
│                 LunaOS                        │
├──────────────────────────────────────────────┤
│ brain/                                       │
│   ├── planner.py         → decide objetivos   │
│   ├── reasoning.py       → Claude/o3/GPT     │
│   ├── task_manager.py    → controla tarefas  │
│   └── memory.py          → aprende estratégias│
│                                                │
│ interaction/                                  │
│   ├── router.py          → escolhe ferramenta │
│   ├── registry.py        → catálogo de tools │
│   ├── verifier.py        → confirma sucesso  │
│   └── tools/                                  │
│       ├── base_tool.py    → interface padrão  │
│       ├── bash_tool.py    → terminal         │
│       ├── python_tool.py  → Python runner    │
│       └── api_tool.py     → APIs externas    │
│                                                │
│ learning/                                     │
│   ├── strategy_memory.py → aprende estratégias│
│                                                │
│ tests/                                        │
│   └── test_puter_models.py → testa todos     │
│                                                │
│ logs/                                         │
│   ├── actions.json                            │
│   └── errors.json                             │
└──────────────────────────────────────────────┘
```

### Fluxo Interaction Engine:
1. **Conselho de IAs** (múltiplos modelos) deliberam sobre o objetivo
2. **Router** consulta `registry.py` para encontrar ferramentas candidatas
3. **Executor** tenta ferramentas em ordem de prioridade (fallback automático)
4. **Verifier** checa sucesso por sinais múltiplos (janela aberta, arquivo criado, saída esperada)
5. **Strategy Memory** aprende qual ferramenta funciona melhor para cada tarefa

### Bug conhecido (fixado):
- Quando o LLM vaza tool_calls em texto (fallback), o histórico não incluía `tool_calls` na mensagem assistant, quebrando chamadas seguintes. Agora normaliza para dict corretamente.

## Provedores LLM (apenas cloud)

Modelos locais (Ollama) estão **desabilitados permanentemente**. O `generate()` em `brain/llm.py` faz cascade apenas por provedores cloud:

1. Mistral → 2. Gemini → 3. OpenRouter → 4. Completions.me → 5. Chutes.ai → 6. GitHub Models → 7. Naga AI → 8. Best AI → 9. Groq → 10. FreeTheAi → 11. Puter

Configure ao menos uma `API_KEY` no `.env` para que o Luna funcione.

## Puter LLM (developer tier)

Puter oferece modelos OpenAI/Anthropic/xAI/Meta/DeepSeek via API com custo ~$0.0001/req:
- `gpt-5.2` — melhor para dev (pesado, agente autônomo)
- `o3` — raciocínio
- `claude-sonnet-5` — agente autônomo
- `grok-3` — xAI
- `deepseek-r1-0528` — raciocínio
- `llama-4-maverick` — Meta
- `gpt-4o-mini` — econômico para usuários

Config: `PUTER_LLM_HEAVY`, `PUTER_LLM_MAIN`, `PUTER_LLM_FAST`, `PUTER_LLM_REASONING`, `PUTER_LLM_AGENT`, `PUTER_LLM_CODING` no `.env`

## Cascade Configurável

A ordem dos provedores LLM é definida por `LUNA_CASCADE_ORDER` no `.env` (padrão: `mistral,gemini,openrouter,completions,chutes,github,naga,bestai,groq,freetheai,puter`).

### Uso via API
- `GET /api/models/status` — mostra cascade atual + providers
- `POST /api/cascade` — `{"order": "puter,groq,gemini"}` altera em tempo real
- `POST /api/crew` — `{"enabled": true}` ativa/desativa Crew Mode

### Sintaxe provider/model
Em qualquer chamada, use `provider/model` para forçar um provedor específico:
- `puter/gpt-5.2` — usa Puter com gpt-5.2
- `groq/qwen3-32b` — usa Groq com Qwen3
- `gemini/gemini-2.5-flash` — usa Gemini diretamente

## Crew Mode (multi-LLM especializado)

Quando ativo (padrão: true), cada tipo de tarefa usa o melhor modelo:

| Tarefa | Modelo |
|--------|--------|
| Chat/Conversa | `grok-3` (criatividade) |
| Código | `gpt-5.2` |
| Raciocínio/Planejamento | `o3` |
| Escrita Criativa | `claude-sonnet-5` |
| Fatos/Pesquisa | `deepseek-r1-0528` |
| Comandos rápidos | `gpt-4o-mini` |

Configurável via `.env`: `CREW_CHAT`, `CREW_CODING`, `CREW_REASONING`, etc.

## Packaging (Tauri Desktop)

```bash
cd luna-desktop
npm install                     # instalar dependências frontend
npm run tauri build             # gerar .deb + .rpm + AppImage

# Flatpak (requer flatpak-builder)
flatpak-builder --user --force-clean --repo=flatpak-repo flatpak-build flatpak/io.github.milogol2822.Luna.yml
flatpak build-bundle flatpak-repo luna-<versão>-x86_64.flatpak io.github.milogol2822.Luna
```

**Arquivos gerados** (após `npm run tauri build`):
- `src-tauri/target/release/bundle/deb/Luna_<versão>_amd64.deb`
- `src-tauri/target/release/bundle/rpm/Luna-<versão>-1.x86_64.rpm`
- `src-tauri/target/release/bundle/appimage/Luna_<versão>_x86_64.AppImage`

**CI/CD**: `.github/workflows/release.yml` — executa em tags `v*`, gera todos os pacotes e faz upload automático para a Release do GitHub.

## Variáveis de ambiente relevantes

- `LUNA_MAX_STEPS=15` — limite de iterações do loop ReAct
- `LUNA_API_HOST`, `LUNA_API_PORT` — host/porta da API
- `LUNA_MAX_HISTORY=10` — pares de conversa mantidos em memória
