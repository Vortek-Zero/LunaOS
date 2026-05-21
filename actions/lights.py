#!/usr/bin/env python3
"""
actions/lights.py — Controle da luz da sala via TinyTuya.
"""
import random

try:
    import tinytuya
    _TUYA_OK = True
except ImportError:
    _TUYA_OK = False

DEVICE_ID = "eb64a81b56fb8003dexqdd"
LOCAL_KEY  = "Ek&~Ah`=4s}5.'Z#"
IP_DEVICE  = "192.168.1.5"

_RESPOSTAS_LIGA = [
    "Luz da sala ligada!",
    "Pronto, acendi a luz da sala.",
    "Luz da sala acesa.",
    "Feito! A sala está iluminada.",
    "Luz ligada, tá na clareza!",
]

_RESPOSTAS_DESLIGA = [
    "Luz da sala apagada.",
    "Pronto, apaguei a luz da sala.",
    "Sala no escuro agora.",
    "Feito! Luz da sala desligada.",
    "Luz apagada, modo cinema ativado.",
]

_KEYWORDS_LIGA    = [
    "liga", "ligar", "ligue",
    "acende", "acender", "acenda", "acendeu",
    "ativa", "ativar", "ative",
    "coloca a luz", "bota a luz", "deixa a luz",
]
_KEYWORDS_DESLIGA = [
    "desliga", "desligar", "desligue",
    "apaga", "apagar", "apague", "apagou",
    "desativa", "desativar", "desative",
    "tira a luz", "tira as luzes", "fecha a luz",
    "pode apagar", "pode desligar",
]
_KEYWORDS_LUZ     = ["luz", "luzes", "sala", "iluminacao", "iluminação", "lampada", "lâmpada"]


def _get_device():
    if not _TUYA_OK:
        return None
    return tinytuya.OutletDevice(
        dev_id=DEVICE_ID, address=IP_DEVICE, local_key=LOCAL_KEY, version=3.4
    )


def _set_light(state: bool) -> str:
    device = _get_device()
    if device is None:
        return "tinytuya não instalado — não consigo controlar a luz."
    try:
        device.set_status(state)
        return random.choice(_RESPOSTAS_LIGA if state else _RESPOSTAS_DESLIGA)
    except Exception as e:
        return f"Erro ao controlar a luz: {e}"


def handle(cmd: str) -> str | None:
    """
    Retorna resposta se o comando for sobre luz/sala, None caso contrário.
    Exige referência a luz/sala para não capturar "liga o spotify" etc.
    """
    c = cmd.lower()
    if not any(w in c for w in _KEYWORDS_LUZ):
        return None
    if any(w in c for w in _KEYWORDS_DESLIGA):
        return _set_light(False)
    if any(w in c for w in _KEYWORDS_LIGA):
        return _set_light(True)
    return None


_instance = None

def get_lights():
    global _instance
    if _instance is None:
        _instance = type("Lights", (), {"handle": staticmethod(handle)})()
    return _instance
