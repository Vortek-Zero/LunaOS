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

## Loop ReAct (multi-step)

O método `_run_autonomous_loop` em `luna_core.py` executa até `MAX_STEPS` (padrão: 15, configurável via `LUNA_MAX_STEPS` no `.env`). O LLM recebe tools nativas (function calling) e decide quando usá-las.

### Fluxo:
1. LLM é chamado com `tools=LUNA_TOOLS`
2. Se retorna `tool_calls` → executa e adiciona resultado ao histórico
3. Se retorna texto sem `tool_calls` → resposta final
4. Reflexão opcional: se ferramentas foram usadas mas objetivo não foi cumprido, continua

### Bug conhecido (fixado):
- Quando o LLM vaza tool_calls em texto (fallback), o histórico não incluía `tool_calls` na mensagem assistant, quebrando chamadas seguintes. Agora normaliza para dict corretamente.

## Provedores LLM (apenas cloud)

Modelos locais (Ollama) estão **desabilitados permanentemente**. O `generate()` em `brain/llm.py` faz cascade apenas por provedores cloud:

1. Mistral → 2. Gemini → 3. OpenRouter → 4. Chutes.ai → 5. GitHub Models → 6. Naga AI → 7. Best AI → 8. Groq

Configure ao menos uma `API_KEY` no `.env` para que o Luna funcione.

## Variáveis de ambiente relevantes

- `LUNA_MAX_STEPS=15` — limite de iterações do loop ReAct
- `LUNA_API_HOST`, `LUNA_API_PORT` — host/porta da API
- `LUNA_MAX_HISTORY=10` — pares de conversa mantidos em memória
