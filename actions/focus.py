#!/usr/bin/env python3
"""
actions/focus.py — Modo Foco / Pomodoro com TTS e log de sessões.
"""
import json
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from config import DATA_DIR
except ImportError:
    DATA_DIR = Path(__file__).parent.parent / "data"

FOCUS_LOG_FILE = Path(DATA_DIR) / "focus_log.json"


class FocusManager:
    def __init__(self):
        self._session: Optional[dict] = None  # {type, duration, end_time, thread, cancelled}
        self._lock = threading.Lock()
        self._tts = None
        self._log: list[dict] = self._load_log()

    def _get_tts(self):
        if self._tts is None:
            from voice.tts import get_tts
            self._tts = get_tts()
        return self._tts

    def _speak(self, msg: str) -> None:
        if shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "🎯 Foco", msg],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self._get_tts().speak(msg, blocking=False)
        except Exception:
            pass

    # ── Sessões ────────────────────────────────────────────────

    def start_focus(self, minutes: int = 25, label: str = "foco") -> str:
        with self._lock:
            if self._session and not self._session.get("cancelled"):
                return "Já existe uma sessão de foco ativa. Use 'cancela o foco' primeiro."

        cancel_event = threading.Event()

        def _run():
            self._speak(f"Sessão de {label} iniciada. {minutes} minutos de concentração.")
            cancelled = cancel_event.wait(timeout=minutes * 60)
            if cancelled:
                return
            with self._lock:
                self._session = None
            self._speak(f"Sessão de {label} concluída! Parabéns, você focou por {minutes} minutos.")
            self._save_session(label, minutes, "completed")

        t = threading.Thread(target=_run, daemon=True)
        with self._lock:
            self._session = {
                "type": label,
                "duration": minutes,
                "end_time": (datetime.now().timestamp() + minutes * 60),
                "cancelled": False,
                "_cancel_event": cancel_event,
            }
        t.start()
        return f"🎯 Sessão de {label} iniciada: {minutes} minutos. Bora focar!"

    def start_break(self, minutes: int = 5) -> str:
        return self.start_focus(minutes, "pausa")

    def cancel(self) -> str:
        with self._lock:
            if not self._session:
                return "Nenhuma sessão de foco ativa."
            label = self._session["type"]
            self._session["cancelled"] = True
            event = self._session.get("_cancel_event")
            self._session = None
        if event:
            event.set()
        self._speak("Sessão de foco cancelada.")
        return f"Sessão de {label} cancelada."

    def status(self) -> str:
        with self._lock:
            if not self._session or self._session.get("cancelled"):
                return "Nenhuma sessão de foco ativa."
            remaining = max(0, int(self._session["end_time"] - datetime.now().timestamp()))
            mins, secs = divmod(remaining, 60)
            return f"🎯 {self._session['type'].capitalize()} ativa: {mins}min {secs}s restantes."

    def stats(self) -> str:
        if not self._log:
            return "Nenhuma sessão de foco registrada ainda."
        total = sum(s["duration"] for s in self._log if s.get("status") == "completed")
        count = len([s for s in self._log if s.get("status") == "completed"])
        return f"📊 Sessões concluídas: {count} | Total focado: {total} minutos ({total//60}h {total%60}min)"

    # ── Persistência ───────────────────────────────────────────

    def _save_session(self, label: str, minutes: int, status: str) -> None:
        self._log.append({
            "type": label,
            "duration": minutes,
            "status": status,
            "ts": datetime.now().isoformat(),
        })
        try:
            FOCUS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            FOCUS_LOG_FILE.write_text(
                json.dumps(self._log, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _load_log(self) -> list:
        try:
            if FOCUS_LOG_FILE.exists():
                return json.loads(FOCUS_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    # ── Interface natural ──────────────────────────────────────

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower()

        if any(w in tl for w in ["cancela o foco", "cancele o foco", "para o foco", "sair do foco"]):
            return self.cancel()

        if any(w in tl for w in ["status do foco", "quanto falta no foco", "foco ativo"]):
            return self.status()

        if any(w in tl for w in ["estatísticas de foco", "historico de foco", "sessões de foco"]):
            return self.stats()

        # Pausa Pomodoro
        if any(w in tl for w in ["pausa de", "modo pausa", "iniciar pausa"]):
            m = re.search(r'(\d+)\s*(?:minutos?|min)', tl)
            mins = int(m.group(1)) if m else 5
            return self.start_break(mins)

        # Foco / Pomodoro
        if any(w in tl for w in ["modo foco", "pomodoro", "iniciar foco", "começar foco",
                                   "sessão de foco", "foco por"]):
            m = re.search(r'(\d+)\s*(?:minutos?|min)', tl)
            mins = int(m.group(1)) if m else 25
            return self.start_focus(mins)

        return None


# Singleton
_focus_instance: Optional[FocusManager] = None

def get_focus() -> FocusManager:
    global _focus_instance
    if _focus_instance is None:
        _focus_instance = FocusManager()
    return _focus_instance
