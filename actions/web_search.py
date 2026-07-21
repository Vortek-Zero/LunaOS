#!/usr/bin/env python3
"""
actions/web_search.py — Pesquisa web com cache (Tavily → Wikipedia → DuckDuckGo)
Extraído de luna_core.py para desacoplar responsabilidades.
"""

import json
import os
import re
import sqlite3
import time as _time
import urllib.parse
import urllib.request
from pathlib import Path


def quick_fact_check(query: str) -> str:
    """Busca rápida via Tavily AI (primário) com fallback Wikipedia + DuckDuckGo.
    Extraído do LunaCore para manter o core enxuto."""
    # ── Cache SQLite ──────────────────────────────────────
    db_path = Path(__file__).parent.parent / "brain" / "facts_cache.db"
    os.makedirs(db_path.parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS cache (query TEXT PRIMARY KEY, result TEXT, ts REAL)")

    stopwords = {
        "o", "que", "você", "acha", "do", "da", "de", "um", "uma",
        "para", "como", "qual", "quais", "me", "mim", "eu", "ele",
        "ela", "nós", "é", "foi", "vai", "ser", "tem", "por",
        "sobre", "ao", "aos", "das", "dos", "na", "no", "nas",
        "nos", "com", "sem", "isso", "a", "e", "i",
    }
    words = re.findall(r"\b\w+\b", query.lower())
    clean_query = " ".join([w for w in words if len(w) > 1 and w not in stopwords])
    if not clean_query.strip():
        clean_query = query

    # Cache hit (TTL 6h)
    cur.execute("SELECT result, ts FROM cache WHERE query=?", (clean_query,))
    row = cur.fetchone()
    if row and (_time.time() - row[1]) < 21600:
        conn.close()
        print(f"[🔍 Pesquisa] Cache hit: '{clean_query}'")
        return row[0]

    result_text = ""
    headers = {"User-Agent": "LunaAI/1.0", "Content-Type": "application/json"}

    # ── Primário: Tavily AI Search ────────────────────────
    try:
        from config import TAVILY_API_KEY
    except ImportError:
        TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

    if TAVILY_API_KEY:
        try:
            payload = json.dumps({
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 3,
                "include_answer": True,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            answer = data.get("answer", "").strip()
            results = data.get("results", [])
            parts = []
            if answer:
                parts.append(answer)
            for r in results[:2]:
                content = r.get("content", "").strip()
                if content:
                    parts.append(content[:300])
            if parts:
                result_text = " | ".join(parts)
                print(f"[🔍 Tavily] ✓ {len(results)} resultado(s)")
        except Exception as e:
            print(f"[🔍 Tavily] falhou: {e}")

    # ── Fallback: Wikipedia ───────────────────────────────
    if not result_text:
        wiki_url = (
            f"https://pt.wikipedia.org/w/api.php?action=query&list=search"
            f"&srsearch={urllib.parse.quote(clean_query)}&utf8=&format=json"
        )
        try:
            req = urllib.request.Request(wiki_url, headers={"User-Agent": "LunaAI/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                items = data.get("query", {}).get("search", [])
                if items:
                    snippets = [f"{i['title']}: {re.sub(r'<[^>]+>', '', i['snippet'])}" for i in items[:2]]
                    result_text = " | ".join(snippets)
                    print(f"[🔍 Wikipedia] {len(items)} resultado(s)")
        except Exception as e:
            print(f"[🔍 Wikipedia] falhou: {e}")

    # ── Fallback: DuckDuckGo ──────────────────────────────
    if not result_text:
        ddg_url = (
            f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_query)}&format=json&no_html=1&skip_disambig=1"
        )
        try:
            req = urllib.request.Request(ddg_url, headers={"User-Agent": "LunaAI/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
            parts = []
            if data.get("Answer"):
                parts.append(data["Answer"])
            if data.get("AbstractText"):
                parts.append(data["AbstractText"][:300])
            for r in data.get("RelatedTopics", [])[:2]:
                if isinstance(r, dict) and r.get("Text"):
                    parts.append(r["Text"][:150])
            if parts:
                result_text = " | ".join(parts)
                print("[🔍 DuckDuckGo] resultado encontrado")
        except Exception as e:
            print(f"[🔍 DuckDuckGo] falhou: {e}")

    # Cache e retorno
    if result_text:
        try:
            cur.execute(
                "INSERT OR REPLACE INTO cache (query, result, ts) VALUES (?, ?, ?)",
                (clean_query, result_text, _time.time()),
            )
            conn.commit()
        except Exception:
            pass
    conn.close()
    return result_text
