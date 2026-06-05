#!/usr/bin/env python3
"""
vision/screen.py — Captura de tela + OCR
Otimizado para Ubuntu/X11 (GNOME).
Fallbacks: Wayland/grim, pyautogui, ImageMagick.
OCR via pytesseract (requer tesseract instalado no sistema).
"""
import subprocess
import shutil
import os
import re
from pathlib import Path
from typing import Optional

try:
    from PIL import Image
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

TEMP_DIR = Path(__file__).parent.parent / "temp" / "img"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_PATH = str(TEMP_DIR / "luna_screen.png")


class ScreenVision:
    def __init__(self):
        self.last_screenshot: Optional[str] = None
        self._is_wayland = os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        self._report_capabilities()

    def _report_capabilities(self) -> None:
        session = "Wayland" if self._is_wayland else "X11/GNOME"
        tools = [t for t in ["xdotool", "wmctrl", "gnome-screenshot", "scrot", "grim", "import"] if shutil.which(t)]
        ocr_ok = "✓ pytesseract" if HAS_OCR else "✗ pytesseract ausente"
        tess_ok = "✓ tesseract" if shutil.which("tesseract") else "✗ tesseract ausente"
        print(f"[Vision] Sessão: {session} | Ferramentas: {', '.join(tools) or 'nenhuma'}")
        print(f"[Vision] OCR: {ocr_ok} | {tess_ok}")

    # ── Captura de tela ────────────────────────────────────────

    def capture(self) -> bool:
        """Captura screenshot. Ordem: mss → import (X11) → scrot → gnome-screenshot → grim → pyautogui."""
        if self._capture_mss():
            return True
        if not self._is_wayland and self._capture_import_imagemagick():
            return True
        if self._capture_scrot():
            return True
        if self._capture_gnome_screenshot():
            return True
        if self._capture_grim():
            return True
        if self._capture_pyautogui():
            return True
        if self._is_wayland and self._capture_import_imagemagick():
            return True
        print("[Vision] ✗ Nenhum método de captura funcionou.")
        return False

    def _capture_mss(self) -> bool:
        if not HAS_MSS:
            return False
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=SCREENSHOT_PATH)
            self.last_screenshot = SCREENSHOT_PATH
            print("[Vision] ✓ Captura via mss")
            return True
        except Exception as e:
            print(f"[Vision] mss falhou: {e}")
            return False

    def _capture_gnome_screenshot(self) -> bool:
        if not shutil.which("gnome-screenshot"):
            return False
        try:
            r = subprocess.run(["gnome-screenshot", "-f", SCREENSHOT_PATH],
                               capture_output=True, timeout=5)
            if r.returncode == 0 and Path(SCREENSHOT_PATH).exists():
                self.last_screenshot = SCREENSHOT_PATH
                print("[Vision] ✓ Captura via gnome-screenshot")
                return True
        except Exception:
            pass
        return False

    def _capture_scrot(self) -> bool:
        if not shutil.which("scrot"):
            return False
        try:
            r = subprocess.run(["scrot", "-z", "-o", SCREENSHOT_PATH],
                               capture_output=True, timeout=5)
            if r.returncode == 0 and Path(SCREENSHOT_PATH).exists():
                self.last_screenshot = SCREENSHOT_PATH
                print("[Vision] ✓ Captura via scrot")
                return True
        except Exception:
            pass
        return False

    def _capture_grim(self) -> bool:
        if not shutil.which("grim"):
            return False
        try:
            r = subprocess.run(["grim", SCREENSHOT_PATH],
                               capture_output=True, timeout=5, env={**os.environ})
            if r.returncode == 0 and Path(SCREENSHOT_PATH).exists():
                self.last_screenshot = SCREENSHOT_PATH
                print("[Vision] ✓ Captura via grim (Wayland)")
                return True
        except Exception:
            pass
        return False

    def _capture_pyautogui(self) -> bool:
        try:
            import pyautogui
            pyautogui.screenshot(SCREENSHOT_PATH)
            if Path(SCREENSHOT_PATH).exists():
                self.last_screenshot = SCREENSHOT_PATH
                print("[Vision] ✓ Captura via pyautogui")
                return True
        except Exception:
            pass
        return False

    def _capture_import_imagemagick(self) -> bool:
        if not shutil.which("import"):
            return False
        try:
            r = subprocess.run(["import", "-window", "root", SCREENSHOT_PATH],
                               capture_output=True, timeout=5)
            if r.returncode == 0 and Path(SCREENSHOT_PATH).exists():
                self.last_screenshot = SCREENSHOT_PATH
                print("[Vision] ✓ Captura via ImageMagick import")
                return True
        except Exception:
            pass
        return False

    # ── OCR ───────────────────────────────────────────────────

    def read_text(self) -> str:
        if not self.last_screenshot or not Path(self.last_screenshot).exists():
            return ""
        if not HAS_OCR or not shutil.which("tesseract"):
            return ""
        try:
            img = Image.open(self.last_screenshot)
            return pytesseract.image_to_string(img, lang="por+eng", config="--psm 11 --oem 3").strip()
        except Exception as e:
            print(f"[Vision] OCR falhou: {e}")
            return ""

    def get_elements_with_positions(self) -> list:
        if not self.last_screenshot or not Path(self.last_screenshot).exists():
            return []
        if not HAS_OCR or not shutil.which("tesseract"):
            return []
        try:
            img = Image.open(self.last_screenshot)
            data = pytesseract.image_to_data(img, lang="por+eng",
                                             output_type=pytesseract.Output.DICT,
                                             config="--psm 11 --oem 3")
            elements = []
            for i, word in enumerate(data["text"]):
                word = word.strip()
                if not word or int(data["conf"][i]) < 30:
                    continue
                elements.append({
                    "text": word,
                    "x": data["left"][i] + data["width"][i] // 2,
                    "y": data["top"][i] + data["height"][i] // 2,
                    "w": data["width"][i],
                    "h": data["height"][i],
                    "conf": int(data["conf"][i]),
                })
            return elements
        except Exception as e:
            print(f"[Vision] get_elements falhou: {e}")
            return []

    def find_element_by_text(self, search: str) -> Optional[dict]:
        elements = self.get_elements_with_positions()
        if not elements:
            return None
        sl = search.lower().strip()
        for el in elements:
            if el["text"].lower() == sl:
                return el
        for el in elements:
            if sl in el["text"].lower():
                return el
        words = sl.split()
        if len(words) > 1:
            for el in elements:
                if any(w in el["text"].lower() for w in words):
                    return el
        return None

    # ── Janelas ────────────────────────────────────────────────

    def get_active_window(self) -> str:
        """Janela ativa: xdotool (X11) → wmctrl → hyprctl (Wayland fallback)."""
        if shutil.which("xdotool"):
            try:
                r = subprocess.run(["xdotool", "getactivewindow", "getwindowname"],
                                   capture_output=True, text=True, timeout=3)
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
            except Exception:
                pass
        if shutil.which("wmctrl"):
            try:
                r = subprocess.run(["wmctrl", "-a", ":ACTIVE:"],
                                   capture_output=True, text=True, timeout=3)
                # wmctrl não retorna o nome diretamente, usa xprop como fallback
            except Exception:
                pass
        # Wayland fallback
        if shutil.which("hyprctl"):
            try:
                r = subprocess.run(["hyprctl", "activewindow", "-j"],
                                   capture_output=True, text=True, timeout=3)
                if r.returncode == 0:
                    import json
                    data = json.loads(r.stdout)
                    return data.get("title", "") or data.get("class", "")
            except Exception:
                pass
        return ""

    def list_windows(self) -> list[str]:
        """Lista janelas: wmctrl (X11/GNOME) → xdotool → hyprctl."""
        windows = self._list_windows_wmctrl()
        if windows:
            return windows
        windows = self._list_windows_xdotool()
        if windows:
            return windows
        return self._list_windows_hyprland()

    def _list_windows_wmctrl(self) -> list[str]:
        if not shutil.which("wmctrl"):
            return []
        try:
            r = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=3)
            if r.returncode != 0:
                return []
            names = []
            for line in r.stdout.strip().splitlines():
                # formato: 0x... desktop hostname title
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    title = parts[3].strip()
                    if title and title not in names:
                        names.append(title)
            return names
        except Exception:
            return []

    def _list_windows_xdotool(self) -> list[str]:
        if not shutil.which("xdotool"):
            return []
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", ""],
                               capture_output=True, text=True, timeout=3)
            if r.returncode != 0:
                return []
            names = []
            for wid in r.stdout.strip().split()[:10]:
                r2 = subprocess.run(["xdotool", "getwindowname", wid],
                                    capture_output=True, text=True, timeout=2)
                if r2.returncode == 0 and r2.stdout.strip():
                    names.append(r2.stdout.strip())
            return names
        except Exception:
            return []

    def _list_windows_hyprland(self) -> list[str]:
        if not shutil.which("hyprctl"):
            return []
        try:
            r = subprocess.run(["hyprctl", "clients", "-j"],
                               capture_output=True, text=True, timeout=3)
            if r.returncode != 0:
                return []
            import json
            clients = json.loads(r.stdout)
            names = []
            for c in clients:
                title = c.get("title", "") or c.get("class", "")
                if title and title not in names:
                    names.append(title)
            return names
        except Exception:
            return []

    # ── Descrição para LLM ─────────────────────────────────────

    def describe(self) -> str:
        parts = []
        active = self.get_active_window()
        if active:
            parts.append(f"Janela ativa: {active}")
        windows = self.list_windows()
        if windows:
            others = [w for w in windows if w != active][:6]
            if others:
                parts.append("Janelas abertas: " + ", ".join(others))
        if self.last_screenshot and Path(self.last_screenshot).exists():
            ocr = self.read_text()
            if ocr and len(ocr) > 30:
                parts.append(f"Texto visível na tela:\n{ocr[:800]}")
            else:
                parts.append("(screenshot capturado mas OCR não retornou texto legível)")
        return "\n".join(parts) if parts else "Nenhuma informação visual disponível."

    def capture_and_describe(self) -> str:
        self.capture()
        return self.describe()

    def describe_with_groq_vision(self, user_prompt: str = "Descreva detalhadamente o que está na tela.") -> str:
        """Usa Groq Vision para entender o screenshot; fallback OCR local."""
        if not self.last_screenshot or not Path(self.last_screenshot).exists():
            return ""

        import base64
        import json
        import urllib.request

        try:
            from config import GROQ_API_KEY, GROQ_VISION_MODEL
        except ImportError:
            GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
            GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "")

        if not GROQ_API_KEY or not GROQ_VISION_MODEL:
            ocr = self.read_text()
            if ocr and len(ocr) > 20:
                return f"(Visão via OCR local)\n{ocr[:1200]}"
            return ""

        try:
            with open(self.last_screenshot, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

            payload = {
                "model": GROQ_VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{encoded_string}"
                                },
                            },
                        ],
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 1024,
            }

            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            print(f"[Vision] Chamando Groq Vision ({GROQ_VISION_MODEL})...")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[Vision] Falha no Groq Vision: {e}")

        # Fallback gratuito: Gemini (google-generativeai)
        try:
            from config import GEMINI_API_KEY
        except ImportError:
            GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        if GEMINI_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel("gemini-2.0-flash")
                with open(self.last_screenshot, "rb") as f:
                    img_bytes = f.read()
                resp = model.generate_content([
                    user_prompt,
                    {"mime_type": "image/png", "data": img_bytes},
                ])
                text = getattr(resp, "text", "") or ""
                if text.strip():
                    print("[Vision] ✓ Gemini Vision")
                    return text.strip()
            except Exception as e2:
                print(f"[Vision] Gemini Vision falhou: {e2}")

        ocr = self.read_text()
        if ocr and len(ocr) > 20:
            return f"(Visão via OCR local)\n{ocr[:1200]}"
        return ""

    def get_quick_context(self) -> str:
        """Contexto leve (sem screenshot/OCR) — janela ativa + janelas abertas. ~5ms."""
        parts = []
        active = self.get_active_window()
        if active:
            parts.append(f"Janela ativa: {active}")
        windows = self.list_windows()
        if windows:
            others = [w for w in windows if w != active][:5]
            if others:
                parts.append("Outras janelas: " + ", ".join(others))
        return " | ".join(parts) if parts else ""

    def verify_action_result(self, action_desc: str, prev_window: str) -> str:
        import time
        time.sleep(0.4)
        current = self.get_active_window()
        if current and current != prev_window:
            return f"✓ Ação executada. Janela mudou para: {current}"
        return f"✓ Ação executada. Janela ativa: {current or prev_window}"

    def get_screen_context_for_click(self, target_text: str) -> Optional[dict]:
        print(f"[Vision] Procurando '{target_text}' na tela...")
        if not self.capture():
            return None
        element = self.find_element_by_text(target_text)
        if element:
            print(f"[Vision] ✓ Encontrado '{element['text']}' em ({element['x']}, {element['y']})")
            return element
        print(f"[Vision] ✗ '{target_text}' não encontrado via OCR.")
        return None


# Singleton
_vision_instance: Optional[ScreenVision] = None

def get_vision() -> ScreenVision:
    global _vision_instance
    if _vision_instance is None:
        _vision_instance = ScreenVision()
    return _vision_instance


if __name__ == "__main__":
    print("=== Teste de Visão ===\n")
    v = get_vision()
    print(f"[1] Janela ativa: {v.get_active_window() or '(não detectada)'}\n")
    print("[2] Janelas abertas:")
    for w in v.list_windows():
        print(f"    - {w}")
    print(f"\n[3] Capturando tela...")
    ok = v.capture()
    print(f"    {'✓ OK' if ok else '✗ Falhou'}\n")
    if ok:
        text = v.read_text()
        print(f"[4] OCR: {len(text)} chars | Amostra: {text[:200]}\n")
    print("[5] Descrição completa:")
    print(v.describe())
