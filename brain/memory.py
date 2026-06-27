#!/usr/bin/env python3
"""
brain/memory.py — Memória limpa e persistente para Luna
Sistema de fatos críticos com recall cross-session
"""
import json
import logging
import re
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("luna.memory")

try:
    from config import (
        MEMORY_FILE,
        MAX_HISTORY,
        MAX_PERSISTENT_FACTS as MAX_PERSISTENT,
        MEMORY_SAVE_DEBOUNCE_SECONDS,
    )
except ImportError:
    MEMORY_FILE = Path(__file__).parent.parent / "data" / "memory.json"
    MAX_HISTORY = 10
    MAX_PERSISTENT = 200
    MEMORY_SAVE_DEBOUNCE_SECONDS = 5.0

# Mapa semântico — palavras que implicam em categorias de fatos
CATEGORY_KEYWORDS = {
    "hardware":    ["ram", "gb", "cpu", "gpu", "processador", "placa", "memoria", "hd", "ssd",
                    "computador", "pc", "notebook", "monitor", "linux", "windows", "sistema operacional",
                    "gnome", "kde", "ubuntu", "arch", "debian", "distro", "memória"],
    "preferencias":["gosta", "prefere", "odeia", "favorito", "favorita", "gosto", "curtir",
                    "não gosta", "costuma", "sempre usa"],
    "perfil":      ["nome", "chamo", "moro", "trabalho", "profissao", "profissão",
                    "estudo", "idade", "anos", "família"],
    "projeto":     ["projeto", "app", "aplicativo", "sistema", "desenvolvendo", "criando",
                    "api", "backend", "frontend"],
    "habitos":     ["acordo", "durmo", "como", "treino", "rotina", "manhã", "noite"],
    "historia":    ["historia", "história", "personagem", "conto", "romance", "capítulo"],
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
        self._save_timer: Optional[threading.Timer] = None
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
                db.create_session(session_id)
                rows = db.get_history(session_id, last_n=MAX_HISTORY)
                self.sessions[session_id] = [
                    {"role": m["role"], "text": m["text"], "ts": m.get("ts", "")}
                    for m in rows
                ]
            except Exception:
                if session_id not in self.sessions:
                    self.sessions[session_id] = []
            self.current_session_id = session_id
            self._schedule_save()

    def create_session(self, session_id: str) -> None:
        self.sessions[session_id] = []
        self.switch_session(session_id)

    def rename_session(self, old_id: str, new_id: str) -> bool:
        if old_id not in self.sessions or not new_id.strip():
            return False
        if new_id in self.sessions and new_id != old_id:
            return False
        self.sessions[new_id] = self.sessions.pop(old_id)
        if self.current_session_id == old_id:
            self.current_session_id = new_id
        self._schedule_save()
        return True

    def delete_session(self, session_id: str) -> bool:
        if session_id not in self.sessions:
            return False
        del self.sessions[session_id]
        if self.current_session_id == session_id:
            if self.sessions:
                self.current_session_id = next(iter(self.sessions))
            else:
                self.create_session("default")
        self._schedule_save()
        return True

    # ── Histórico da sessão ────────────────────────────────────

    def add_exchange(self, user_text: str, assistant_text: str) -> None:
        with self._data_lock:
            self.history.append({
                "role": "user",
                "text": user_text,
                "ts": datetime.now().isoformat()
            })
            self.history.append({
                "role": "assistant",
                "text": assistant_text,
                "ts": datetime.now().isoformat()
            })
            if len(self.history) > MAX_HISTORY * 2:
                self.history = self.history[-(MAX_HISTORY * 2):]

            try:
                from brain.chat_db import get_chat_db
                get_chat_db().add_exchange(self.current_session_id, user_text, assistant_text)
            except Exception as e:
                logger.warning("Falha ao salvar exchange no chat_db: %s", e)

            self._schedule_save()

    def get_history_text(self, last_n: int = 5) -> str:
        try:
            from brain.chat_db import get_chat_db
            text = get_chat_db().get_history_text(self.current_session_id, last_n)
            if text:
                return text
        except Exception:
            pass
        recent = self.history[-(last_n * 2):]
        lines = []
        for msg in recent:
            prefix = "Usuário" if msg["role"] == "user" else "Luna"
            lines.append(f"{prefix}: {msg['text']}")
        return "\n".join(lines)

    def get_last_user(self) -> str:
        for msg in reversed(self.history):
            if msg["role"] == "user":
                return msg["text"]
        return ""

    # ── Memória persistente ────────────────────────────────────

    def remember(self, fact: str, category: str = "geral", importance: float = 0.5) -> None:
        """
        Salva um fato na memória persistente com deduplicação semântica.
        importance >= 0.85 → fato crítico (injetado em TODAS as sessões)
        """
        with self._data_lock:
            fact_lower = fact.lower().strip()

            # Deduplicação — evita duplicatas e atualiza fatos similares
            for existing in self.facts:
                ex_lower = existing.get("fact", "").lower().strip()
                if ex_lower == fact_lower:
                    return  # Idêntico
                # Verifica sobreposição de palavras (>65% = similar)
                if len(fact_lower) > 10 and len(ex_lower) > 10:
                    words_new = set(re.findall(r'\w{3,}', fact_lower))
                    words_ex  = set(re.findall(r'\w{3,}', ex_lower))
                    if words_new and words_ex:
                        overlap = len(words_new & words_ex) / max(len(words_new), len(words_ex))
                        if overlap > 0.65 and existing.get("category") == category:
                            if len(fact) > len(existing.get("fact", "")):
                                existing["fact"] = fact
                                existing["importance"] = max(importance, existing.get("importance", 0.5))
                                existing["ts"] = datetime.now().isoformat()
                                self._rebuild_index()
                                self._schedule_save()
                            return

            self.facts.append({
                "fact": fact,
                "category": category,
                "importance": importance,
                "ts": datetime.now().isoformat(),
            })

            self._index_fact(len(self.facts) - 1, fact)

            if len(self.facts) > MAX_PERSISTENT:
                self.facts = sorted(
                    self.facts, key=lambda f: f.get("importance", 0), reverse=True
                )[:MAX_PERSISTENT]
                self._rebuild_index()

            self._schedule_save()

        if self.rag:
            self.rag.remember(fact, source="system")

    def recall(self, query: str, limit: int = 5) -> list[str]:
        """Busca fatos por palavras-chave da query."""
        with self._data_lock:
            if not self.facts or not query:
                return []

            query_words = set(re.findall(r"\b\w{3,}\b", query.lower()))
            if not query_words:
                return []

            scored = []
            for i, mem in enumerate(self.facts):
                fact_words = self._facts_index.get(i, set())
                overlap = len(query_words & fact_words)
                if overlap > 0:
                    score = overlap * mem.get("importance", 0.5)
                    scored.append((score, mem["fact"]))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [f for _, f in scored[:limit]]

    def recall_critical(self) -> list[str]:
        """
        Retorna todos os fatos com importância >= 0.85.
        Esses fatos são injetados em TODOS os prompts, em TODAS as sessões.
        """
        with self._data_lock:
            return [
                f["fact"] for f in self.facts
                if f.get("importance", 0) >= 0.85
            ]

    def recall_by_category(self, category: str, limit: int = 10) -> list[str]:
        """Retorna fatos de uma categoria ordenados por importância."""
        with self._data_lock:
            facts = [
                f for f in self.facts
                if f.get("category", "").lower() == category.lower()
            ]
            facts.sort(key=lambda f: f.get("importance", 0), reverse=True)
            return [f["fact"] for f in facts[:limit]]

    def _detect_relevant_categories(self, query: str) -> list[str]:
        """Detecta categorias semanticamente relevantes para a query."""
        query_lower = query.lower()
        relevant = []
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                relevant.append(category)
        return relevant

    @staticmethod
    def _is_topic_change(query: str) -> bool:
        """Detecta se o usuário mudou de assunto (saudação, tópico novo, etc)."""
        tl = query.lower().strip()
        # Comandos de ação NÃO são mudança de assunto
        action_prefixes = [
            "toca", "toque", "abre", "abra", "inicia", "inicie", "lista", "liste",
            "edita", "edite", "cria", "crie", "apaga", "apague", "manda", "envia",
            "pesquisa", "pesquise", "mostra", "mostre", "exibe", "exiba", "fala",
            "desliga", "desligue", "liga", "ligue", "escreve", "escreva",
        ]
        first_word = tl.split()[0] if tl.split() else ""
        if first_word in action_prefixes:
            return False
        # Perguntas de continuação
        continuation = ["que é", "o que", "quem", "como funciona", "como estava", "sobre o que", "continue"]
        if any(c in tl for c in continuation):
            return False
        # Saudações e início de conversa
        greetings = [
            "ola", "olá", "oi", "hey", "e ai", "e aí", " tudo bom", "tudo bem",
            "boa tarde", "bom dia", "boa noite", "fala", "bão", "beleza",
            "como vai", "how are you", "hello", "hi",
        ]
        if any(g in tl for g in greetings):
            return True
        # Palavra única ou muito curta sem ser comando → provável mudança
        if len(tl.split()) <= 2:
            return True
        return False

    def get_full_context_for_prompt(self, query: str) -> str:
        """
        Contexto completo para o prompt — cross-session.

        Estratégia (em ordem):
        1. Fatos críticos (importance >= 0.85) — SEMPRE injetados
        2. Fatos por categoria detectada na query
        3. Fatos por palavras-chave
        4. Histórico recente da sessão (PULADO se for mudança de assunto)
        5. RAG vetorial (se disponível)
        """
        with self._data_lock:
            parts = []
            already_included: set[str] = set()

            # ── 1. Fatos críticos ──────────────────────────────────
            critical_facts = self.recall_critical()
            if critical_facts:
                facts_text = "\n".join(f"• {f}" for f in critical_facts)
                parts.append(f"[FATOS PERMANENTES DO USUÁRIO — sempre considere]\n{facts_text}")
                already_included.update(critical_facts)

            topic_change = self._is_topic_change(query)

            # ── 2. Fatos por categoria relevante ──────────────────
            if not topic_change:
                relevant_categories = self._detect_relevant_categories(query)
                for cat in relevant_categories:
                    cat_facts = [f for f in self.recall_by_category(cat, limit=5)
                                 if f not in already_included]
                    if cat_facts:
                        cat_text = "\n".join(f"• {f}" for f in cat_facts)
                        parts.append(f"[Memória — {cat}]\n{cat_text}")
                        already_included.update(cat_facts)

            # ── 3. Fatos por palavras-chave ────────────────────────
            if not topic_change:
                kw_facts = [f for f in self.recall(query, limit=3) if f not in already_included]
                if kw_facts:
                    kw_text = "\n".join(f"• {f}" for f in kw_facts)
                    parts.append(f"[Memória relevante]\n{kw_text}")
                    already_included.update(kw_facts)

            # ── 4. Histórico recente ───────────────────────────────
            if not topic_change:
                history = self.get_history_text(last_n=2)
                if history:
                    parts.append(f"[Conversa recente]\n{history}")

            # ── 5. RAG vetorial ───────────────────────────────────
            if self.rag and not topic_change:
                rag_ctx = self.rag.retrieve_context(query)
                if rag_ctx:
                    parts.append(rag_ctx)

            return "\n\n".join(parts)

    # Compatibilidade retroativa
    def get_context_for_prompt(self, query: str) -> str:
        return self.get_full_context_for_prompt(query)

    # ── Persistência com Debounce ──────────────────────────────

    def _schedule_save(self) -> None:
        self._dirty = True
        with self._save_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(
                MEMORY_SAVE_DEBOUNCE_SECONDS,
                self._save
            )
            self._save_timer.daemon = True
            self._save_timer.start()

    def _load(self) -> None:
        try:
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            if MEMORY_FILE.exists():
                data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                self.facts = data.get("facts", [])
                if "sessions" in data:
                    self.sessions = data["sessions"]
                    self.current_session_id = data.get("current_session_id", "default")
                else:
                    self.sessions = {"default": data.get("history", [])}
                    self.current_session_id = "default"
        except Exception as e:
            print(f"[Memory] Falha ao carregar: {e}")
            self.facts = []
            self.sessions = {"default": []}
            self.current_session_id = "default"

    def _save(self) -> None:
        with self._data_lock:
            if not self._dirty:
                return
            try:
                MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
                data_to_save = {
                    "facts": self.facts,
                    "sessions": self.sessions,
                    "current_session_id": self.current_session_id
                }
                MEMORY_FILE.write_text(
                    json.dumps(data_to_save, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                self._dirty = False
            except Exception as e:
                print(f"[Memory] Falha ao salvar: {e}")

    def _force_save(self) -> None:
        self._dirty = True
        self._save()

    def clear_history(self) -> None:
        with self._data_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
            sid = self.current_session_id
            self.history = []
            try:
                from brain.chat_db import get_chat_db
                get_chat_db().clear_session_history(sid)
            except Exception:
                pass
            self._dirty = True
            self._save()

    def clear_facts(self) -> int:
        with self._data_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
            count = len(self.facts)
            self.facts = []
            self._facts_index = {}
            self._dirty = True
            self._save()
            return count

    def clear_all(self) -> str:
        """Limpa histórico de conversa e fatos persistentes."""
        self.clear_history()
        n = self.clear_facts()
        return f"Memória zerada: {n} fatos removidos, histórico apagado."

    def stats(self) -> str:
        critical = len(self.recall_critical())
        return (
            f"Histórico sessão: {len(self.history)//2} trocas | "
            f"Memórias persistentes: {len(self.facts)} ({critical} críticas)"
        )

    # ── Índice de busca rápida ─────────────────────────────────

    def _rebuild_index(self) -> None:
        with self._data_lock:
            self._facts_index = {}
            for i, mem in enumerate(self.facts):
                self._index_fact(i, mem["fact"])

    def _index_fact(self, idx: int, fact_text: str) -> None:
        # No lock needed - always called with _data_lock held
        self._facts_index[idx] = set(re.findall(r"\b\w{3,}\b", fact_text.lower()))


# Singleton
_memory_instance: Optional[Memory] = None


def get_memory() -> Memory:
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = Memory()
    return _memory_instance
