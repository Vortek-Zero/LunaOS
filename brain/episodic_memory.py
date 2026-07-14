#!/usr/bin/env python3
"""
brain/episodic_memory.py — Memória Episódica da Luna
Lembra experiências com timestamp, tópicos e contexto — não só fatos isolados.
"""

import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

try:
    from config import DATA_DIR
except ImportError:
    DATA_DIR = Path(__file__).parent.parent / "data"

EPISODES_FILE = Path(DATA_DIR) / "episodes.json"

# Tópicos reconhecidos automaticamente
_TOPIC_PATTERNS = {
    "programação": [
        "python",
        "rust",
        "javascript",
        "html",
        "css",
        "código",
        "programa",
        "projeto",
        "github",
        "git",
        "bug",
        "debug",
        "api",
        "backend",
        "frontend",
    ],
    "estudo": [
        "estudei",
        "estudando",
        "aprendi",
        "aprendo",
        "aula",
        "etec",
        "escola",
        "curso",
        "módulo",
        "exercício",
        "prova",
    ],
    "luna": ["luna", "assistente", "ia", "sistema", "ferramenta", "melhorar", "versão"],
    "jogos": ["jogo", "game", "jogar", "partida", "vencer", "perder"],
    "música": ["música", "tocar", "spotify", "rádio", "playlist"],
    "casa": ["luz", "tuya", "casa", "sala", "quarto", "dispositivo"],
    "trabalho": ["freela", "cliente", "projeto", "dinheiro", "vender", "entregar"],
    "saúde": ["dormi", "acordei", "comeu", "exercício", "academia", "cansado"],
    "math": ["cálculo", "matemática", "fórmula", "equação"],
}


def _extract_topics(text: str) -> list[str]:
    """Extrai tópicos do texto por palavras-chave."""
    tl = text.lower()
    found = []
    for topic, keywords in _TOPIC_PATTERNS.items():
        if any(kw in tl for kw in keywords):
            found.append(topic)
    return found or ["geral"]


class EpisodicMemory:
    """
    Memória de experiências com contexto temporal.
    Diferente dos fatos (o que o usuário gosta), aqui ficam os eventos
    (o que aconteceu, quando e como foi).
    """

    def __init__(self):
        self._episodes: list[dict] = []
        self._lock = threading.Lock()
        self._load()

    def log_episode(
        self,
        text: str,
        response_summary: str = "",
        topics: list[str] | None = None,
        action_type: str = "conversa",
        outcome: str = "ok",
    ) -> None:
        """
        Registra uma experiência.
        Chamado automaticamente pelo luna_core após cada interação relevante.
        """
        if not text or not text.strip():
            return

        topics = topics or _extract_topics(text)
        now = datetime.now()

        episode = {
            "id": f"ep_{int(now.timestamp() * 1000)}",
            "ts": now.isoformat(),
            "date": now.date().isoformat(),
            "hour": now.hour,
            "weekday": now.strftime("%A"),
            "text": text[:200],
            "summary": response_summary[:200] if response_summary else "",
            "topics": topics,
            "action_type": action_type,
            "outcome": outcome,
        }

        with self._lock:
            self._episodes.append(episode)
            # Mantém apenas os últimos 2000 episódios
            if len(self._episodes) > 2000:
                self._episodes = self._episodes[-1500:]
            self._save()

    def recall(self, query: str, days: int = 30, limit: int = 5) -> list[dict]:
        """
        Busca episódios relevantes por tópico, palavras-chave ou data.
        Retorna lista de episódios ordenados do mais recente.
        """
        cutoff = datetime.now() - timedelta(days=days)
        query_lower = query.lower()
        query_words = set(w for w in re.split(r"\W+", query_lower) if len(w) > 3)
        query_topics = _extract_topics(query)

        scored = []
        with self._lock:
            for ep in reversed(self._episodes):
                try:
                    ep_dt = datetime.fromisoformat(ep["ts"])
                except Exception:
                    continue
                if ep_dt < cutoff:
                    continue

                score = 0
                ep_text = ep.get("text", "").lower()
                ep_topics = ep.get("topics", [])

                # Pontos por tópico em comum
                topic_overlap = len(set(query_topics) & set(ep_topics))
                score += topic_overlap * 3

                # Pontos por palavras em comum
                ep_words = set(w for w in re.split(r"\W+", ep_text) if len(w) > 3)
                word_overlap = len(query_words & ep_words)
                score += word_overlap

                if score > 0:
                    scored.append((score, ep))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:limit]]

    def get_recent_summary(self, n_days: int = 7) -> str:
        """
        Resumo dos últimos N dias para injetar no contexto do LLM.
        Retorna texto compacto com os episódios mais relevantes.
        """
        cutoff = datetime.now() - timedelta(days=n_days)
        recent = []

        with self._lock:
            for ep in reversed(self._episodes):
                try:
                    ep_dt = datetime.fromisoformat(ep["ts"])
                except Exception:
                    continue
                if ep_dt < cutoff:
                    break
                recent.append(ep)

        if not recent:
            return ""

        # Agrupa por tópico/dia
        lines = [f"[MEMÓRIA EPISÓDICA — últimos {n_days} dias]"]
        seen_topics: set = set()

        for ep in recent[:15]:  # Limita a 15 episódios no contexto
            date_str = ep.get("date", "")
            topics = ep.get("topics", ["geral"])
            text_snippet = ep.get("text", "")[:80]
            topic_key = tuple(sorted(topics))

            if topic_key not in seen_topics:
                seen_topics.add(topic_key)
            topics_str = ", ".join(topics)
            lines.append(f"• {date_str} [{topics_str}]: {text_snippet}")

        return "\n".join(lines)

    def format_for_user(self, episodes: list[dict]) -> str:
        """Formata episódios para resposta ao usuário."""
        if not episodes:
            return "Não encontrei episódios relevantes."
        lines = []
        for ep in episodes:
            date_str = ep.get("date", "")
            hour = ep.get("hour", "?")
            topics = ", ".join(ep.get("topics", []))
            text = ep.get("text", "")
            lines.append(f"📅 {date_str} às {hour}h [{topics}]\n   {text}")
        return "\n\n".join(lines)

    def get_episode_count(self) -> int:
        """Retorna a quantidade de episódios armazenados (thread-safe)."""
        with self._lock:
            return len(self._episodes)

    def _load(self):
        try:
            if EPISODES_FILE.exists():
                self._episodes = json.loads(EPISODES_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._episodes = []

    def _save(self):
        EPISODES_FILE.parent.mkdir(parents=True, exist_ok=True)
        EPISODES_FILE.write_text(json.dumps(self._episodes, ensure_ascii=False, indent=2), encoding="utf-8")


# Singleton
_instance: EpisodicMemory | None = None


def get_episodic_memory() -> EpisodicMemory:
    global _instance
    if _instance is None:
        _instance = EpisodicMemory()
    return _instance
