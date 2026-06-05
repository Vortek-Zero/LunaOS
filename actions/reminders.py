#!/usr/bin/env python3
"""
actions/reminders.py — Lembretes com data/hora, TTS e notificação desktop.
"""
import json
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from config import DATA_DIR
except ImportError:
    DATA_DIR = Path(__file__).parent.parent / "data"

REMINDERS_FILE = Path(DATA_DIR) / "reminders.json"


class ReminderManager:
    def __init__(self):
        self._reminders: list[dict] = []
        self._lock = threading.Lock()
        self._tts = None
        self._load()
        self._start_monitor()

    def _get_tts(self):
        if self._tts is None:
            from voice.tts import get_tts
            self._tts = get_tts()
        return self._tts

    # ── Parsing de data/hora ───────────────────────────────────

    def parse_datetime(self, text: str) -> Optional[datetime]:
        """Extrai data/hora de texto natural."""
        tl = text.lower()
        now = datetime.now()

        # "em X horas/minutos"
        m = re.search(r'em\s+(\d+)\s+hora[s]?', tl)
        if m:
            return now + timedelta(hours=int(m.group(1)))
        m = re.search(r'em\s+(\d+)\s+minuto[s]?', tl)
        if m:
            return now + timedelta(minutes=int(m.group(1)))

        # "daqui X horas/minutos"
        m = re.search(r'daqui\s+(\d+)\s+hora[s]?', tl)
        if m:
            return now + timedelta(hours=int(m.group(1)))
        m = re.search(r'daqui\s+(\d+)\s+minuto[s]?', tl)
        if m:
            return now + timedelta(minutes=int(m.group(1)))

        # Horário absoluto "às HH:MM" ou "às HHh"
        m = re.search(r'às?\s+(\d{1,2})[h:](\d{2})', tl)
        if m:
            h, mn = int(m.group(1)), int(m.group(2))
            target = now.replace(hour=h, minute=mn, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target
        m = re.search(r'às?\s+(\d{1,2})h\b', tl)
        if m:
            h = int(m.group(1))
            target = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

        # "amanhã às HH"
        if "amanhã" in tl or "amanha" in tl:
            m = re.search(r'(\d{1,2})[h:](\d{2})', tl)
            if m:
                h, mn = int(m.group(1)), int(m.group(2))
                return (now + timedelta(days=1)).replace(hour=h, minute=mn, second=0, microsecond=0)
            return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

        # Dias da semana
        days_map = {"segunda": 0, "terça": 1, "terca": 1, "quarta": 2,
                    "quinta": 3, "sexta": 4, "sábado": 5, "sabado": 5, "domingo": 6}
        for day_name, day_num in days_map.items():
            if day_name in tl:
                days_ahead = (day_num - now.weekday()) % 7 or 7
                target = now + timedelta(days=days_ahead)
                m = re.search(r'(\d{1,2})[h:](\d{2})', tl)
                if m:
                    return target.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
                return target.replace(hour=9, minute=0, second=0, microsecond=0)

        return None

    def extract_message(self, text: str) -> str:
        """Extrai a mensagem do lembrete."""
        tl = text.lower()
        # Remove prefixos de comando
        for prefix in ["me lembra de", "me lembre de", "lembra de", "lembre de",
                        "me avisa para", "me avisa de", "criar lembrete"]:
            if prefix in tl:
                tl = tl.replace(prefix, "").strip()
                break
        # Remove partes de tempo
        tl = re.sub(r'(?:às?|as|em|daqui|amanhã|amanha)\s+\d+[h:]\d*\s*(?:horas?|minutos?)?', '', tl)
        tl = re.sub(r'\d+\s*(?:horas?|minutos?)', '', tl)
        tl = re.sub(r'(?:segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)', '', tl)
        return tl.strip() or "lembrete"

    # ── CRUD ──────────────────────────────────────────────────

    def add(self, message: str, when: datetime) -> str:
        with self._lock:
            self._reminders.append({
                "message": message,
                "when": when.isoformat(),
                "done": False,
            })
            self._save()
        return f"🔔 Lembrete criado: '{message}' para {when.strftime('%d/%m às %H:%M')}."

    def list_reminders(self) -> str:
        with self._lock:
            pending = [r for r in self._reminders if not r["done"]]
        if not pending:
            return "Nenhum lembrete ativo."
        lines = ["📋 Lembretes:"]
        for i, r in enumerate(pending, 1):
            when = datetime.fromisoformat(r["when"])
            lines.append(f"  {i}. {r['message']} — {when.strftime('%d/%m às %H:%M')}")
        return "\n".join(lines)

    def cancel(self, query: str) -> str:
        with self._lock:
            for r in self._reminders:
                if not r["done"] and query.lower() in r["message"].lower():
                    r["done"] = True
                    self._save()
                    return f"Lembrete '{r['message']}' cancelado."
        return f"Lembrete '{query}' não encontrado."

    # ── Monitor em background ──────────────────────────────────

    def _start_monitor(self) -> None:
        def _monitor():
            while True:
                time.sleep(15)
                now = datetime.now()
                with self._lock:
                    for r in self._reminders:
                        if r["done"]:
                            continue
                        when = datetime.fromisoformat(r["when"])
                        if when <= now:
                            r["done"] = True
                            self._save()
                            self._fire(r["message"])
        threading.Thread(target=_monitor, daemon=True).start()

    def _fire(self, message: str) -> None:
        print(f"\n[Reminder] 🔔 {message}")
        if shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "🔔 Lembrete", message],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self._get_tts().speak(f"Lembrete: {message}", blocking=False)
        except Exception:
            pass

    def _load(self) -> None:
        try:
            if REMINDERS_FILE.exists():
                self._reminders = json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._reminders = []

    def _save(self) -> None:
        REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        REMINDERS_FILE.write_text(
            json.dumps(self._reminders, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Interface natural ──────────────────────────────────────

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower()

        if any(w in tl for w in ["quais são meus lembretes", "ver lembretes", "meus lembretes",
                                   "lista de lembretes", "lembretes ativos"]):
            return self.list_reminders()

        if any(w in tl for w in ["cancela o lembrete", "cancele o lembrete", "remove o lembrete"]):
            m = re.search(r'lembrete\s+(?:do\s+|da\s+|de\s+)?(.+)', tl)
            query = m.group(1).strip() if m else ""
            return self.cancel(query)

        if any(w in tl for w in ["me lembra", "me lembre", "lembra de", "lembre de",
                                   "criar lembrete", "me avisa"]):
            when = self.parse_datetime(tl)
            if not when:
                return "Não entendi quando você quer ser lembrado. Tente: 'me lembra de [algo] às 15h'."
            message = self.extract_message(text)
            return self.add(message, when)

        return None


# Singleton
_reminder_instance: Optional[ReminderManager] = None

def get_reminders() -> ReminderManager:
    global _reminder_instance
    if _reminder_instance is None:
        _reminder_instance = ReminderManager()
    return _reminder_instance
