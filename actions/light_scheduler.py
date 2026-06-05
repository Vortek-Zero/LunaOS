#!/usr/bin/env python3
"""
actions/light_scheduler.py — Agendamentos programáveis para as luzes.
Persiste em data/light_schedules.json e roda monitor em background.
"""
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from config import DATA_DIR
except ImportError:
    DATA_DIR = Path(__file__).parent.parent / "data"

SCHEDULES_FILE = Path(DATA_DIR) / "light_schedules.json"


class LightScheduler:
    def __init__(self):
        self._schedules: list[dict] = []  # [{id, hour, minute, state, days, enabled, label}]
        self._lock = threading.Lock()
        self._load()
        self._start_monitor()

    # ── CRUD ──────────────────────────────────────────────────

    def add(self, hour: int, minute: int, state: bool,
            days: list[int] = None, label: str = "") -> str:
        """
        Adiciona agendamento.
        days: lista de dias da semana (0=seg..6=dom), None = todos os dias.
        state: True=ligar, False=apagar.
        """
        sid = f"ls_{int(time.time()*1000)}"
        entry = {
            "id": sid,
            "hour": hour,
            "minute": minute,
            "state": state,
            "days": days,          # None = todos
            "enabled": True,
            "label": label or f"{'Ligar' if state else 'Apagar'} às {hour:02d}:{minute:02d}",
        }
        with self._lock:
            self._schedules.append(entry)
            self._save()
        return f"✅ Agendamento criado: {entry['label']}"

    def remove(self, sid: str) -> bool:
        with self._lock:
            before = len(self._schedules)
            self._schedules = [s for s in self._schedules if s["id"] != sid]
            self._save()
        return len(self._schedules) < before

    def toggle(self, sid: str) -> Optional[str]:
        with self._lock:
            for s in self._schedules:
                if s["id"] == sid:
                    s["enabled"] = not s["enabled"]
                    self._save()
                    return f"{'Ativado' if s['enabled'] else 'Pausado'}: {s['label']}"
        return None

    def list_schedules(self) -> list[dict]:
        with self._lock:
            return list(self._schedules)

    def list_text(self) -> str:
        with self._lock:
            if not self._schedules:
                return "Nenhum agendamento de luz configurado."
            lines = ["📅 Agendamentos de luz:"]
            days_names = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
            for s in self._schedules:
                days_str = "todos os dias" if s["days"] is None else \
                           ", ".join(days_names[d] for d in s["days"])
                status = "✓" if s["enabled"] else "⏸"
                action = "Ligar" if s["state"] else "Apagar"
                lines.append(f"  {status} {s['hour']:02d}:{s['minute']:02d} — {action} ({days_str})")
            return "\n".join(lines)

    # ── Monitor ───────────────────────────────────────────────

    def _start_monitor(self):
        t = threading.Thread(target=self._monitor_loop, daemon=True)
        t.start()

    def _monitor_loop(self):
        last_fired: set = set()  # evita disparar duas vezes no mesmo minuto
        while True:
            now = datetime.now()
            key = (now.hour, now.minute, now.weekday(), now.date().isoformat())
            with self._lock:
                schedules = list(self._schedules)
            for s in schedules:
                if not s["enabled"]:
                    continue
                if s["hour"] != now.hour or s["minute"] != now.minute:
                    continue
                if s["days"] is not None and now.weekday() not in s["days"]:
                    continue
                fire_key = (s["id"], key)
                if fire_key in last_fired:
                    continue
                last_fired.add(fire_key)
                self._fire(s)
            # Limpa chaves antigas (> 2 min atrás)
            last_fired = {k for k in last_fired if k[1][3] == now.date().isoformat()}
            time.sleep(20)  # verifica a cada 20s

    def _fire(self, schedule: dict):
        try:
            from actions.lights import _set_light
            result = _set_light(schedule["state"])
            print(f"[LightScheduler] Disparado: {schedule['label']} → {result}")
            # Notificação TTS
            try:
                from voice.tts import get_tts
                action = "ligada" if schedule["state"] else "apagada"
                get_tts().speak(f"Luz da sala {action} automaticamente.", blocking=False)
            except Exception:
                pass
        except Exception as e:
            print(f"[LightScheduler] Erro ao disparar: {e}")

    # ── Persistência ──────────────────────────────────────────

    def _load(self):
        try:
            if SCHEDULES_FILE.exists():
                self._schedules = json.loads(SCHEDULES_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._schedules = []

    def _save(self):
        SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCHEDULES_FILE.write_text(
            json.dumps(self._schedules, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Parser de linguagem natural ───────────────────────────

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower().strip()

        # Listar
        if any(w in tl for w in ["agendamentos", "horários programados", "programações de luz"]):
            return self.list_text()

        # Remover
        m = re.search(r'(?:remove|cancela|apaga)\s+agendamento\s+(\S+)', tl)
        if m:
            ok = self.remove(m.group(1))
            return "Agendamento removido." if ok else "Agendamento não encontrado."

        # Detecta hora + ação
        # Ex: "apagar a luz às 21h", "ligar a luz às 7:30", "luz apagada às 22:00"
        time_m = re.search(r'(\d{1,2})[h:](\d{0,2})', tl)
        if not time_m:
            return None

        hour = int(time_m.group(1))
        minute = int(time_m.group(2)) if time_m.group(2) else 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None

        # Detecta ação
        _on_kw  = ["liga", "ligar", "acende", "acender", "ativa", "ativar", "ligue", "acenda"]
        _off_kw = ["apaga", "apagar", "desliga", "desligar", "apague", "desligue"]
        state = None
        if any(w in tl for w in _on_kw):
            state = True
        elif any(w in tl for w in _off_kw):
            state = False
        if state is None:
            return None

        # Detecta dias específicos
        day_map = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "sáb": 5, "dom": 6}
        days = None
        found_days = [v for k, v in day_map.items() if k in tl]
        if found_days:
            days = found_days
        elif "semana" in tl and "fim" not in tl:
            days = [0, 1, 2, 3, 4]
        elif "fim de semana" in tl or "fds" in tl:
            days = [5, 6]

        return self.add(hour, minute, state, days)


# Singleton
_instance: Optional[LightScheduler] = None

def get_light_scheduler() -> LightScheduler:
    global _instance
    if _instance is None:
        _instance = LightScheduler()
    return _instance
