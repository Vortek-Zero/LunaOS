#!/usr/bin/env python3
"""
orchestrator.py — PC A: Interface leve da Luna
Coleta input (texto/voz), envia ao Worker via HTTP, exibe resposta.
Não carrega luna_core, modelos Qwen ou automações.

Iniciar: python orchestrator.py
"""
import sys
import json
import threading
from pathlib import Path

import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QComboBox, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont

# ══════════════════════════════════════════════════════════════
#  DEVICE MANAGER
# ══════════════════════════════════════════════════════════════

class DeviceManager:
    """
    Gerencia dispositivos Worker registrados.
    Carrega de devices.json; permite trocar o worker ativo em runtime.
    """

    DEVICES_FILE = Path(__file__).parent / "config" / "devices.json"

    def __init__(self):
        self._devices: dict[str, dict] = {}
        self._active_id: str = ""
        self._load()

    def _load(self):
        if self.DEVICES_FILE.exists():
            data = json.loads(self.DEVICES_FILE.read_text())
            for d in data.get("devices", []):
                self._devices[d["id"]] = d
            self._active_id = data.get("active_device", "")
        # Fallback via config.py
        if not self._devices:
            try:
                import config
                self._devices["default"] = {
                    "id": "default",
                    "name": "Worker (config.py)",
                    "ip_address": config.WORKER_URL.split("//")[-1].split(":")[0],
                    "port": int(config.WORKER_URL.split(":")[-1]),
                    "api_key": config.WORKER_API_KEY,
                }
                self._active_id = "default"
            except Exception:
                pass

    def register(self, device: dict):
        self._devices[device["id"]] = device

    def set_active(self, device_id: str):
        if device_id in self._devices:
            self._active_id = device_id

    @property
    def active(self) -> dict | None:
        return self._devices.get(self._active_id)

    @property
    def device_names(self) -> list[str]:
        return [f"{d['id']} — {d['name']}" for d in self._devices.values()]

    def base_url(self) -> str:
        d = self.active
        if not d:
            return ""
        return f"http://{d['ip_address']}:{d['port']}"

    def api_key(self) -> str:
        d = self.active
        return d["api_key"] if d else ""


# ══════════════════════════════════════════════════════════════
#  STATUS BRIDGE — emite sinais na main thread (thread-safe)
# ══════════════════════════════════════════════════════════════

class StatusBridge(QObject):
    """Ponte thread-safe para atualizar o status_label na main thread."""
    status_changed = pyqtSignal(str, str)  # (texto, cor_css)


# ══════════════════════════════════════════════════════════════
#  RELAY WORKER (QThread — não bloqueia a UI)
# ══════════════════════════════════════════════════════════════

