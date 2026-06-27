#!/usr/bin/env python3
"""
actions/morse.py — Escreve texto em código Morse piscando a luz da sala.
Ponto  = flash curto  (0.3s)
Traço  = flash longo  (0.9s)
Espaço entre símbolos = 0.3s apagado
Espaço entre letras   = 0.9s apagado
Espaço entre palavras = 2.0s apagado
"""
import time
import threading

try:
    import tinytuya
    _TUYA_OK = True
except ImportError:
    _TUYA_OK = False

DEVICE_ID = "eb64a81b56fb8003dexqdd"
LOCAL_KEY  = "Ek&~Ah`=4s}5.'Z#"
IP_DEVICE  = "192.168.1.15"

MORSE = {
    'A':'.-','B':'-...','C':'-.-.','D':'-..','E':'.','F':'..-.','G':'--.','H':'....','I':'..','J':'.---',
    'K':'-.-','L':'.-..','M':'--','N':'-.','O':'---','P':'.--.','Q':'--.-','R':'.-.','S':'...','T':'-',
    'U':'..-','V':'...-','W':'.--','X':'-..-','Y':'-.--','Z':'--..',
    '0':'-----','1':'.----','2':'..---','3':'...--','4':'....-','5':'.....',
    '6':'-....','7':'--...','8':'---..','9':'----.',
    ' ': ' ',
}

DOT   = 0.3
DASH  = 0.9
SYM   = 0.3   # pausa entre símbolos da mesma letra
LETTER= 0.9   # pausa entre letras
WORD  = 2.0   # pausa entre palavras

# Estado de pendência: aguardando o texto a converter
_pending = False


def _device():
    if not _TUYA_OK:
        return None
    return tinytuya.OutletDevice(dev_id=DEVICE_ID, address=IP_DEVICE, local_key=LOCAL_KEY, version=3.4)


def _flash(dev, duration: float):
    dev.set_status(True)
    time.sleep(duration)
    dev.set_status(False)


def _transmit(text: str):
    dev = _device()
    if dev is None:
        return
    text = text.upper()
    for i, ch in enumerate(text):
        code = MORSE.get(ch)
        if code is None:
            continue
        if code == ' ':
            time.sleep(WORD)
            continue
        for j, sym in enumerate(code):
            _flash(dev, DOT if sym == '.' else DASH)
            if j < len(code) - 1:
                time.sleep(SYM)
        if i < len(text) - 1 and text[i + 1] != ' ':
            time.sleep(LETTER)
    # Garante luz apagada no fim
    try:
        dev.set_status(False)
    except Exception:
        pass


def text_to_morse(text: str) -> str:
    """Retorna a representação visual do morse (ex: '... --- ...')."""
    result = []
    for ch in text.upper():
        code = MORSE.get(ch)
        if code == ' ':
            result.append('/')
        elif code:
            result.append(code)
    return ' '.join(result)


def handle(cmd: str) -> str | None:
    global _pending
    c = cmd.lower()

    # Detecta intenção de morse
    _morse_kw = ["morse", "código morse", "codigo morse", "transmita em morse", "pisca em morse"]
    if not any(w in c for w in _morse_kw):
        # Se estava aguardando texto, este cmd É o texto
        if _pending:
            _pending = False
            morse_str = text_to_morse(cmd)
            threading.Thread(target=_transmit, args=(cmd,), daemon=True).start()
            return f"Transmitindo em morse: {morse_str}"
        return None

    # Tem "morse" no comando — extrai o texto após a keyword
    for kw in ["transmita em morse", "codigo morse", "código morse", "morse"]:
        if kw in c:
            after = c.split(kw, 1)[-1].strip().lstrip(',:- ')
            if after:
                morse_str = text_to_morse(after)
                threading.Thread(target=_transmit, args=(after,), daemon=True).start()
                return f"Transmitindo em morse: {morse_str}"
            break

    # Não veio texto junto — pede ao usuário
    _pending = True
    return "O que você quer que eu escreva em morse?"


class _MorseAccessor:
    def handle(self, cmd):
        return handle(cmd)

    @property
    def _pending(self):
        return globals().get("_pending", False)


_instance = None

def get_morse():
    global _instance
    if _instance is None:
        _instance = _MorseAccessor()
    return _instance
