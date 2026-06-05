#!/usr/bin/env python3
"""
actions/notes.py — Notas rápidas persistentes.
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from config import DATA_DIR
except ImportError:
    DATA_DIR = Path(__file__).parent.parent / "data"

NOTES_FILE = Path(DATA_DIR) / "notes.json"


class NotesManager:
    def __init__(self):
        self._notes: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            if NOTES_FILE.exists():
                self._notes = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._notes = []

    def _save(self) -> None:
        NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        NOTES_FILE.write_text(json.dumps(self._notes, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, text: str) -> str:
        text = text.strip()
        if not text:
            return "O que você quer anotar?"
        self._notes.append({"text": text, "ts": datetime.now().isoformat()})
        self._save()
        return f"📝 Anotado: '{text}'"

    def list_notes(self) -> str:
        if not self._notes:
            return "Nenhuma nota salva."
        lines = ["📋 Suas notas:"]
        for i, note in enumerate(self._notes, 1):
            ts = datetime.fromisoformat(note["ts"]).strftime("%d/%m %H:%M")
            lines.append(f"  {i}. [{ts}] {note['text']}")
        return "\n".join(lines)

    def delete(self, index: int) -> str:
        if index < 1 or index > len(self._notes):
            return f"Nota {index} não existe. Você tem {len(self._notes)} nota(s)."
        removed = self._notes.pop(index - 1)
        self._save()
        return f"🗑 Nota removida: '{removed['text']}'"

    def search(self, query: str) -> str:
        query_lower = query.lower()
        results = [n for n in self._notes if query_lower in n["text"].lower()]
        if not results:
            return f"Nenhuma nota encontrada com '{query}'."
        lines = [f"🔍 Notas com '{query}':"]
        for i, note in enumerate(results, 1):
            lines.append(f"  {i}. {note['text']}")
        return "\n".join(lines)

    def clear(self) -> str:
        count = len(self._notes)
        self._notes = []
        self._save()
        return f"{count} nota(s) apagada(s)."

    def format_for_tts(self) -> str:
        if not self._notes:
            return "Você não tem nenhuma nota salva."
        if len(self._notes) == 1:
            return f"Você tem 1 nota: {self._notes[0]['text']}."
        texts = [n["text"] for n in self._notes]
        return f"Você tem {len(texts)} notas: " + ". ".join(texts) + "."

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower()

        # Listar / Ler
        if any(w in tl for w in ["ver notas", "minhas notas", "lista de notas",
                                   "leia as notas", "ler as notas", "mostra as notas"]):
            return self.list_notes()

        # Buscar
        m = re.search(r'(?:busca|pesquisa|procura)\s+(?:nas notas|nas anotações)[:\s]+(.+)', tl)
        if m:
            return self.search(m.group(1).strip())

        # Apagar por índice
        m = re.search(r'(?:apaga|apague|deleta|delete|remove|remova)\s+(?:a\s+)?nota\s+(\d+)', tl)
        if m:
            return self.delete(int(m.group(1)))

        # Limpar tudo
        if any(w in tl for w in ["apaga todas as notas", "limpa as notas", "limpar notas"]):
            return self.clear()

        # Anotar
        m = re.search(r'(?:anota|anote|nota|registra|registre|salva|salve)[:\s]+(.+)', tl)
        if m:
            return self.add(m.group(1).strip())

        return None


# Singleton
_notes_instance: Optional[NotesManager] = None

def get_notes() -> NotesManager:
    global _notes_instance
    if _notes_instance is None:
        _notes_instance = NotesManager()
    return _notes_instance
