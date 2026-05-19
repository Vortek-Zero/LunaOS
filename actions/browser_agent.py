#!/usr/bin/env python3
"""
actions/browser_agent.py — AI Computer Agent com Playwright + Groq Vision

Fluxo por passo:
  1. Playwright tira screenshot da página atual
  2. Groq Vision (llama-4-scout) analisa a imagem e decide a próxima ação
  3. Playwright executa a ação (click, type, navigate, scroll)
  4. Repete até a tarefa estar concluída ou atingir max_steps

Suporta contexto persistente (salva cookies/logins entre sessões).
"""
import asyncio
import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

# ── Configuração ──────────────────────────────────────────────
_USER_DATA_DIR = Path(__file__).parent.parent / "data" / "browser_profile"
_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

_SCREENSHOT_PATH = Path(__file__).parent.parent / "temp" / "img" / "browser_agent.png"
_SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)

try:
    from config import GROQ_API_KEY
except ImportError:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Modelo de visão disponível no Groq
_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# ── Prompt do agente ──────────────────────────────────────────
_AGENT_SYSTEM = """Você é um agente de automação de browser. Analise o screenshot e decida a próxima ação.

Responda APENAS com JSON válido, sem markdown:
{
  "action": "click|type|navigate|scroll|wait|done|fail",
  "target": "texto visível do elemento OU seletor CSS OU nth-TIPO:N OU URL",
  "value": "texto para digitar (apenas para action=type)",
  "reason": "por que esta ação"
}

Ações disponíveis:
- click: clica em elemento pelo texto visível, seletor CSS, ou nth-TIPO:N
- type: digita texto em campo focado (use após click no campo)
- navigate: navega para URL
- scroll: "down" ou "up"
- wait: aguarda 1s (use quando página está carregando)
- done: tarefa concluída com sucesso
- fail: impossível completar a tarefa

Para clicar no Nº elemento de um tipo, use target="nth-TIPO:N" onde:
  TIPO pode ser: link, resultado, video, botao, imagem
  N é o número (1=primeiro, 2=segundo, etc.)
  Exemplos: "nth-link:1", "nth-resultado:2", "nth-video:3"

IMPORTANTE: Prefira clicar por texto visível quando o texto é claro.
Use nth-TIPO:N quando o usuário pede "primeiro link", "segundo resultado", etc."""


