#!/usr/bin/env python3
"""
actions/whatsapp.py — WhatsApp sem API key oficial.

Estratégias (em ordem):
  1. Bridge local opcional (WHATSAPP_BRIDGE_URL no .env) — ex: whatsapp-web.js
  2. Automação UI do app desktop / WhatsApp Web no navegador (xdotool)
"""
import os
import re
import time
import shutil
import subprocess
from typing import Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

WHATSAPP_BRIDGE_URL = os.getenv("WHATSAPP_BRIDGE_URL", "").rstrip("/")

_LAUNCH_COMMANDS = [
    "whatsapp-native",
    "flatpak run io.github.mimbrero.WhatsAppDesktop",
    "flatpak run com.github.eneshecan.WhatsAppForLinux",
    "chromium --app=https://web.whatsapp.com",
    "firefox --new-window https://web.whatsapp.com",
]


class WhatsAppManager:
    def __init__(self):
        self._ui = None

    def _get_ui(self):
        if self._ui is None:
            from actions.ui import UIManager
            self._ui = UIManager()
        return self._ui

    def _launch(self) -> bool:
        for cmd in _LAUNCH_COMMANDS:
            bin_name = cmd.split()[0]
            if shutil.which(bin_name) or bin_name in ("flatpak", "chromium", "firefox"):
                try:
                    subprocess.Popen(
                        cmd, shell=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    time.sleep(3)
                    return True
                except Exception:
                    continue
        return False

    def _focus_whatsapp(self) -> bool:
        for tool, args in [
            ("wmctrl", ["-a", "WhatsApp"]),
            ("wmctrl", ["-a", "whatsapp"]),
            ("xdotool", ["search", "--name", "WhatsApp", "windowactivate"]),
        ]:
            if shutil.which(tool):
                try:
                    subprocess.run([tool] + args, capture_output=True, timeout=3)
                    time.sleep(0.5)
                    return True
                except Exception:
                    pass
        return False

    def open_whatsapp(self) -> str:
        if self._focus_whatsapp():
            return "WhatsApp focado."
        if self._launch():
            return "WhatsApp aberto."
        return (
            "FALHOU: WhatsApp não encontrado. Instale: "
            "yay -S whatsapp-native ou flatpak install flathub io.github.mimbrero.WhatsAppDesktop"
        )

    def _bridge_send(self, phone_or_chat: str, message: str) -> Optional[str]:
        if not WHATSAPP_BRIDGE_URL or not HAS_REQUESTS:
            return None
        try:
            r = requests.post(
                f"{WHATSAPP_BRIDGE_URL}/send",
                json={"to": phone_or_chat, "message": message},
                timeout=15,
            )
            if r.ok:
                return f"Mensagem enviada via bridge para {phone_or_chat}."
            return f"FALHOU: bridge retornou {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return f"FALHOU: bridge WhatsApp: {e}"

    def send_message(self, contact: str, message: str) -> str:
        if not contact or not message:
            return "FALHOU: contact e message são obrigatórios."

        # Tenta bridge HTTP local (sem API Meta)
        if re.match(r"^\+?\d[\d\s\-]{8,}$", contact.replace(" ", "")):
            bridged = self._bridge_send(contact, message)
            if bridged and not bridged.startswith("FALHOU"):
                return bridged

        open_res = self.open_whatsapp()
        if open_res.startswith("FALHOU"):
            return open_res

        ui = self._get_ui()
        time.sleep(1)

        # Busca contato (Ctrl+Shift+F no WhatsApp Desktop / Web)
        if shutil.which("xdotool"):
            subprocess.run(["xdotool", "key", "ctrl+shift+f"], capture_output=True, timeout=2)
        else:
            ui.press_key("ctrl+f")
        time.sleep(0.4)
        ui.type_text(contact)
        time.sleep(0.8)
        ui.press_key("Return")
        time.sleep(0.6)
        ui.type_text(message)
        time.sleep(0.2)
        ui.press_key("Return")
        return f"Mensagem enviada para '{contact}' via automação de tela."

    def status(self) -> str:
        if WHATSAPP_BRIDGE_URL:
            return f"Bridge configurada: {WHATSAPP_BRIDGE_URL}"
        focused = self._focus_whatsapp()
        return "WhatsApp aberto e focado." if focused else "WhatsApp não detectado na tela. Use open primeiro."


_wa_instance: Optional[WhatsAppManager] = None


def get_whatsapp() -> WhatsAppManager:
    global _wa_instance
    if _wa_instance is None:
        _wa_instance = WhatsAppManager()
    return _wa_instance
