#!/usr/bin/env python3
"""
dom_tool.py — Browser DOM automation via Playwright.
Prioridade: 100 para tarefas de navegador (primeira tentativa).

Capacidades:
  - Navegar para URL
  - Clicar em elementos (texto, seletor)
  - Digitar texto
  - Extrair conteúdo da página
  - Tirar screenshot
  - Esperar por elementos
  - Executar JavaScript
"""

import asyncio
from pathlib import Path

from interaction.tools.base_tool import BaseTool, ToolResult

TEMP_DIR = Path(__file__).parent.parent.parent / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

_BROWSER = None
_PAGE = None


def _get_or_create_eventloop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class DOMTool(BaseTool):
    name = "dom"
    description = "Automação de navegador via DOM (Playwright) — navegar, clicar, digitar, extrair"
    category = "browser"
    priority = 100

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None
        self._loop = None

    def _ensure_loop(self):
        if self._loop is None or not self._loop.is_running():
            self._loop = _get_or_create_eventloop()

    def available(self) -> bool:
        try:
            import importlib

            return importlib.util.find_spec("playwright") is not None
        except Exception:
            return False

    async def _launch(self):
        global _BROWSER, _PAGE
        if _PAGE and _PAGE.is_closed():
            _PAGE = None
            _BROWSER = None
        if _PAGE:
            self._page = _PAGE
            self._browser = _BROWSER
            return

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,800",
            ],
        )
        ctx = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            locale="pt-BR",
        )
        self._page = await ctx.new_page()
        _BROWSER = self._browser
        _PAGE = self._page

    async def _close(self):
        global _BROWSER, _PAGE
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        _BROWSER = None
        _PAGE = None
        self._browser = None
        self._page = None
        self._playwright = None

    def execute(self, task: dict) -> ToolResult:
        self._ensure_loop()
        goal = task.get("goal", "")
        action = task.get("action", "navigate")
        url = task.get("url", "")
        selector = task.get("selector", "")
        text = task.get("text", "")
        js_code = task.get("js", "")

        try:
            if self._loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(
                    self._execute_async(action, url, selector, text, js_code, goal), self._loop
                )
                return fut.result(timeout=30)
            else:
                return self._loop.run_until_complete(self._execute_async(action, url, selector, text, js_code, goal))
        except Exception as e:
            return ToolResult(status="error", error=str(e), signals={"exception": True})

    async def _execute_async(
        self, action: str, url: str, selector: str, text: str, js_code: str, goal: str
    ) -> ToolResult:
        await self._launch()

        if action == "navigate" or (not action and url):
            await self._page.goto(url or "https://www.google.com", wait_until="domcontentloaded")
            title = await self._page.title()
            return ToolResult(
                status="success",
                data={"url": self._page.url, "title": title},
                signals={"url_changed": True, "page_loaded": True},
            )

        if action == "click":
            if selector:
                await self._page.click(selector)
            elif text:
                await self._page.get_by_text(text, exact=False).first.click()
            else:
                return ToolResult(status="error", error="Nenhum seletor ou texto para clicar")
            return ToolResult(status="success", data={"clicked": selector or text})

        if action == "type":
            target = self._page.locator(selector) if selector else self._page.locator("body")
            await target.fill(text)
            return ToolResult(status="success", data={"typed": text})

        if action == "extract":
            content = await self._page.content()
            text_content = await self._page.inner_text("body")
            return ToolResult(
                status="success",
                data={"text": text_content[:5000], "html_length": len(content)},
            )

        if action == "screenshot":
            path = str(TEMP_DIR / "dom_screenshot.png")
            await self._page.screenshot(path=path, full_page=True)
            return ToolResult(
                status="success",
                data={"screenshot": path},
                signals={"screenshot_taken": True},
            )

        if action == "wait":
            timeout = int(selector) if selector.isdigit() else 3000
            await self._page.wait_for_timeout(timeout)
            return ToolResult(status="success", data={"waited": f"{timeout}ms"})

        if action == "js":
            result = await self._page.evaluate(js_code)
            return ToolResult(status="success", data={"result": str(result)[:1000]})

        if action == "search":
            await self._page.goto(f"https://www.google.com/search?q={goal}", wait_until="domcontentloaded")
            results = await self._page.evaluate("""
                () => Array.from(document.querySelectorAll('h3')).slice(0,5).map(h => ({
                    title: h.innerText,
                    url: h.closest('a')?.href || ''
                }))
            """)
            return ToolResult(
                status="success",
                data={"results": results},
                signals={"search_done": True},
            )

        if action == "close":
            await self._close()
            return ToolResult(status="success", data={"closed": True})

        return ToolResult(status="error", error=f"Ação desconhecida: {action}")

    def verify(self, result: ToolResult) -> bool:
        if result.status == "success":
            return True
        if result.signals.get("url_changed"):
            return True
        if result.signals.get("page_loaded"):
            return True
        if result.signals.get("screenshot_taken"):
            return True
        return bool(result.signals.get("search_done"))

    def to_dict(self) -> dict:
        info = super().to_dict()
        info["browser_open"] = _PAGE is not None and not _PAGE.is_closed()
        return info
