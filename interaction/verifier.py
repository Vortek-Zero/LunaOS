#!/usr/bin/env python3
"""
verifier.py — Verificador de sucesso multi-sinal.
Não checa apenas "deu erro". Analisa sinais concretos:
  - Janela foi aberta?
  - Arquivo foi criado?
  - Tela mudou?
  - Saída contém resultado esperado?
"""

import re
from pathlib import Path

from interaction.tools.base_tool import ToolResult


class Verifier:
    def __init__(self):
        self._snapshot_before = {}

    def check(self, result: ToolResult, goal: str = "") -> bool:
        if result.status == "success":
            return True

        signals = result.signals or {}

        if signals.get("returncode") == 0:
            return True

        if signals.get("window_opened"):
            return True

        if signals.get("file_created"):
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

    def _extract_keywords(self, goal: str) -> list[str]:
        words = re.findall(r"\b[a-zA-Z]{3,}\b", goal)
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
        }
        return [w for w in words if w.lower() not in stopwords]
