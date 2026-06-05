#!/usr/bin/env python3
"""
actions/party.py — Modos de piscada da luz da sala.
Balada, SOS, metrônomo, contagem regressiva, timer de luz.
"""
import time
import random
import threading
import re

try:
    import tinytuya
    _TUYA_OK = True
except ImportError:
    _TUYA_OK = False

DEVICE_ID = "eb64a81b56fb8003dexqdd"
LOCAL_KEY  = "Ek&~Ah`=4s}5.'Z#"
IP_DEVICE  = "192.168.1.5"

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _device():
    if not _TUYA_OK:
        return None
    return tinytuya.OutletDevice(dev_id=DEVICE_ID, address=IP_DEVICE, local_key=LOCAL_KEY, version=3.4)


def _flash(dev, on: float, off: float = 0.0):
    dev.set_status(True);  time.sleep(on)
    dev.set_status(False)
    if off: time.sleep(off)


# ── Padrões balada ────────────────────────────────────────────

def _strobe(dev):
    for _ in range(20):
        if _stop_event.is_set(): return
        _flash(dev, 0.05, 0.05)

def _pulse(dev):
    for _ in range(8):
        if _stop_event.is_set(): return
        _flash(dev, 0.4, 0.4)

def _random_burst(dev):
    for _ in range(15):
        if _stop_event.is_set(): return
        _flash(dev, random.uniform(0.05, 0.3), random.uniform(0.05, 0.25))

def _sos_beat(dev):
    for _ in range(3):
        if _stop_event.is_set(): return
        for d in [0.1, 0.1, 0.1, 0.4]:
            _flash(dev, d, 0.1)
        time.sleep(0.3)

def _wave(dev):
    for _ in range(6):
        if _stop_event.is_set(): return
        _flash(dev, 0.6, 0.15)

PARTY_PATTERNS = [_strobe, _pulse, _random_burst, _sos_beat, _wave]


def _party_loop():
    dev = _device()
    if not dev: return
    try:
        while not _stop_event.is_set():
            random.choice(PARTY_PATTERNS)(dev)
            if not _stop_event.is_set():
                time.sleep(random.uniform(0.1, 0.4))
    finally:
        try: dev.set_status(False)
        except Exception: pass


# ── SOS contínuo ─────────────────────────────────────────────

def _sos_loop():
    """... --- ... repetido até parar."""
    dev = _device()
    if not dev: return
    DOT, DASH, SYM, LETTER, WORD = 0.2, 0.6, 0.2, 0.6, 1.5
    try:
        while not _stop_event.is_set():
            for sym in ['.','.','.','-','-','-','.','.','.']: 
                if _stop_event.is_set(): break
                _flash(dev, DOT if sym == '.' else DASH, SYM)
            if not _stop_event.is_set():
                time.sleep(WORD)
    finally:
        try: dev.set_status(False)
        except Exception: pass


# ── Metrônomo ─────────────────────────────────────────────────

def _metronome_loop(bpm: int):
    dev = _device()
    if not dev: return
    interval = 60.0 / bpm
    flash_on = min(0.08, interval * 0.3)
    try:
        while not _stop_event.is_set():
            _flash(dev, flash_on)
            remaining = interval - flash_on
            # Dorme em fatias para responder ao stop_event rapidamente
            slept = 0.0
            while slept < remaining and not _stop_event.is_set():
                chunk = min(0.05, remaining - slept)
                time.sleep(chunk)
                slept += chunk
    finally:
        try: dev.set_status(False)
        except Exception: pass


# ── Contagem regressiva visual ────────────────────────────────

def _countdown_loop(n: int):
    """Pisca N vezes, pausa, N-1 vezes, ... 1 vez, flash longo final."""
    dev = _device()
    if not dev: return
    try:
        for i in range(n, 0, -1):
            if _stop_event.is_set(): break
            for _ in range(i):
                if _stop_event.is_set(): break
                _flash(dev, 0.2, 0.2)
            if i > 1 and not _stop_event.is_set():
                time.sleep(0.8)
        if not _stop_event.is_set():
            _flash(dev, 1.0)  # flash longo = largada
    finally:
        try: dev.set_status(False)
        except Exception: pass


