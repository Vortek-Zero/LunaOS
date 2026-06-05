#!/usr/bin/env python3
"""
actions/automation.py — Luna Automation
Placeholder para automação residencial via ESP32.
Em breve: controle de luzes, tomadas, sensores e alertas.
"""
from typing import Optional


class AutomationManager:
    """
    Gerenciador de automação residencial.
    
    TODO (quando o ESP32 estiver integrado):
    - Conectar via MQTT ou HTTP ao ESP32
    - Controlar luzes, tomadas, ar-condicionado
    - Ler sensores de temperatura, umidade, movimento
    - Disparar alertas via Luna
    """

    def __init__(self):
        self.connected = False
        self.devices: dict[str, dict] = {}
        # Placeholder: endereço do ESP32
        self.esp32_host: Optional[str] = None

    def status(self) -> str:
        if not self.connected:
            return (
                "🏠 Luna Automation — Em breve!\n"
                "Quando o ESP32 estiver configurado, você poderá controlar\n"
                "luzes, tomadas e sensores da sua casa por aqui."
            )
        return f"🏠 Conectado ao ESP32 ({self.esp32_host}) | {len(self.devices)} dispositivos"

    def connect(self, host: str) -> bool:
        """Tenta conectar ao ESP32. Placeholder."""
        self.esp32_host = host
        # TODO: implementar conexão real (MQTT/HTTP)
        self.connected = False
        return False

    def toggle_device(self, name: str) -> str:
        """Liga/desliga dispositivo. Placeholder."""
        return f"⚠ Automação ainda não configurada. Dispositivo '{name}' não encontrado."

    def list_devices(self) -> list[str]:
        return list(self.devices.keys())


_manager: Optional[AutomationManager] = None


def get_automation() -> AutomationManager:
    global _manager
    if _manager is None:
        _manager = AutomationManager()
    return _manager