class BrowserAgent:
    """
    Agente autônomo que controla o Firefox via Playwright.
    Usa Groq Vision para "ver" a página e decidir ações.
    """

    def __init__(self):
        self._browser = None
        self._context = None
        self._page = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False

    # ── Ciclo de vida ─────────────────────────────────────────

    async def _start(self, headless: bool = False):
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        # Contexto persistente: mantém cookies/logins entre sessões
        self._context = await self._pw.firefox.launch_persistent_context(
            user_data_dir=str(_USER_DATA_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 800},
            locale="pt-BR",
            args=["--no-sandbox"],
        )
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        self._running = True
        print("[BrowserAgent] ✓ Firefox iniciado (contexto persistente)")

    async def _stop(self):
        try:
            if self._context:
                await self._context.close()
            if hasattr(self, '_pw'):
                await self._pw.stop()
        except Exception:
            pass
        self._running = False
        self._page = None
        self._context = None

    # ── Screenshot → base64 ───────────────────────────────────

    async def _screenshot_b64(self) -> str:
        await self._page.screenshot(path=str(_SCREENSHOT_PATH), full_page=False)
        with open(_SCREENSHOT_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()

    # ── Groq Vision ───────────────────────────────────────────

    def _ask_vision(self, img_b64: str, task: str, history: list[str]) -> dict:
        """Envia screenshot para Groq Vision e recebe a próxima ação."""
        import urllib.request

        hist_text = "\n".join(f"- {h}" for h in history[-5:]) if history else "Nenhuma ainda."
        user_msg = (
            f"Tarefa: {task}\n\n"
            f"Ações já executadas:\n{hist_text}\n\n"
            f"Analise o screenshot e decida a próxima ação."
        )

        payload = json.dumps({
            "model": _VISION_MODEL,
            "messages": [
                {"role": "system", "content": _AGENT_SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": user_msg},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{img_b64}"
                    }}
                ]}
            ],
            "temperature": 0.1,
            "max_tokens": 300,
        }).encode()

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        raw = data["choices"][0]["message"]["content"].strip()

        # Parseia JSON da resposta
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        return {"action": "fail", "reason": f"Resposta inválida: {raw[:100]}"}

    # ── Executor de ações ─────────────────────────────────────

    async def _execute(self, action: dict) -> str:
        act = action.get("action", "fail")
        target = action.get("target", "")
        value = action.get("value", "")

        if act == "navigate":
            url = target if target.startswith("http") else f"https://{target}"
            await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
            return f"Navegou para {url}"

        elif act == "click":
            # Tenta por texto visível primeiro, depois por seletor, depois por JS nth-element
            try:
                await self._page.get_by_text(target, exact=False).first.click(timeout=5000)
                return f"Clicou em '{target}'"
            except Exception:
                try:
                    await self._page.locator(target).first.click(timeout=5000)
                    return f"Clicou em seletor '{target}'"
                except Exception:
                    # Tenta nth-element via JS: "nth-link:2", "nth-result:1", "nth-video:3"
                    nth_m = re.match(r'nth-(\w+):(\d+)', target)
                    if nth_m:
                        kind, n = nth_m.group(1), int(nth_m.group(2)) - 1
                        selector_map = {
                            "link":      "a[href]:not([href='#']):not([href=''])",
                            "resultado": "h3 a, .g a, [data-ved] a, article a",
                            "video":     "a[href*='watch'], ytd-video-renderer a, .video-item a, thumbnail a",
                            "botao":     "button, input[type='submit'], input[type='button'], [role='button']",
                            "imagem":    "img[src]:not([src=''])",
                        }
                        sel = selector_map.get(kind, "a")
                        try:
                            await self._page.locator(sel).nth(n).click(timeout=5000)
                            return f"Clicou no {n+1}º {kind}"
                        except Exception as e:
                            return f"Falha ao clicar no {n+1}º {kind}: {e}"
                    return f"Falha ao clicar em '{target}'"

        elif act == "type":
            await self._page.keyboard.type(value, delay=30)
            return f"Digitou '{value[:30]}...'" if len(value) > 30 else f"Digitou '{value}'"

        elif act == "scroll":
            direction = 1 if value == "down" or target == "down" else -1
            await self._page.mouse.wheel(0, direction * 500)
            return f"Rolou {'para baixo' if direction > 0 else 'para cima'}"

        elif act == "wait":
            await asyncio.sleep(1.5)
            return "Aguardou 1.5s"

        elif act in ("done", "fail"):
            return act

        return f"Ação desconhecida: {act}"

    # ── Loop principal do agente ──────────────────────────────

    async def _run_task(self, task: str, max_steps: int = 10) -> str:
        history: list[str] = []
        last_url = ""

        for step in range(1, max_steps + 1):
            print(f"[BrowserAgent] Passo {step}/{max_steps}")

            # Aguarda rede estabilizar
            try:
                await self._page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass

            # Screenshot
            img_b64 = await self._screenshot_b64()
            current_url = self._page.url
            if current_url != last_url:
                history.append(f"URL atual: {current_url}")
                last_url = current_url

            # Visão → decisão
            try:
                action = self._ask_vision(img_b64, task, history)
            except Exception as e:
                return f"Erro na visão: {e}"

            print(f"[BrowserAgent] Ação: {action.get('action')} | {action.get('reason','')}")

            if action.get("action") == "done":
                return f"✓ Tarefa concluída: {action.get('reason', 'sucesso')}"
            if action.get("action") == "fail":
                return f"✗ Não foi possível: {action.get('reason', 'falha')}"

            # Executa
            result = await self._execute(action)
            history.append(f"Passo {step}: {action.get('action')} → {result}")

            if result in ("done", "fail"):
                return f"Tarefa {'concluída' if result == 'done' else 'falhou'}."

            await asyncio.sleep(0.5)

        return f"Limite de {max_steps} passos atingido. Última ação: {history[-1] if history else 'nenhuma'}"

    # ── API pública (síncrona) ────────────────────────────────

    def run(self, task: str, headless: bool = False, max_steps: int = 10) -> str:
        """
        Executa uma tarefa no browser. Bloqueia até concluir.
        Mantém o browser aberto entre chamadas (reutiliza contexto).
        Sempre roda numa thread dedicada com loop próprio para evitar
        conflito com o event loop do FastAPI ou qualquer outro loop ativo.
        """
        if not GROQ_API_KEY:
            return "Groq API key não configurada. Necessária para visão computacional."

        async def _main():
            if not self._running:
                await self._start(headless=headless)
            return await self._run_task(task, max_steps=max_steps)

        def _run_in_new_loop():
            """Cria um event loop limpo e dedicado nesta thread."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_main())
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        import threading
        import concurrent.futures

        # Sempre usa thread dedicada — evita conflito com loops existentes
        # (FastAPI, Qt, ou qualquer outro loop em execução)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_run_in_new_loop)
                return future.result(timeout=120)
        except concurrent.futures.TimeoutError:
            return "Erro no agente: timeout de 120s atingido."
        except Exception as e:
            return f"Erro no agente: {e}"

    def close(self):
        """Fecha o browser."""
        if self._running:
            try:
                asyncio.run(self._stop())
            except Exception:
                pass

    def navigate(self, url: str) -> str:
        """Navega para uma URL diretamente."""
        return self.run(f"Navegue para {url} e confirme que a página carregou.", max_steps=3)

    def screenshot_path(self) -> Optional[str]:
        """Retorna o caminho do último screenshot."""
        return str(_SCREENSHOT_PATH) if _SCREENSHOT_PATH.exists() else None


# Singleton
_agent: Optional[BrowserAgent] = None

def get_browser_agent() -> BrowserAgent:
    global _agent
    if _agent is None:
        _agent = BrowserAgent()
    return _agent