class RelayWorker(QThread):
    """Envia mensagem ao Worker HTTP e devolve a resposta via signal."""
    result_signal = pyqtSignal(str)
    error_signal  = pyqtSignal(str)

    def __init__(self, device_manager: DeviceManager, message: str):
        super().__init__()
        self._dm = device_manager
        self._message = message

    def run(self):
        url = f"{self._dm.base_url()}/chat"
        headers = {"X-API-KEY": self._dm.api_key(), "Content-Type": "application/json"}
        try:
            resp = requests.post(url, json={"message": self._message}, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            self.result_signal.emit(data.get("response", "(sem resposta)"))
        except requests.exceptions.ConnectionError:
            self.error_signal.emit(f"[ERRO] Worker inacessível em {self._dm.base_url()}")
        except requests.exceptions.Timeout:
            self.error_signal.emit("[ERRO] Timeout — Worker demorou demais para responder.")
        except Exception as e:
            self.error_signal.emit(f"[ERRO] {e}")


# ══════════════════════════════════════════════════════════════
#  JANELA PRINCIPAL
# ══════════════════════════════════════════════════════════════

class OrchestratorWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.dm = DeviceManager()
        self._relay: RelayWorker | None = None

        # Bridge para atualizar status_label de qualquer thread com segurança
        self._status_bridge = StatusBridge()
        self._status_bridge.status_changed.connect(self._apply_status)

        self._build_ui()
        self._check_worker_health()

        # Reconexão automática a cada 30 segundos
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(30_000)
        self._reconnect_timer.timeout.connect(self._check_worker_health)
        self._reconnect_timer.start()

    # ── UI ────────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("Luna — Orquestrador (PC A)")
        self.setMinimumSize(640, 480)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Barra de dispositivos ──────────────────────────────
        dev_bar = QHBoxLayout()
        dev_bar.addWidget(QLabel("Worker:"))
        self.device_combo = QComboBox()
        self.device_combo.addItems(self.dm.device_names)
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        dev_bar.addWidget(self.device_combo, 1)
        self.status_label = QLabel("●  verificando...")
        self.status_label.setStyleSheet("color: gray;")
        dev_bar.addWidget(self.status_label)
        layout.addLayout(dev_bar)

        # ── Chat ──────────────────────────────────────────────
        self.chat_area = QTextEdit()
        self.chat_area.setReadOnly(True)
        self.chat_area.setFont(QFont("Courier New", 10))
        self.chat_area.setStyleSheet(
            "background:#0d0d1a; color:#c8c8e8; border:1px solid #333;"
        )
        layout.addWidget(self.chat_area, 1)

        # ── Input ─────────────────────────────────────────────
        input_bar = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Digite sua mensagem...")
        self.input_field.returnPressed.connect(self._send)
        input_bar.addWidget(self.input_field, 1)
        self.send_btn = QPushButton("Enviar")
        self.send_btn.clicked.connect(self._send)
        input_bar.addWidget(self.send_btn)
        layout.addLayout(input_bar)

    # ── Lógica ────────────────────────────────────────────────

    def _on_device_changed(self, idx: int):
        device_id = list(self.dm._devices.keys())[idx]
        self.dm.set_active(device_id)
        self._check_worker_health()

    def _check_worker_health(self):
        """Verifica saúde do worker em thread de background (thread-safe via signal)."""
        def _ping():
            try:
                url = f"{self.dm.base_url()}/health"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    self._status_bridge.status_changed.emit("●  online", "color: #00cc66;")
                else:
                    self._status_bridge.status_changed.emit("●  offline", "color: #cc3333;")
            except Exception:
                self._status_bridge.status_changed.emit("●  offline", "color: #cc3333;")

        threading.Thread(target=_ping, daemon=True).start()

    def _apply_status(self, text: str, style: str):
        """Atualiza status_label na main thread (chamado via signal)."""
        self.status_label.setText(text)
        self.status_label.setStyleSheet(style)

    def _set_offline(self):
        self._status_bridge.status_changed.emit("●  offline", "color: #cc3333;")

    def _send(self):
        text = self.input_field.text().strip()
        if not text or self._relay and self._relay.isRunning():
            return

        self.input_field.clear()
        self._append_chat("Você", text)
        self.send_btn.setEnabled(False)
        self._status_bridge.status_changed.emit("●  processando...", "color: #ccaa00;")

        self._relay = RelayWorker(self.dm, text)
        self._relay.result_signal.connect(self._on_response)
        self._relay.error_signal.connect(self._on_error)
        self._relay.start()

    def _on_response(self, text: str):
        self._append_chat("Luna", text)
        self.send_btn.setEnabled(True)
        self._status_bridge.status_changed.emit("●  online", "color: #00cc66;")

    def _on_error(self, msg: str):
        self._append_chat("SYS", msg)
        self.send_btn.setEnabled(True)
        self._set_offline()

    def _append_chat(self, sender: str, text: str):
        color = {"Você": "#7eb8f7", "Luna": "#b8f7a0", "SYS": "#f7a0a0"}.get(sender, "#ffffff")
        self.chat_area.append(
            f'<span style="color:{color};font-weight:bold;">{sender}:</span> '
            f'<span style="color:#d0d0e8;">{text}</span><br>'
        )


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = OrchestratorWindow()
    win.show()
    sys.exit(app.exec())
