#!/usr/bin/env python3
"""
brain/chat_db.py — Memória SQL (SQLite) para histórico de chats por sessão.
Substitui o JSON de sessões em brain/memory.py com persistência robusta.
"""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "chat_history.db"

_local = threading.local()


def _conn() -> sqlite3.Connection:
    """Retorna conexão thread-local."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def init_db() -> None:
    c = _conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id      TEXT PRIMARY KEY,
            title   TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role       TEXT NOT NULL CHECK(role IN ('user','assistant')),
            text       TEXT NOT NULL,
            ts         TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
    """)
    c.commit()
    # Garante sessão default
    _ensure_session("default", "Conversa padrão")


def _ensure_session(session_id: str, title: str = "") -> None:
    c = _conn()
    now = datetime.now().isoformat()
    c.execute(
        "INSERT OR IGNORE INTO sessions(id, title, created, updated) VALUES (?,?,?,?)",
        (session_id, title or session_id, now, now),
    )
    c.commit()


# ── Sessões ────────────────────────────────────────────────────

def list_sessions() -> list[dict]:
    rows = _conn().execute(
        "SELECT id, title, created, updated FROM sessions ORDER BY updated DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def create_session(session_id: str, title: str = "") -> None:
    _ensure_session(session_id, title or session_id)


def rename_session(session_id: str, new_title: str) -> bool:
    c = _conn()
    c.execute(
        "UPDATE sessions SET title=?, updated=? WHERE id=?",
        (new_title, datetime.now().isoformat(), session_id),
    )
    c.commit()
    return c.execute("SELECT changes()").fetchone()[0] > 0


def delete_session(session_id: str) -> bool:
    if session_id == "default":
        return False
    c = _conn()
    c.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    c.commit()
    return c.execute("SELECT changes()").fetchone()[0] > 0


# ── Mensagens ──────────────────────────────────────────────────

def add_message(session_id: str, role: str, text: str) -> None:
    _ensure_session(session_id)
    now = datetime.now().isoformat()
    c = _conn()
    c.execute(
        "INSERT INTO messages(session_id, role, text, ts) VALUES (?,?,?,?)",
        (session_id, role, text, now),
    )
    c.execute(
        "UPDATE sessions SET updated=? WHERE id=?",
        (now, session_id),
    )
    c.commit()


def add_exchange(session_id: str, user_text: str, assistant_text: str) -> None:
    _ensure_session(session_id)
    now = datetime.now().isoformat()
    c = _conn()
    c.execute(
        "INSERT INTO messages(session_id, role, text, ts) VALUES (?,?,?,?)",
        (session_id, "user", user_text, now),
    )
    c.execute(
        "INSERT INTO messages(session_id, role, text, ts) VALUES (?,?,?,?)",
        (session_id, "assistant", assistant_text, now),
    )
    c.execute("UPDATE sessions SET updated=? WHERE id=?", (now, session_id))
    c.commit()


def get_history(session_id: str, last_n: int = 20) -> list[dict]:
    rows = _conn().execute(
        """SELECT role, text, ts FROM messages
           WHERE session_id=?
           ORDER BY id DESC LIMIT ?""",
        (session_id, last_n * 2),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_history_text(session_id: str, last_n: int = 5) -> str:
    msgs = get_history(session_id, last_n)
    lines = []
    for m in msgs:
        prefix = "Usuário" if m["role"] == "user" else "Luna"
        lines.append(f"{prefix}: {m['text']}")
    return "\n".join(lines)


def clear_session_history(session_id: str) -> None:
    c = _conn()
    c.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
    c.commit()


# Singleton init
_initialized = False


def get_chat_db():
    global _initialized
    if not _initialized:
        init_db()
        _initialized = True
    return _ChatDB()


class _ChatDB:
    """Wrapper de conveniência para uso no Memory."""
    list_sessions = staticmethod(list_sessions)
    create_session = staticmethod(create_session)
    rename_session = staticmethod(rename_session)
    delete_session = staticmethod(delete_session)
    add_exchange = staticmethod(add_exchange)
    get_history = staticmethod(get_history)
    get_history_text = staticmethod(get_history_text)
    clear_session_history = staticmethod(clear_session_history)
