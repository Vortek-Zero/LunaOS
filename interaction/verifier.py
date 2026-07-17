#!/usr/bin/env python3
"""
verifier.py — Verificador de sucesso multi-sinal.
Não checa apenas "deu erro". Analisa sinais concretos:
  - Janela foi aberta/mudou?
  - Arquivo foi criado/modificado?
  - Tela mudou (screenshot diferente)?
  - URL mudou?
  - Saída contém resultado esperado?
  - Processo está rodando?
"""

import re
from pathlib import Path

from interaction.tools.base_tool import ToolResult


class Verifier:
    def __init__(self):
        self._previous_state = {}

    def check(self, result: ToolResult, goal: str = "") -> bool:
        if result.status == "success":
            return True

        signals = result.signals or {}

        if signals.get("window_changed"):
            return True

        if signals.get("element_clicked"):
            return True

        if signals.get("url_changed"):
            return True

        if signals.get("page_loaded"):
            return True

        if signals.get("file_created"):
            return True

        if signals.get("search_done"):
            return True

        if signals.get("screenshot_taken"):
            return True

        if signals.get("text_typed"):
            return True

        if signals.get("returncode") == 0:
            return True

        if signals.get("http_ok"):
            return True

        stdout = ""
        if result.data and isinstance(result.data, dict):
            stdout = result.data.get("stdout", "") or ""

        if stdout:
            goal_keywords = self._extract_keywords(goal)
            for kw in goal_keywords:
                if kw.lower() in stdout.lower():
                    return True

        return False

    def check_window_opened(self, window_name: str = None) -> bool:
        try:
            from vision.screen import get_vision

            vision = get_vision()
            current = vision.get_active_window()
            if window_name:
                return window_name.lower() in current.lower()
            return bool(current)
        except Exception:
            return False

    def check_file_created(self, path: str) -> bool:
        return Path(path).exists()

    def check_process_running(self, name: str) -> bool:
        try:
            import subprocess

            result = subprocess.run(
                ["pgrep", "-f", name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def check_screen_changed(self, prev_screenshot: str = None) -> bool:
        try:
            from vision.screen import get_vision

            vision = get_vision()
            now = vision.capture()
            if now and prev_screenshot and Path(prev_screenshot).exists():
                import hashlib

                old_hash = hashlib.md5(Path(prev_screenshot).read_bytes()).hexdigest()
                new_hash = hashlib.md5(Path(vision.last_screenshot).read_bytes()).hexdigest()
                return old_hash != new_hash
            return False
        except Exception:
            return False

    def _extract_keywords(self, goal: str) -> list[str]:
        words = re.findall(r"\b[a-zA-ZÀ-ÿ]{3,}\b", goal)
        stopwords = {
            "para",
            "com",
            "uma",
            "como",
            "mais",
            "dos",
            "das",
            "que",
            "por",
            "pelo",
            "num",
            "numa",
            "sem",
            "sob",
            "era",
            "tem",
            "vai",
            "pode",
            "nos",
            "nas",
            "aos",
            "ela",
            "ele",
            "você",
            "isso",
            "aquele",
            "esta",
            "este",
        }
        return [w for w in words if w.lower() not in stopwords]
