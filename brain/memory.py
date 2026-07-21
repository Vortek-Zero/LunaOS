#!/usr/bin/env python3
"""
brain/memory.py — Memória limpa e persistente para Luna
Sistema de fatos críticos com recall cross-session
Contém também extract_facts_from_text (movido de luna_core.py)
"""

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("luna.memory")

try:
    from config import (
        MAX_HISTORY,
        MEMORY_FILE,
        MEMORY_SAVE_DEBOUNCE_SECONDS,
    )
    from config import (
        MAX_PERSISTENT_FACTS as MAX_PERSISTENT,
    )
except ImportError:
    MEMORY_FILE = Path(__file__).parent.parent / "data" / "memory.json"
    MAX_HISTORY = 10
    MAX_PERSISTENT = 200
    MEMORY_SAVE_DEBOUNCE_SECONDS = 5.0

# Mapa semântico — palavras que implicam em categorias de fatos
CATEGORY_KEYWORDS = {
    "hardware": [
        "ram", "gb", "cpu", "gpu", "processador", "placa", "memoria",
        "hd", "ssd", "computador", "pc", "notebook", "monitor",
        "linux", "windows", "sistema operacional", "gnome",
        "kde", "ubuntu", "arch", "debian", "distro", "memória",
    ],
    "preferencias": [
        "gosta", "prefere", "odeia", "favorito", "favorita",
        "gosto", "curtir", "não gosta", "costuma", "sempre usa",
    ],
    "perfil": ["nome", "chamo", "moro", "trabalho", "profissao", "profissão", "estudo", "idade", "anos", "família"],
    "projeto": ["projeto", "app", "aplicativo", "sistema", "desenvolvendo", "criando", "api", "backend", "frontend"],
    "habitos": ["acordo", "durmo", "como", "treino", "rotina", "manhã", "noite"],
    "historia": ["historia", "história", "personagem", "conto", "romance", "capítulo"],
}


class Memory:
    """
    Sistema unificado de memória.
    - history: conversa recente (sessão atual, em RAM)
    - facts: memórias persistentes (em disco, cross-session)
    """

    def __init__(self):
        self.sessions: dict[str, list[dict]] = {"default": []}
        self.current_session_id: str = "default"
        self.facts: list[dict] = []
        self._facts_index: dict[str, set] = {}
        self._save_timer: threading.Timer | None = None
        self._save_lock = threading.Lock()
        self._data_lock = threading.RLock()
        self._dirty = False
        self._load()
        self._rebuild_index()

        try:
            from brain.memory_rag import MemoryRAG
            self.rag = MemoryRAG()
        except ImportError:
            self.rag = None

    @property
    def history(self) -> list[dict]:
        return self.sessions.setdefault(self.current_session_id, [])

    @history.setter
    def history(self, val: list[dict]):
        self.sessions[self.current_session_id] = val

    def get_sessions(self) -> list[str]:
        return list(self.sessions.keys())

    def switch_session(self, session_id: str) -> None:
        """Troca sessão e recarrega histórico do SQLite (fonte de verdade)."""
        with self._data_lock:
            try:
                from brain.chat_db import get_chat_db
                db = get_chat_db()
                history = db.load_session(session_id)
            except Exception:
                history = []
            self.sessions[session_id] = history
            self.current_session_id = session_id

    # ── Histórico ──────────────────────────────────────────

    def add_exchange(self, user_text: str, assistant_response: str) -> None:
        with self._data_lock:
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": assistant_response})
            self._trim_history()
            self._save()

    def get_context_for_prompt(self, query: str, max_turns: int = None) -> str:
        """Retorna histórico formatado para o prompt."""
        if max_turns is None:
            max_turns = MAX_HISTORY
        with self._data_lock:
            recent = self.history[-(max_turns * 2):]
            if not recent:
                return ""
            lines = ["[HISTÓRICO RECENTE DA CONVERSA]"]
            for msg in recent:
                role = "Usuário" if msg.get("role") == "user" else "Luna"
                content = msg.get("content", "")
                if content:
                    lines.append(f"{role}: {content}")
            return "\n".join(lines)

    def clear_history(self) -> None:
        with self._data_lock:
            self.history.clear()
            self._save()

    def _trim_history(self) -> None:
        max_entries = MAX_HISTORY * 2
        if len(self.history) > max_entries:
            self.history = self.history[-max_entries:]

    # ── Fatos Persistentes ──────────────────────────────────

    def _rebuild_index(self) -> None:
        self._facts_index.clear()
        for f in self.facts:
            cat = f.get("category", "geral")
            if cat not in self._facts_index:
                self._facts_index[cat] = set()
            self._facts_index[cat].add(f.get("fact", "").lower())

    def remember(self, fact: str, category: str = "geral", importance: float = 0.8) -> None:
        fact_lower = fact.lower().strip()
        cat = category.strip().lower()

        # Evita duplicatas próximas
        existing = self._facts_index.get(cat, set())
        for ef in existing:
            if fact_lower in ef or ef in fact_lower:
                return

        entry = {"fact": fact, "category": cat, "importance": importance, "ts": datetime.now().isoformat()}
        with self._data_lock:
            self.facts.append(entry)
            if cat not in self._facts_index:
                self._facts_index[cat] = set()
            self._facts_index[cat].add(fact_lower)
            if len(self.facts) > MAX_PERSISTENT:
                self.facts = self.facts[-MAX_PERSISTENT:]
            self._save()

    def recall(self, query: str, top_n: int = 5) -> list[dict]:
        """Busca fatos relevantes por keyword matching."""
        query_lower = query.lower()
        query_words = set(re.findall(r"\b\w+\b", query_lower))
        scored = []
        for f in self.facts:
            fact_lower = f["fact"].lower()
            matches = sum(1 for w in query_words if w in fact_lower and len(w) > 2)
            if matches > 0:
                scored.append((matches * f.get("importance", 0.5), f))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:top_n]]

    def get_context_for_prompt_with_facts(self, query: str) -> str:
        """Histórico + fatos relevantes combinados."""
        context = self.get_context_for_prompt(query)
        facts = self.recall(query, top_n=3)
        if facts:
            fact_lines = ["[FATOS SOBRE O USUÁRIO]"]
            for f in facts:
                fact_lines.append(f"- {f['fact']} (importância: {f['importance']:.1f})")
            context += "\n" + "\n".join(fact_lines)
        return context

    def stats(self) -> str:
        with self._data_lock:
            fact_count = len(self.facts)
            categories = set(f.get("category", "geral") for f in self.facts)
            cat_str = ", ".join(sorted(categories)[:5])
            return f"{len(self.history)} msgs | {fact_count} fatos ({cat_str})"

    def clear_facts(self) -> int:
        with self._data_lock:
            n = len(self.facts)
            self.facts.clear()
            self._facts_index.clear()
            self._save()
        return n

    def clear_all(self) -> str:
        n_facts = self.clear_facts()
        self.clear_history()
        return f"Memória apagada: {n_facts} fatos removidos."

    # ── Persistência ──────────────────────────────────────────

    def _load(self):
        try:
            if MEMORY_FILE.exists():
                data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                self.sessions = data.get("sessions", {"default": []})
                self.current_session_id = data.get("current_session", "default")
                if self.current_session_id not in self.sessions:
                    self.current_session_id = "default"
                self.facts = data.get("facts", [])
        except Exception as e:
            logger.error(f"Erro ao carregar memória: {e}")

    def _save(self):
        def _do_save():
            with self._save_lock:
                data = {
                    "sessions": self.sessions,
                    "current_session": self.current_session_id,
                    "facts": self.facts[-MAX_PERSISTENT:],
                }
                MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
                MEMORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                self._dirty = False

        self._dirty = True
        if self._save_timer and self._save_timer.is_alive():
            self._save_timer.cancel()
        self._save_timer = threading.Timer(MEMORY_SAVE_DEBOUNCE_SECONDS, _do_save)
        self._save_timer.daemon = True
        self._save_timer.start()


