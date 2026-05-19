import subprocess
import shutil
import time

class UIManager:
    """Gerencia a automação de interface: teclado, mouse e scroll."""

    def click_at(self, x: int, y: int) -> dict:
        if shutil.which("xdotool"):
            r = subprocess.run(
                ["xdotool", "mousemove", str(x), str(y), "click", "1"],
                capture_output=True, timeout=2
            )
            return {"success": r.returncode == 0, "message": f"Clicado em ({x},{y})"}
        try:
            import pyautogui
            pyautogui.click(x, y)
            return {"success": True, "message": f"Clicado em ({x},{y})"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def click_text(self, text: str) -> dict:
        from vision.screen import get_vision
        vision = get_vision()
        elem = vision.get_screen_context_for_click(text)
        if elem:
            return self.click_at(elem["x"], elem["y"])
        return {"success": False, "message": f"Elemento '{text}' não encontrado na tela."}

    def type_text(self, text: str) -> dict:
        if shutil.which("xdotool"):
            r = subprocess.run(
                ["xdotool", "type", "--delay", "30", "--", text],
                capture_output=True, timeout=5
            )
            return {"success": r.returncode == 0, "message": f"Digitado: '{text}'"}
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=0.03)
            return {"success": True, "message": f"Digitado: '{text}'"}
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
        }
        mapped = key_map.get(key.lower(), key)
        if shutil.which("xdotool"):
            r = subprocess.run(
                ["xdotool", "key", mapped],
                capture_output=True, timeout=2
            )
            return {"success": r.returncode == 0, "message": f"Tecla: {mapped}"}
        try:
            import pyautogui
            pyautogui.hotkey(*mapped.split("+"))
            return {"success": True, "message": f"Tecla: {mapped}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def scroll(self, direction: str, amount: int = 3) -> dict:
        dir_map = {"up": "4", "cima": "4", "down": "5", "baixo": "5"}
        btn = dir_map.get(direction.lower(), "5")
        if shutil.which("xdotool"):
            for _ in range(amount):
                subprocess.run(["xdotool", "click", btn], capture_output=True, timeout=1)
                time.sleep(0.1)
            return {"success": True, "message": f"Scroll {direction} x{amount}"}
        return {"success": False, "message": "xdotool não disponível"}
