#!/usr/bin/env python3
import time
import threading
import subprocess
import re
from typing import Dict, Optional
from voice.tts import get_tts

class TimerManager:
    def __init__(self):
        self.timers: Dict[str, threading.Timer] = {}
        self.timer_ends: Dict[str, float] = {}

    def _notify(self, name: str):
        # Alarme visual (pisca a luz da sala) - REMOVIDO A PEDIDO DO USUÁRIO
        # try:
        #     from actions.party import visual_alarm
        #     threading.Thread(target=visual_alarm, daemon=True).start()
        # except Exception:
        #     pass
        # Fala
        tts = get_tts()
        msg = f"Atenção! Seu timer para {name} terminou!"
        tts.speak(msg, blocking=False)
        # Notificação de sistema
        try:
            subprocess.run(["notify-send", "-u", "critical", "Luna: Timer Terminou", msg], check=False)
        except Exception:
            pass
        
        # Limpa
        if name in self.timers:
            del self.timers[name]
        if name in self.timer_ends:
            del self.timer_ends[name]

    def add_timer(self, duration_sec: int, name: str = "Padrão"):
        # Cancela se já existir com esse nome
        if name in self.timers:
            self.timers[name].cancel()

        t = threading.Timer(duration_sec, self._notify, args=[name])
        t.daemon = True
        self.timers[name] = t
        self.timer_ends[name] = time.time() + duration_sec
        t.start()

    def cancel_timer(self, name: str = "Padrão") -> bool:
        if name in self.timers:
            self.timers[name].cancel()
            del self.timers[name]
            del self.timer_ends[name]
            return True
        return False

    def status(self) -> str:
        if not self.timers:
            return "Nenhum timer ativo no momento."
        
        now = time.time()
        lines = ["Timers ativos:"]
        for name, end_t in self.timer_ends.items():
            rem = int(end_t - now)
            if rem > 0:
                mins, secs = divmod(rem, 60)
                lines.append(f"- {name}: {mins}m {secs}s restantes")
        return "\n".join(lines)

    def handle(self, command: str) -> str:
        cmd = command.lower()
        
        if "status" in cmd or "quanto tempo" in cmd:
            return self.status()
            
        if "cancela" in cmd or "cancelar" in cmd or "para o timer" in cmd:
            if self.timers:
                # Cancela o primeiro ou todos
                for name in list(self.timers.keys()):
                    self.cancel_timer(name)
                return "Todos os timers foram cancelados."
            return "Não há timers para cancelar."

        # Extrai duração
        minutes = 0
        seconds = 0
        
        m_min = re.search(r'(\d+)\s*(?:minuto|minutos|min|m\b)', cmd)
        if m_min:
            minutes = int(m_min.group(1))
            
        m_sec = re.search(r'(\d+)\s*(?:segundo|segundos|seg\b)', cmd)
        if m_sec:
            seconds = int(m_sec.group(1))
            
        if minutes == 0 and seconds == 0:
            return "" # não conseguiu parsear o tempo
            
        total_sec = minutes * 60 + seconds
        
        # Extrai nome do timer (ex: "para o macarrão")
        name = "Padrão"
        m_name = re.search(r'para o (.+)|para a (.+)|do (.+)|da (.+)', cmd)
        if m_name:
            # Pega o primeiro grupo não nulo
            for g in m_name.groups():
                if g:
                    name = g.strip()
                    break

        self.add_timer(total_sec, name)
        
        time_str = []
        if minutes > 0:
            time_str.append(f"{minutes} minutos")
        if seconds > 0:
            time_str.append(f"{seconds} segundos")
        
        return f"Timer de {' e '.join(time_str)} iniciado para: {name}."

_instance = None
def get_timer() -> TimerManager:
    global _instance
    if _instance is None:
        _instance = TimerManager()
    return _instance
