# Luna — O que funciona, o que não, e bugs conhecidos

> **Pipeline atual:** toda ação no PC → LLM (FASE 5) + ferramentas tipadas.  
> Meta/admin (`status`, `limpa tudo`) não usa LLM.

## Correções aplicadas (última revisão)

| Bug | Status |
|-----|--------|
| B1 `run_luna_command` / `execute_natural` | **Removido** — tools dedicadas + `_resolve_click` |
| B2 `_execute_action` JSON legacy | **Removido** — só ferramentas nativas |
| B3 memória vs SQLite desktop | **Corrigido** — `switch_session` recarrega do `chat_db` |
| B4 clique vs `abre` | **Corrigido** (executor) |
| B6 briefing órfão | **Tool `get_daily_briefing`** + API `/api/briefing` |
| Wayland input | **ydotool + wtype** em `actions/ui.py` |
| Vision 403 Groq | **Fallback Gemini + OCR** |
| OCR fraco | **pytesseract + mss** no requirements |
| Secrets no git | **`.gitignore`** (.env, token.json, credentials.json) |

## Ferramentas (60+)

Principais: `open_app`, `open_url`, `search_web`, `click_web_result`, `click_on_screen`, `see_screen`, `take_screenshot`, `run_terminal_command`, `kill_process`, `filesystem`, `get_daily_briefing`, `run_browser_task`, `google_*`, `set_timer`, `manage_*`, `get_weather`, `whatsapp_action`.

**Removido:** `run_luna_command` (não aparece mais na lista do agente).

## Dependências gratuitas

### Python (`pip install -r requirements.txt`)
edge-tts, groq, pytesseract, Pillow, **mss**, google-generativeai, etc.

### Sistema (Arch)
```bash
sudo pacman -S tesseract tesseract-data-por wmctrl xdotool gio grim playerctl
# Wayland (recomendado):
sudo pacman -S ydotool wtype   # ydotool precisa: systemctl --user enable --now ydotoold
```

## Testes

```bash
python tests/system_audit.py
```

### Manual
- `briefing do dia` → `get_daily_briefing`
- `tira um print` → `take_screenshot` / `see_screen`
- `abra firefox e pesquise youtube.com` → multi-tool
- Trocar sessão no desktop → histórico coerente no prompt

## Limitações restantes

1. **WhatsApp UI** — frágil (layout muda)
2. **ydotool** — requer daemon `ydotoold` no Wayland
3. **Browser agent** — pesado; precisa Playwright configurado
4. **Conversas 20+ trocas** — contexto truncado em ~2800 chars de memória
5. **Sem LLM offline** — nenhuma ação no PC (intencional)

## Segurança

- Nunca commitar `.env`, `token.json`, `credentials.json`
- Use `.env.example` como modelo