# ── Fact extraction (movido de luna_core.py) ──────────────────


def extract_facts_from_text(user_text: str, llm=None) -> list[dict]:
    """
    Extrai fatos importantes do texto do usuário usando LLM.
    Retorna lista de dicts com fact, category, importance.
    Roda em background — não atrasa a resposta.
    """
    if not user_text or len(user_text.strip()) < 10:
        return []
    if llm is None:
        return []

    try:
        prompt = f"""Analise a mensagem do usuário e extraia APENAS informações factuais importantes sobre ele.
Ignore perguntas, pedidos, comandos, e conteúdo que não seja sobre o usuário em si.

REGRAS:
- Só extraia um fato se for uma INFORMAÇÃO PERMANENTE sobre o usuário (hardware, sistema, profissão, onde mora, preferências fortes, nome de projetos pessoais).
- NUNCA extraia: perguntas, comandos, conversas casuais, saudações, feedback, confirmações ("sim", "ok").
- NUNCA extraia explicações técnicas genéricas (ex: "ls lista arquivos").
- Se não houver NENHUM fato permanente, retorne {{"facts": []}}.

Mensagem do usuário: "{user_text}"

Responda APENAS com JSON. Se não houver fatos, retorne {{"facts": []}}.
Formato:
{{"facts": [
  {{"fact": "descrição clara do fato", "category": "hardware|preferencias|perfil|projeto|habitos|historia", "importance": 0.0-1.0}}
]}}

Importância: APENAS use 0.95 para informações técnicas críticas, 0.85 para preferências fortes e projetos pessoais. Ignore importance < 0.85."""

        raw = llm.generate(prompt, task_type="command", model="fast", max_retries=1)
        if not raw:
            return []

        json_match = re.search(r"\{.*\}", str(raw), re.DOTALL)
        if not json_match:
            return []

        data = json.loads(json_match.group())
        facts = data.get("facts", [])
        result = []

        for item in facts:
            fact = item.get("fact", "").strip()
            category = item.get("category", "geral").strip()
            importance = float(item.get("importance", 0.5))

            if not fact or importance < 0.85:
                continue
            lower = fact.lower()
            if any(w in lower for w in ["?", "comando", "pergunta", "pedido", "ok ", "sim", "não"]):
                continue

            result.append({"fact": fact, "category": category, "importance": importance})
            tag = "🔴" if importance >= 0.85 else "🟡"
            print(f"[Memory] {tag} Fato extraído ({category}, {importance:.2f}): {fact[:60]}")

        return result
    except Exception:
        return []


# ── Singleton ─────────────────────────────────────────────────

_memory_instance: Memory | None = None


def get_memory() -> Memory:
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = Memory()
    return _memory_instance
