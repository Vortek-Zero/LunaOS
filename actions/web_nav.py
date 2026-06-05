#!/usr/bin/env python3
"""
actions/web_nav.py — Navegação web sem depender só de OCR.

Prioridade para resultados de busca:
  1. Abrir URL do 1º resultado (fetch) — mais confiável
  2. Atalhos de teclado no navegador focado (xdotool)
  3. BrowserAgent Playwright (DOM real)
  4. OCR (último recurso — feito em executor._resolve_click)
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time
import unicodedata
from typing import Optional
from urllib.parse import quote, unquote

_ORDINALS = {
    "primeiro": 0, "primeira": 0, "1o": 0, "1a": 0, "1º": 0, "1ª": 0,
    "segundo": 1, "segunda": 1, "2o": 1, "2a": 1, "2º": 1, "2ª": 1,
    "terceiro": 2, "terceira": 2, "3o": 2, "3º": 2,
}


def _norm(s: str) -> str:
    t = unicodedata.normalize("NFD", s.lower().strip())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def parse_ordinal_index(text: str) -> int:
    words = _norm(text).split()
    for w in words:
        if w in _ORDINALS:
            return _ORDINALS[w]
    m = re.search(r"\b(\d+)\b", text)
    if m:
        return max(0, int(m.group(1)) - 1)
    return 0


def is_web_result_click(text: str) -> bool:
    n = _norm(text)
    if any(w in n for w in ("resultado", "resultados", "link", "links", "busca", "google", "pesquisa")):
        return True
    if re.search(r"(?:primeiro|segundo|terceiro|\d+)\s*(?:resultado|link)", n):
        return True
    if re.search(r"(?:acesse|acessa|acessar|entra|entre)\s+(?:o|a)?\s*(?:primeiro|segundo|\d+)", n):
        return True
    if "clica" in n and ("web" in n or "pagina" in n or "página" in n):
        return True
    return False


def fetch_first_result_url(query: str, index: int = 0) -> Optional[str]:
    """Obtém URL do N-ésimo resultado orgânico (DuckDuckGo HTML → fallback Jina/Google)."""
    if not query or not query.strip():
        return None

    urls = _fetch_ddg_result_urls(query)
    if not urls:
        urls = _fetch_google_jina_urls(query)

    if index < len(urls):
        return urls[index]
    return urls[0] if urls else None


def _fetch_ddg_result_urls(query: str) -> list[str]:
    import urllib.request
    from urllib.parse import quote, unquote

    try:
        url = f"https://html.duckduckgo.com/html/?q={quote(query.strip())}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) LunaAI"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        found: list[str] = []
        for m in re.finditer(r"uddg=([^&\"'>]+)", html):
            u = unquote(m.group(1))
            if u.startswith("http") and u not in found:
                found.append(u)
        return found[:10]
    except Exception as e:
        print(f"[WebNav] DuckDuckGo: {e}")
        return []


def _fetch_google_jina_urls(query: str) -> list[str]:
    import urllib.request

    q = quote(query.strip())
    search_url = f"https://www.google.com/search?q={q}&hl=pt-BR&num=10"
    jina_url = f"https://r.jina.ai/{search_url}"
    try:
        req = urllib.request.Request(jina_url, headers={"User-Agent": "LunaAI/1.0"})
        with urllib.request.urlopen(req, timeout=18) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[WebNav] Jina SERP: {e}")
        return []

    skip_domains = (
        "google.com", "googleusercontent", "gstatic.com",
        "accounts.google", "support.google",
    )
    urls: list[str] = []
    for m in re.finditer(r"https?://[^\s\)\]\"'<>]+", content):
        url = m.group(0).rstrip(".,;)")
        if any(d in url for d in skip_domains):
            continue
        if url not in urls:
            urls.append(url)
    return urls[:10]


def click_via_keyboard(n: int = 0) -> dict:
    """Navega até o (n+1)º resultado na página de busca com setas + Enter."""
    if not shutil.which("xdotool"):
        return {"success": False, "message": "FALHOU: xdotool não instalado."}
    try:
        # Garante foco na janela ativa (navegador)
        subprocess.run(["xdotool", "getactivewindow", "windowfocus"], capture_output=True, timeout=2)
        time.sleep(0.25)
        # Sai de barra de endereço se estiver focada
        subprocess.run(["xdotool", "key", "Escape"], capture_output=True, timeout=1)
        time.sleep(0.15)
        # Google: Tab até área de resultados ou seta para baixo
        subprocess.run(["xdotool", "key", "Tab", "Tab"], capture_output=True, timeout=1)
        time.sleep(0.1)
        for _ in range(n + 1):
            subprocess.run(["xdotool", "key", "Down"], capture_output=True, timeout=1)
            time.sleep(0.08)
        subprocess.run(["xdotool", "key", "Return"], capture_output=True, timeout=1)
        return {
            "success": True,
            "message": f"Abri o {n + 1}º resultado via teclado (setas + Enter).",
        }
    except Exception as e:
        return {"success": False, "message": f"FALHOU: teclado: {e}"}


def click_via_browser_agent(task: str, executor) -> Optional[dict]:
    """Playwright + visão — DOM real, não OCR da tela inteira."""
    try:
        agent = executor.browser_agent
        result = agent.run(task, headless=False, max_steps=8)
        ok = result.startswith("✓") or "concluíd" in result.lower() or "Clicou" in result
        return {"success": ok, "message": result}
    except Exception as e:
        print(f"[WebNav] BrowserAgent: {e}")
        return None


def try_click_web_result(
    text: str,
    executor,
    search_query: str = "",
) -> Optional[dict]:
    """
    Tenta abrir/clicar resultado de busca sem OCR.
    Retorna dict de resultado ou None para fallback.
    """
    if not is_web_result_click(text):
        return None

    n = parse_ordinal_index(text)
    query = (search_query or getattr(executor.web_manager, "last_search_query", "") or "").strip()

    print(f"[WebNav] Resultado web #{n + 1} | query='{query[:40]}'")

    # 1) Abrir URL diretamente (melhor — não precisa “clicar”)
    if query:
        url = fetch_first_result_url(query, index=n)
        if url:
            res = executor.open_url(url)
            if res.get("success"):
                return {
                    "success": True,
                    "message": f"Abri o {n + 1}º resultado: {url[:80]}",
                }

    # 2) Teclado na janela do navegador focada
    kb = click_via_keyboard(n)
    if kb.get("success"):
        return kb

    # 3) BrowserAgent (Playwright)
    task = (
        f"Na página de resultados de busca atual, clique no {n + 1}º resultado de pesquisa "
        f"(link do título, não anúncio). Use target nth-resultado:{n + 1} se necessário."
    )
    if query:
        task = (
            f"Vá para https://www.google.com/search?q={quote(query)} e clique no "
            f"{n + 1}º resultado orgânico."
        )
    ba = click_via_browser_agent(task, executor)
    if ba and ba.get("success"):
        return ba

    return None
