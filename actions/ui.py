"""
actions/ui.py — Automação de teclado/mouse (X11 + Wayland).
Gratuito: xdotool (X11/XWayland), ydotool + wtype (Wayland), pyautogui fallback.
"""
import os
import subprocess
import shutil
import time


def _session_type() -> str:
    return os.environ.get("XDG_SESSION_TYPE", "x11").lower()


def _is_wayland() -> bool:
    return _session_type() == "wayland"


class UIManager:
    """Gerencia automação de interface multiplataforma."""

    def click_at(self, x: int, y: int) -> dict:
        if _is_wayland() and shutil.which("ydotool"):
            try:
                r = subprocess.run(
                    ["ydotool", "mousemove", "--absolute", str(x), str(y), "click", "0x40"],
                    capture_output=True, timeout=3,
                )
                if r.returncode == 0:
                    return {"success": True, "message": f"Clicado em ({x},{y}) via ydotool"}
            except Exception as e:
                print(f"[UI] ydotool click: {e}")

        if shutil.which("xdotool"):
            r = subprocess.run(
                ["xdotool", "mousemove", str(x), str(y), "click", "1"],
                capture_output=True, timeout=2,
            )
            if r.returncode == 0:
                return {"success": True, "message": f"Clicado em ({x},{y}) via xdotool"}

        try:
            import pyautogui
            pyautogui.click(x, y)
            return {"success": True, "message": f"Clicado em ({x},{y})"}
        except Exception as e:
            hint = "Instale ydotool (Wayland) ou xdotool (X11)."
            return {"success": False, "message": f"{e}. {hint}"}

    def click_text(self, text: str) -> dict:
        from vision.screen import get_vision
        vision = get_vision()
        elem = vision.get_screen_context_for_click(text)
        if elem:
            return self.click_at(elem["x"], elem["y"])
        return {"success": False, "message": f"Elemento '{text}' não encontrado na tela (OCR)."}

    def type_text(self, text: str) -> dict:
        if _is_wayland() and shutil.which("wtype"):
            try:
                r = subprocess.run(["wtype", "--", text], capture_output=True, timeout=8)
                if r.returncode == 0:
                    return {"success": True, "message": f"Digitado via wtype: '{text[:40]}...'"}
            except Exception as e:
                print(f"[UI] wtype: {e}")

        if _is_wayland() and shutil.which("ydotool"):
            try:
                r = subprocess.run(
                    ["ydotool", "type", "--", text],
                    capture_output=True, timeout=8,
                )
                if r.returncode == 0:
                    return {"success": True, "message": f"Digitado via ydotool"}
            except Exception as e:
                print(f"[UI] ydotool type: {e}")

        if shutil.which("xdotool"):
            r = subprocess.run(
                ["xdotool", "type", "--delay", "30", "--", text],
                capture_output=True, timeout=8,
            )
            if r.returncode == 0:
                return {"success": True, "message": f"Digitado: '{text[:40]}...'"}

        try:
            import pyautogui
            pyautogui.typewrite(text, interval=0.03)
            return {"success": True, "message": f"Digitado: '{text[:40]}...'"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def press_key(self, key: str) -> dict:
        key_map = {
            "enter": "Return", "return": "Return",
            "escape": "Escape", "esc": "Escape",
            "tab": "Tab", "space": "space",
            "backspace": "BackSpace", "delete": "Delete",
            "ctrl+c": "ctrl+c", "ctrl+v": "ctrl+v",
            "ctrl+a": "ctrl+a", "ctrl+z": "ctrl+z",
            "ctrl+f": "ctrl+f", "ctrl+shift+f": "ctrl+shift+f",
            "ctrl+shift+a": "ctrl+shift+a", "ctrl+w": "ctrl+w",
            "ctrl+t": "ctrl+t", "ctrl+l": "ctrl+l",
            "ctrl+enter": "ctrl+Return", "alt+tab": "alt+Tab",
            "super": "super", "win": "super",
            "f11": "F11", "up": "Up", "down": "Down",
            "left": "Left", "right": "Right",
        }
        mapped = key_map.get(key.lower().replace(" ", ""), key)

        if _is_wayland() and shutil.which("ydotool"):
            try:
                parts = mapped.replace("+", " ").split()
                if len(parts) == 1:
                    r = subprocess.run(["ydotool", "key", parts[0]], capture_output=True, timeout=2)
                else:
                    combo = ":".join(parts)
                    r = subprocess.run(["ydotool", "key", combo], capture_output=True, timeout=2)
                if r.returncode == 0:
                    return {"success": True, "message": f"Tecla: {mapped}"}
            except Exception:
                pass

        if shutil.which("xdotool"):
            r = subprocess.run(["xdotool", "key", mapped], capture_output=True, timeout=2)
            if r.returncode == 0:
                return {"success": True, "message": f"Tecla: {mapped}"}

        try:
            import pyautogui
            pyautogui.hotkey(*mapped.split("+"))
            return {"success": True, "message": f"Tecla: {mapped}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def scroll(self, direction: str, amount: int = 3) -> dict:
        dir_map = {"up": "4", "cima": "4", "down": "5", "baixo": "5"}
        btn = dir_map.get(direction.lower(), "5")

        if _is_wayland() and shutil.which("ydotool"):
            code = "0xE0" if btn == "4" else "0xE1"
            try:
                for _ in range(amount):
                    subprocess.run(["ydotool", "click", code], capture_output=True, timeout=1)
                    time.sleep(0.08)
                return {"success": True, "message": f"Scroll {direction} x{amount}"}
            except Exception:
                pass

        if shutil.which("xdotool"):
            for _ in range(amount):
                subprocess.run(["xdotool", "click", btn], capture_output=True, timeout=1)
                time.sleep(0.1)
            return {"success": True, "message": f"Scroll {direction} x{amount}"}

        return {"success": False, "message": "Scroll requer xdotool ou ydotool."}