# ── Timer de luz ──────────────────────────────────────────────

def _light_timer(seconds: int):
    """Mantém a luz acesa e apaga após N segundos."""
    dev = _device()
    if not dev: return
    try:
        dev.set_status(True)
        slept = 0
        while slept < seconds and not _stop_event.is_set():
            time.sleep(1)
            slept += 1
        dev.set_status(False)
    except Exception:
        try: dev.set_status(False)
        except Exception: pass


# ── Alarme visual (chamado externamente pelo timer.py) ────────

def visual_alarm(flashes: int = 6):
    """Pisca a luz N vezes para sinalizar alarme. Não usa _stop_event."""
    dev = _device()
    if not dev: return
    try:
        for _ in range(flashes):
            _flash(dev, 0.3, 0.3)
    finally:
        try: dev.set_status(False)
        except Exception: pass


# ── Controle de threads ───────────────────────────────────────

def _start_thread(target, *args):
    global _thread
    _stop_event.clear()
    _thread = threading.Thread(target=target, args=args, daemon=True)
    _thread.start()


def stop_all():
    _stop_event.set()
    if _thread:
        _thread.join(timeout=3)


# ── Parsing de duração ────────────────────────────────────────

def _parse_seconds(text: str) -> int | None:
    m = re.search(r'(\d+)\s*(hora|h\b|minuto|min|segundo|seg|s\b)', text)
    if not m: return None
    val, unit = int(m.group(1)), m.group(2)
    if unit.startswith('h'):   return val * 3600
    if unit.startswith('min'): return val * 60
    return val

def _parse_bpm(text: str) -> int | None:
    m = re.search(r'(\d+)\s*(?:bpm)?', text)
    return int(m.group(1)) if m else None

def _parse_count(text: str) -> int:
    m = re.search(r'(\d+)', text)
    return min(int(m.group(1)), 10) if m else 5


# ── Keywords ─────────────────────────────────────────────────

_KW_PARTY   = ["balada", "modo balada", "modo festa", "festa", "pisca louca", "discoteca", "modo disco"]
_KW_STOP    = ["para balada", "para a balada", "desliga balada", "sai da balada",
               "para festa", "modo normal", "para tudo", "cancela"]
_KW_SOS     = ["sos", "emergencia", "emergência", "socorro"]
_KW_METRO   = ["metronomo", "metrônomo", "bpm", "pisca no ritmo", "pisca em"]
_KW_COUNT   = ["contagem regressiva", "contagem", "countdown", "conta regressiva"]
_KW_TIMER   = ["timer de luz", "apaga a luz em", "apaga em", "luz por", "luz durante"]


def handle(cmd: str) -> str | None:
    c = cmd.lower()

    if any(w in c for w in _KW_STOP):
        stop_all()
        return "Parado. Luz apagada."

    if any(w in c for w in _KW_SOS):
        _start_thread(_sos_loop)
        return "SOS ativado! Diga 'para tudo' para parar."

    if any(w in c for w in _KW_METRO):
        bpm = _parse_bpm(c) or 120
        bpm = max(20, min(300, bpm))
        _start_thread(_metronome_loop, bpm)
        return f"Metrônomo a {bpm} BPM. Diga 'para tudo' para parar."

    if any(w in c for w in _KW_COUNT):
        n = _parse_count(c)
        _start_thread(_countdown_loop, n)
        return f"Contagem regressiva de {n}!"

    if any(w in c for w in _KW_TIMER):
        secs = _parse_seconds(c)
        if not secs:
            return "Quanto tempo? Ex: 'apaga a luz em 30 minutos'."
        _start_thread(_light_timer, secs)
        mins = secs // 60
        return f"Luz acesa. Apago em {mins} minuto{'s' if mins != 1 else ''}."

    if any(w in c for w in _KW_PARTY):
        _start_thread(_party_loop)
        return "Modo balada ativado! 🎉 Diga 'para balada' para parar."

    return None


_instance = None

def get_party():
    global _instance
    if _instance is None:
        _instance = type("Party", (), {"handle": staticmethod(handle)})()
    return _instance
