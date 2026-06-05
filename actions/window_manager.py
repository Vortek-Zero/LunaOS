#!/usr/bin/env python3
"""
actions/window_manager.py — Controle avançado de janelas via hyprctl + xdotool.
"""
import re
import shutil
import subprocess
from typing import Optional


def _run(cmd: list[str], timeout: int = 3) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except Exception as e:
        return 1, str(e)


class WindowManager:
    def __init__(self):
        self._has_hyprctl = bool(shutil.which("hyprctl"))
        self._has_xdotool = bool(shutil.which("xdotool"))
        tools = []
        if self._has_hyprctl:
            tools.append("hyprctl")
        if self._has_xdotool:
            tools.append("xdotool")
        print(f"[WindowManager] Ferramentas: {', '.join(tools) or 'nenhuma'}")

    def _hypr(self, *args) -> tuple[bool, str]:
        if not self._has_hyprctl:
            return False, "hyprctl não disponível."
        code, out = _run(["hyprctl"] + list(args))
        return code == 0, out

    def _dispatch(self, action: str, *args) -> str:
        cmd = ["hyprctl", "dispatch", action] + list(args)
        code, out = _run(cmd)
        return out if code == 0 else f"Erro: {out}"

    # ── Janela ativa ───────────────────────────────────────────

    def close_active(self) -> str:
        if self._has_hyprctl:
            self._dispatch("killactive")
            return "✕ Janela fechada."
        if self._has_xdotool:
            code, wid = _run(["xdotool", "getactivewindow"])
            if code == 0:
                _run(["xdotool", "windowclose", wid])
                return "✕ Janela fechada."
        return "Não foi possível fechar a janela."

    def minimize_active(self) -> str:
        if self._has_hyprctl:
            self._dispatch("movetoworkspacesilent", "special")
            return "Janela minimizada."
        if self._has_xdotool:
            code, wid = _run(["xdotool", "getactivewindow"])
            if code == 0:
                _run(["xdotool", "windowminimize", wid])
                return "Janela minimizada."
        return "Não foi possível minimizar."

    def maximize_active(self) -> str:
        if self._has_hyprctl:
            self._dispatch("fullscreen", "1")
            return "Janela maximizada."
        if self._has_xdotool:
            code, wid = _run(["xdotool", "getactivewindow"])
            if code == 0:
                _run(["xdotool", "windowmaximize", wid])
                return "Janela maximizada."
        return "Não foi possível maximizar."

    def fullscreen(self) -> str:
        if self._has_hyprctl:
            self._dispatch("fullscreen", "0")
            return "Tela cheia ativada."
        return "hyprctl não disponível."

    def toggle_float(self) -> str:
        if self._has_hyprctl:
            self._dispatch("togglefloating")
            return "Modo flutuante alternado."
        return "hyprctl não disponível."

    # ── Workspaces ─────────────────────────────────────────────

    def go_to_workspace(self, num: int) -> str:
        if self._has_hyprctl:
            self._dispatch("workspace", str(num))
            return f"Workspace {num} ativado."
        return "hyprctl não disponível."

    def move_to_workspace(self, num: int) -> str:
        if self._has_hyprctl:
            self._dispatch("movetoworkspace", str(num))
            return f"Janela movida para workspace {num}."
        return "hyprctl não disponível."

    # ── Tile / Move ────────────────────────────────────────────

    def tile_left(self) -> str:
        if self._has_hyprctl:
            self._dispatch("movefocus", "l")
            return "Foco movido para esquerda."
        return "hyprctl não disponível."

    def tile_right(self) -> str:
        if self._has_hyprctl:
            self._dispatch("movefocus", "r")
            return "Foco movido para direita."
        return "hyprctl não disponível."

    def swap_left(self) -> str:
        if self._has_hyprctl:
            self._dispatch("swapwindow", "l")
            return "Janela movida para esquerda."
        return "hyprctl não disponível."

    def swap_right(self) -> str:
        if self._has_hyprctl:
            self._dispatch("swapwindow", "r")
            return "Janela movida para direita."
        return "hyprctl não disponível."

    def list_windows(self) -> str:
        from vision.screen import get_vision
        wins = get_vision().list_windows()
        if not wins:
            return "Nenhuma janela visível detectada."
        lines = ["Janelas abertas:"]
        for i, w in enumerate(wins[:25], 1):
            lines.append(f"  {i}. {w}")
        return "\n".join(lines)

    def focus_window(self, title: str) -> str:
        if not title:
            return "FALHOU: informe o título da janela."
        if shutil.which("wmctrl"):
            code, _ = _run(["wmctrl", "-a", title])
            if code == 0:
                return f"Janela focada: {title}"
        if shutil.which("xdotool"):
            code, _ = _run(["xdotool", "search", "--name", title, "windowactivate"])
            if code == 0:
                return f"Janela focada: {title}"
        if self._has_hyprctl:
            ok, clients = self._hypr("clients", "-j")
            if ok:
                import json
                try:
                    for c in json.loads(clients):
                        if title.lower() in c.get("title", "").lower():
                            addr = c.get("address", "")
                            self._dispatch("focuswindow", f"address:{addr}")
                            return f"Janela focada: {c.get('title')}"
                except Exception:
                    pass
        return f"FALHOU: janela '{title}' não encontrada."

    # ── Interface natural ──────────────────────────────────────

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower()

        # Workspace
        m = re.search(r'workspace\s+(\d+)|(?:vai para|ir para|muda para)\s+(?:o\s+)?workspace\s+(\d+)', tl)
        if m:
            num = int(m.group(1) or m.group(2))
            return self.go_to_workspace(num)

        m = re.search(r'move\s+(?:a\s+janela\s+)?para\s+(?:o\s+)?workspace\s+(\d+)', tl)
        if m:
            return self.move_to_workspace(int(m.group(1)))

        if any(w in tl for w in ["fecha essa janela", "fecha a janela", "fechar janela", "fecha janela"]):
            return self.close_active()
        if any(w in tl for w in ["minimiza", "minimize", "minimizar"]):
            return self.minimize_active()
        if any(w in tl for w in ["maximiza", "maximize", "maximizar"]):
            return self.maximize_active()
        if any(w in tl for w in ["tela cheia", "fullscreen"]):
            return self.fullscreen()
        if any(w in tl for w in ["flutuante", "floating", "toggle float"]):
            return self.toggle_float()
        if any(w in tl for w in ["move para esquerda", "janela para esquerda"]):
            return self.swap_left()
        if any(w in tl for w in ["move para direita", "janela para direita"]):
            return self.swap_right()

        return None


# Singleton
_wm_instance: Optional[WindowManager] = None

def get_window_manager() -> WindowManager:
    global _wm_instance
    if _wm_instance is None:
        _wm_instance = WindowManager()
    return _wm_instance
