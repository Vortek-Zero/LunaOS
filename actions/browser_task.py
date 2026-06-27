#!/usr/bin/env python3
"""
actions/browser_task.py — Automação web avançada via browser-use.
Utiliza Playwright + LLM para navegar e realizar tarefas complexas.
"""
import asyncio
import os
from typing import Optional

try:
    from browser_use import Agent
    from langchain_groq import ChatGroq
    from langchain_google_genai import ChatGoogleGenerativeAI
    HAS_BROWSER_USE = True
except ImportError:
    HAS_BROWSER_USE = False

try:
    from config import GROQ_API_KEY, GEMINI_API_KEY
except ImportError:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

class BrowserTaskManager:
    def __init__(self):
        self.llm = self._setup_llm()

    def _setup_llm(self):
        if not HAS_BROWSER_USE:
            return None
        
        # Prioridade para Gemini 2.0 Flash (rápido e barato para DOM)
        if GEMINI_API_KEY:
            return ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=GEMINI_API_KEY)
        # Fallback para Groq Llama 3.3
        if GROQ_API_KEY:
            return ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=GROQ_API_KEY)
        return None

    async def _run_task(self, task: str):
        if not HAS_BROWSER_USE or not self.llm:
            return "FALHOU: browser-use ou chaves de API não disponíveis."

        agent = Agent(
            task=task,
            llm=self.llm,
        )
        result = await agent.run()
        return str(result)

    def run(self, task: str) -> str:
        if not HAS_BROWSER_USE:
            return "FALHOU: Instale browser-use (pip install browser-use)."
        
        try:
            return asyncio.run(self._run_task(task))
        except Exception as e:
            return f"FALHOU: Erro no browser-use: {e}"

_instance = None
def get_browser_task_manager():
    global _instance
    if _instance is None:
        _instance = BrowserTaskManager()
    return _instance
