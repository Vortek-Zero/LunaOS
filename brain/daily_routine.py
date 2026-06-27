"""
brain/daily_routine.py — Sistema de Rotinas Diárias
Inspirado no OpenClaw (cron + standing orders + heartbeat)
Gerencia briefing matinal, rotinas programadas e ações proativas
"""
import json
import re
import threading
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

try:
    from config import DATA_DIR
except ImportError:
    DATA_DIR = Path(__file__).parent.parent / "data"

ROUTINES_FILE = Path(DATA_DIR) / "daily_routines.json"
ACTIVITY_LOG_FILE = Path(DATA_DIR) / "activity_log.json"


class RoutineManager:
    """
    Gerencia rotinas diárias com agendamento por horário.

    Rotina = {
        "id": str,
        "name": str,
        "hour": int,
        "minute": int,
        "actions": [{"type": "briefing"|"say"|"calendar_check"|"reminder", "params": {...}}],
        "days": None|list[int],  # None = todos, [0-6] = Seg-Dom
        "enabled": bool,
        "last_fired": str | None,  # ISO date
    }
    """
    def __init__(self, luna_core=None):
        self._routines: list[dict] = []
        self._lock = threading.Lock()
        self._luna = luna_core
        self._load()
        self._ensure_default_routines()
        self._start_monitor()

    # ── Rotinas padrão ────────────────────────────────────────

    def _ensure_default_routines(self):
        """Cria rotinas padrão se nenhuma existir."""
        with self._lock:
            if self._routines:
                return

        defaults = [
            {
                "id": "morning_briefing",
                "name": "Briefing Matinal",
                "hour": 7,
                "minute": 30,
                "actions": [{"type": "briefing", "params": {}}],
                "days": None,
                "enabled": True,
                "last_fired": None,
            },
            {
                "id": "calendar_check_morning",
                "name": "Verificação de Agenda",
                "hour": 8,
                "minute": 0,
                "actions": [{"type": "calendar_check", "params": {}}],
                "days": [0, 1, 2, 3, 4],
                "enabled": True,
                "last_fired": None,
            },
            {
                "id": "evening_wind_down",
                "name": "Resumo do Final do Dia",
                "hour": 20,
                "minute": 0,
                "actions": [{"type": "say", "params": {"message": "Hora de começar a desacelerar. Que tal revisar o dia de amanhã?"}}],
                "days": None,
                "enabled": False,
                "last_fired": None,
            },
        ]
        self._routines.extend(defaults)
        self._save()

    # ── CRUD ──────────────────────────────────────────────────

    def add_routine(self, name: str, hour: int, minute: int,
                    actions: list[dict], days: list[int] = None,
                    enabled: bool = True) -> str:
        rid = f"rt_{int(time.time()*1000)}"
        entry = {
            "id": rid,
            "name": name,
            "hour": hour,
            "minute": minute,
            "actions": actions,
            "days": days,
            "enabled": enabled,
            "last_fired": None,
        }
        with self._lock:
            self._routines.append(entry)
            self._save()
        return f"Rotina '{name}' criada para {hour:02d}:{minute:02d}."

    def remove_routine(self, rid: str) -> bool:
        with self._lock:
            before = len(self._routines)
            self._routines = [r for r in self._routines if r["id"] != rid]
            self._save()
        return len(self._routines) < before

    def toggle_routine(self, rid: str) -> Optional[str]:
        with self._lock:
            for r in self._routines:
                if r["id"] == rid:
                    r["enabled"] = not r["enabled"]
                    self._save()
                    status = "ativada" if r["enabled"] else "pausada"
                    return f"Rotina '{r['name']}' {status}."
        return None

    def list_routines_text(self) -> str:
        with self._lock:
            if not self._routines:
                return "Nenhuma rotina configurada."
            days_names = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
            lines = ["📅 Rotinas Diárias:"]
            for r in self._routines:
                days_str = "todos os dias" if r["days"] is None else ", ".join(days_names[d] for d in r["days"])
                status = "✓" if r["enabled"] else "⏸"
                actions_str = ", ".join(a["type"] for a in r["actions"])
                lines.append(f"  {status} {r['hour']:02d}:{r['minute']:02d} — {r['name']} [{actions_str}] ({days_str})")
            return "\n".join(lines)

    # ── Monitor ───────────────────────────────────────────────

    def _start_monitor(self):
        t = threading.Thread(target=self._monitor_loop, daemon=True)
        t.start()

    def _monitor_loop(self):
        last_fired: set = set()
        while True:
            time.sleep(30)
            now = datetime.now()
            today_str = now.date().isoformat()

            with self._lock:
                routines = list(self._routines)

            for r in routines:
                if not r["enabled"]:
                    continue
                if r["hour"] != now.hour or r["minute"] != now.minute:
                    continue
                if r["days"] is not None and now.weekday() not in r["days"]:
                    continue
                if r.get("last_fired") == today_str:
                    continue

                fire_key = (r["id"], today_str)
                if fire_key in last_fired:
                    continue
                last_fired.add(fire_key)

                self._execute_routine(r)
                with self._lock:
                    for stored in self._routines:
                        if stored["id"] == r["id"]:
                            stored["last_fired"] = today_str
                            self._save()
                            break

            last_fired = {k for k in last_fired if k[1] == today_str}

    def _execute_routine(self, routine: dict):
        print(f"[Routine] Executando: {routine['name']}")
        for action in routine["actions"]:
            try:
                self._dispatch_action(action)
            except Exception as e:
                print(f"[Routine] Erro na ação {action['type']}: {e}")

    def _dispatch_action(self, action: dict):
        a_type = action["type"]
        params = action.get("params", {})

        if a_type == "briefing":
            self._trigger_briefing()
        elif a_type == "say":
            message = params.get("message", "")
            if message:
                print(f"[Routine] Fala: {message}")
                self._speak(message)
        elif a_type == "calendar_check":
            self._check_calendar_proactive()
        elif a_type == "reminder":
            message = params.get("message", "")
            if message:
                self._speak(f"Lembrete: {message}")

    def _trigger_briefing(self):
        if self._luna:
            try:
                briefing = self._luna._daily_briefing()
                print(f"\n{'='*50}\n☀️ BRIEFING MATINAL AUTOMÁTICO\n{'='*50}\n{briefing}\n{'='*50}")
                self._speak(briefing)
            except Exception as e:
                print(f"[Routine] Erro ao gerar briefing: {e}")

    def _check_calendar_proactive(self):
        if not self._luna:
            return
        try:
            google = self._luna._executor.google
            if not google or not google.available:
                return
            events = google.get_events_by_date(date.today().isoformat())
            if "Nenhum" not in events:
                msg = f"Revendo sua agenda de hoje:\n{events}"
                print(f"[Routine] {msg}")
                self._speak(msg[:300])
        except Exception as e:
            print(f"[Routine] Erro ao verificar agenda: {e}")

    def _speak(self, text: str):
        try:
            from voice.tts import get_tts
            get_tts().speak(text, blocking=False)
        except Exception:
            pass

    # ── Persistência ──────────────────────────────────────────

    def _load(self):
        try:
            if ROUTINES_FILE.exists():
                self._routines = json.loads(ROUTINES_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._routines = []

    def _save(self):
        ROUTINES_FILE.parent.mkdir(parents=True, exist_ok=True)
        ROUTINES_FILE.write_text(
            json.dumps(self._routines, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Handler de linguagem natural ──────────────────────────

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower().strip()

        if any(w in tl for w in ["rotinas", "rotina", "listar rotinas", "ver rotinas"]):
            return self.list_routines_text()

        m = re.search(r'(?:remove|cancela|apaga|pausa)\s+(?:a\s+)?rotina\s+(\S+)', tl)
        if m:
            rid = m.group(1)
            if "pausa" in tl or "pausar" in tl:
                return self.toggle_routine(rid)
            ok = self.remove_routine(rid)
            return "Rotina removida." if ok else "Rotina não encontrada."

        m = re.search(r'ativa\s+(?:a\s+)?rotina\s+(\S+)', tl)
        if m:
            return self.toggle_routine(m.group(1))

        return None


# ── Activity Logger ──────────────────────────────────────────

class ActivityLogger:
    """Registra atividades do usuário para aprender padrões (inspirado no dreaming do OpenClaw)."""
    def __init__(self):
        self._log: list[dict] = []
        self._lock = threading.Lock()
        self._load()

    def log(self, action: str, details: str = ""):
        with self._lock:
            self._log.append({
                "ts": datetime.now().isoformat(),
                "action": action,
                "details": details,
            })
            self._save()

    def get_patterns(self, days: int = 7) -> dict:
        """Analisa padrões dos últimos N dias."""
        from collections import Counter
        cutoff = datetime.now().timestamp() - (days * 86400)
        recent = [e for e in self._log if datetime.fromisoformat(e["ts"]).timestamp() > cutoff]

        hour_distribution = Counter()
        action_counts = Counter()
        for e in recent:
            try:
                h = datetime.fromisoformat(e["ts"]).hour
                hour_distribution[h] += 1
            except Exception:
                pass
            action_counts[e["action"]] += 1

        peak_hours = [h for h, _ in hour_distribution.most_common(5)]
        return {
            "total_entries": len(recent),
            "peak_hours": sorted(peak_hours),
            "most_common_actions": action_counts.most_common(5),
        }

    def get_daily_summary(self) -> str:
        """Gera um resumo do dia."""
        today_str = date.today().isoformat()
        today_entries = [
            e for e in self._log
            if e["ts"].startswith(today_str)
        ]
        if not today_entries:
            return "Nenhuma atividade registrada hoje ainda."

        actions = [e["action"] for e in today_entries]
        from collections import Counter
        top = Counter(actions).most_common(5)
        lines = [f"📊 Resumo do dia ({today_str}):"]
        lines.append(f"  Total de ações: {len(today_entries)}")
        for action, count in top:
            lines.append(f"  • {action}: {count}x")
        return "\n".join(lines)

    def _load(self):
        try:
            if ACTIVITY_LOG_FILE.exists():
                self._log = json.loads(ACTIVITY_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._log = []

    def _save(self):
        ACTIVITY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if len(self._log) > 5000:
            self._log = self._log[-3000:]
        ACTIVITY_LOG_FILE.write_text(
            json.dumps(self._log, ensure_ascii=False, indent=2), encoding="utf-8"
        )


# ── Background Worker (Heartbeat estilo OpenClaw) ───────────

class BackgroundWorker:
    """
    Worker proativo estilo heartbeat do OpenClaw.
    Executa verificações periódicas em background:
    - A cada 5 minutos, verifica compromissos próximos no calendário
    - A cada 30 minutos, verifica se há algo relevante para notificar
    - Aprende padrões do usuário
    """
    def __init__(self, luna_core=None):
        self._luna = luna_core
        self._running = False
        self._thread = None
        self._notified_events: set = set()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()
        print("[BackgroundWorker] Heartbeat iniciado.")

    def stop(self):
        self._running = False

    def _heartbeat_loop(self):
        """Loop principal: verifica calendário a cada 5 min, outras tarefas periódicas."""
        calendar_interval = 300
        learning_interval = 1800
        tick = 0
        while self._running:
            time.sleep(60)
            tick += 1

            if tick % (calendar_interval // 60) == 0:
                self._check_upcoming_events()

            if tick % (learning_interval // 60) == 0:
                self._background_learning()

    def _check_upcoming_events(self):
        """Verifica se há compromissos no calendário nos próximos 30 min."""
        if not self._luna:
            return
        try:
            google = self._luna._executor.google
            if not google or not google.available:
                return

            from datetime import timedelta
            now = datetime.utcnow()
            time_min = now.isoformat() + "Z"
            time_max = (now + timedelta(hours=1)).isoformat() + "Z"

            service = google._cal()
            events = service.events().list(
                calendarId="primary", timeMin=time_min, timeMax=time_max,
                maxResults=5, singleEvents=True, orderBy="startTime"
            ).execute().get("items", [])

            for ev in events:
                ev_start = ev["start"].get("dateTime", ev["start"].get("date"))
                ev_id = ev.get("id", "")
                if ev_id in self._notified_events:
                    continue

                try:
                    dt = datetime.fromisoformat(ev_start.replace('Z', '+00:00'))
                    now_local = datetime.now()
                    mins_until = (dt - now_local).total_seconds() / 60
                    if 0 < mins_until <= 35:
                        self._notified_events.add(ev_id)
                        msg = f"Você tem um compromisso em {int(mins_until)} minutos: {ev['summary']}"
                        print(f"[BackgroundWorker] ⏰ {msg}")
                        self._speak(msg)
                except Exception:
                    pass

            if len(self._notified_events) > 200:
                self._notified_events.clear()
        except Exception as e:
            print(f"[BackgroundWorker] Erro ao verificar eventos: {e}")

    def _background_learning(self):
        """Aprende padrões do usuário baseado em horários de uso."""
        if not self._luna:
            return
        try:
            memory = self._luna._memory
            now = datetime.now()
            hour = now.hour

            if 22 <= hour or hour < 6:
                memory.remember(
                    "O usuário costuma usar o sistema à noite (após 22h)",
                    category="habitos", importance=0.5
                )
            elif 6 <= hour < 9:
                memory.remember(
                    "O usuário costuma usar o sistema pela manhã",
                    category="habitos", importance=0.5
                )
        except Exception:
            pass

    def _speak(self, text: str):
        try:
            from voice.tts import get_tts
            get_tts().speak(text, blocking=False)
        except Exception:
            pass


# Singleton
_routine_instance: Optional[RoutineManager] = None
_logger_instance: Optional[ActivityLogger] = None
_worker_instance: Optional[BackgroundWorker] = None


def get_routine_manager(luna_core=None) -> RoutineManager:
    global _routine_instance
    if _routine_instance is None:
        _routine_instance = RoutineManager(luna_core)
    elif luna_core and _routine_instance._luna is None:
        _routine_instance._luna = luna_core
    return _routine_instance


def get_activity_logger() -> ActivityLogger:
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = ActivityLogger()
    return _logger_instance


def get_background_worker(luna_core=None) -> BackgroundWorker:
    global _worker_instance
    if _worker_instance is None:
        _worker_instance = BackgroundWorker(luna_core)
    elif luna_core and _worker_instance._luna is None:
        _worker_instance._luna = luna_core
    return _worker_instance
