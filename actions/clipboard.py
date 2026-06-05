#!/usr/bin/env python3
"""
actions/clipboard.py — Área de transferência via wl-clipboard (Wayland) ou xclip (X11).
"""
import re
import shutil
import subprocess
from typing import Optional


class ClipboardManager:
    def __init__(self):
        self._has_wl_paste = bool(shutil.which("wl-paste"))
        self._has_wl_copy = bool(shutil.which("wl-copy"))
        self._has_xclip = bool(shutil.which("xclip"))
        self._has_xsel = bool(shutil.which("xsel"))
        self._history: list[str] = []

        tool = "wl-clipboard" if self._has_wl_paste else ("xclip" if self._has_xclip else "xsel" if self._has_xsel else "nenhuma")
        print(f"[Clipboard] Ferramenta: {tool}")

    def read(self) -> str:
        """Lê conteúdo atual da área de transferência."""
        try:
            if self._has_wl_paste:
                r = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=3)
                if r.returncode == 0:
                    return r.stdout
            if self._has_xclip:
                r = subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                                   capture_output=True, text=True, timeout=3)
                if r.returncode == 0:
                    return r.stdout
            if self._has_xsel:
                r = subprocess.run(["xsel", "--clipboard", "--output"],
                                   capture_output=True, text=True, timeout=3)
                if r.returncode == 0:
                    return r.stdout
        except Exception:
            pass
        return ""

    def write(self, text: str) -> str:
        """Escreve texto na área de transferência."""
        try:
            if self._has_wl_copy:
                r = subprocess.run(["wl-copy"], input=text, text=True, timeout=3)
                if r.returncode == 0:
                    self._history.append(text[:100])
                    return f"📋 Copiado: '{text[:60]}{'...' if len(text) > 60 else ''}'"
            if self._has_xclip:
                r = subprocess.run(["xclip", "-selection", "clipboard"],
                                   input=text, text=True, timeout=3)
                if r.returncode == 0:
                    self._history.append(text[:100])
                    return f"📋 Copiado: '{text[:60]}{'...' if len(text) > 60 else ''}'"
            if self._has_xsel:
                r = subprocess.run(["xsel", "--clipboard", "--input"],
                                   input=text, text=True, timeout=3)
                if r.returncode == 0:
                    self._history.append(text[:100])
                    return f"📋 Copiado."
        except Exception as e:
            return f"Erro ao copiar: {e}"
        return "Nenhuma ferramenta de clipboard disponível (wl-copy/xclip/xsel)."

    def get_current(self) -> str:
        content = self.read()
        if not content:
            return "A área de transferência está vazia."
        preview = content[:200]
        if len(content) > 200:
            preview += f"... ({len(content)} caracteres no total)"
        return f"📋 Área de transferência:\n{preview}"

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower()

        if any(w in tl for w in ["o que está na área de transferência", "o que tem no clipboard",
                                   "leia o clipboard", "ver clipboard", "área de transferência"]):
            return self.get_current()

        m = re.search(r'(?:copia|copie|copiar)\s+(?:o texto\s+)?["\']?(.+?)["\']?\s*$', tl)
        if m:
            return self.write(m.group(1).strip())

        return None


# Singleton
_clipboard_instance: Optional[ClipboardManager] = None

def get_clipboard() -> ClipboardManager:
    global _clipboard_instance
    if _clipboard_instance is None:
        _clipboard_instance = ClipboardManager()
    return _clipboard_instance
