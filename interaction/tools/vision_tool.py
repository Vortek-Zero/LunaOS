#!/usr/bin/env python3
"""
vision_tool.py — Computer Use: visão computacional + controle de GUI.
Prioridade: 30 (último recurso para tarefas de navegador, primário para desktop).

Fluxo:
  1. Screenshot da tela
  2. LLM com visão analisa a tela (Groq, Gemini, Puter)
  3. LLM retorna coordenadas/ações
  4. pyautogui executa cliques/teclas
  5. Verificador confirma se tela mudou
"""

import json
import time
from pathlib import Path

from interaction.tools.base_tool import BaseTool, ToolResult

TEMP_DIR = Path(__file__).parent.parent.parent / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


class VisionTool(BaseTool):
    name = "vision"
    description = "Computer Use — vê a tela, decide onde clicar, executa ações via pyautogui"
    category = "browser"
    priority = 30

    def __init__(self):
        self._vision = None
        self._last_screenshot = None

    def _get_vision(self):
        if self._vision is None:
            try:
                from vision.screen import get_vision

                self._vision = get_vision()
            except Exception:
                return None
        return self._vision

    def available(self) -> bool:
        try:
            import pyautogui

            pyautogui.size()
            return True
        except Exception:
            return False

    def execute(self, task: dict) -> ToolResult:
        goal = task.get("goal", "")
        action = task.get("action", "analyze")
        x = task.get("x")
        y = task.get("y")
        text = task.get("text", "")
        button = task.get("button", "left")
        key = task.get("key", "")
        target_text = task.get("target_text", "")

        if action == "screenshot":
            return self._do_screenshot()

        if action == "analyze" or (not action and goal):
            return self._analyze_and_act(goal)

        if action == "click":
            return self._do_click(x, y, button)

        if action == "click_text":
            return self._click_text(target_text or text)

        if action == "type":
            return self._do_type(text)

        if action == "press":
            return self._do_press(key)

        if action in ("scroll_down", "scroll_up"):
            return self._do_scroll(action)

        if action == "get_active_window":
            return self._get_active_window()

        return ToolResult(status="error", error=f"Ação desconhecida: {action}")

    def _do_screenshot(self) -> ToolResult:
        vision = self._get_vision()
        if not vision:
            return ToolResult(status="error", error="ScreenVision não disponível")

        ok = vision.capture()
        if not ok:
            return ToolResult(status="error", error="Falha ao capturar tela")

        self._last_screenshot = vision.last_screenshot
        ocr = vision.read_text()
        window = vision.get_active_window()

        return ToolResult(
            status="success",
            data={
                "screenshot": vision.last_screenshot,
                "ocr": ocr[:2000] if ocr else "",
                "active_window": window,
            },
            signals={"screenshot_taken": True},
        )

    def _analyze_and_act(self, goal: str) -> ToolResult:
        vision = self._get_vision()
        if not vision:
            return ToolResult(status="error", error="ScreenVision não disponível")

        ok = vision.capture()
        if not ok:
            return ToolResult(status="error", error="Falha ao capturar tela")

        self._last_screenshot = vision.last_screenshot

        window_before = vision.get_active_window()
        ocr = vision.read_text()

        if not ocr:
            return ToolResult(
                status="error", error="OCR não retornou texto — tela vazia ou ilegível", signals={"ocr_failed": True}
            )

        prompt = f"""Você é um agente de Computer Use. Analise esta captura de tela.

Objetivo do usuário: {goal}

Texto visível na tela:
{ocr[:2000]}

Janela ativa: {window_before}

Com base na tela, decida a PRÓXIMA AÇÃO a ser tomada.
Responda APENAS JSON no formato:
{{"action": "click"|"type"|"press"|"done", "target_text": "...", "text": "...", "key": "...", "rationale": "..."}}

Regras:
- "click" no target_text que corresponde ao objetivo
- "type" para digitar texto em campo
- "press" + "key" para teclas especiais (Enter, Escape, Tab)
- "done" se o objetivo já foi alcançado"""

        try:
            from brain.llm import get_llm

            llm = get_llm()
            raw = llm.generate(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{self._encode_image(vision.last_screenshot)}"
                                },
                            },
                        ],
                    },
                ],
                task_type="creative",
                model="puter/grok-3",
                max_retries=1,
            )
        except Exception:
            raw = None

        if not raw:
            return ToolResult(
                status="error",
                data={"ocr": ocr[:1000], "active_window": window_before},
                error="LLM com visão não disponível",
            )

        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            decision = json.loads(cleaned)
        except Exception:
            decision = {"action": "done", "rationale": raw[:200]}

        act = decision.get("action", "done")

        if act == "click":
            target = decision.get("target_text", "")
            if target:
                click_result = self._click_text(target)
                if click_result.status == "success":
                    time.sleep(0.5)
                    vision.capture()
                    window_after = vision.get_active_window()
                    return ToolResult(
                        status="success",
                        data={
                            "action": "click",
                            "target": target,
                            "window_before": window_before,
                            "window_after": window_after,
                        },
                        signals={"window_changed": window_before != window_after},
                    )

        elif act == "type":
            text_to_type = decision.get("text", "")
            if text_to_type:
                import pyautogui

                pyautogui.write(text_to_type, interval=0.05)
                return ToolResult(
                    status="success",
                    data={"action": "type", "text": text_to_type},
                    signals={"text_typed": True},
                )

        elif act == "press":
            key_to_press = decision.get("key", "enter")
            import pyautogui

            pyautogui.press(key_to_press)
            return ToolResult(
                status="success",
                data={"action": "press", "key": key_to_press},
                signals={"key_pressed": True},
            )

        return ToolResult(
            status="success" if act == "done" else "partial",
            data={"action": act, "rationale": decision.get("rationale", ""), "ocr": ocr[:500]},
            signals={"action_completed": act == "done"},
        )

    def _click_text(self, target_text: str) -> ToolResult:
        vision = self._get_vision()
        if not vision:
            return ToolResult(status="error", error="ScreenVision não disponível")

        if not vision.last_screenshot:
            vision.capture()

        element = vision.find_element_by_text(target_text)
        if not element:
            return ToolResult(
                status="error",
                error=f"'{target_text}' não encontrado na tela",
                signals={"element_not_found": True},
            )

        import pyautogui

        x, y = element["x"], element["y"]
        pyautogui.moveTo(x, y, duration=0.3)
        pyautogui.click()
        return ToolResult(
            status="success",
            data={"clicked": target_text, "x": x, "y": y},
            signals={"element_clicked": True},
        )

    def _do_click(self, x: int, y: int, button: str = "left") -> ToolResult:
        import pyautogui

        pyautogui.moveTo(x, y, duration=0.2)
        pyautogui.click(button=button)
        return ToolResult(
            status="success",
            data={"x": x, "y": y, "button": button},
            signals={"clicked": True},
        )

    def _do_type(self, text: str) -> ToolResult:
        import pyautogui

        pyautogui.write(text, interval=0.05)
        return ToolResult(status="success", data={"typed": text}, signals={"text_typed": True})

    def _do_press(self, key: str) -> ToolResult:
        import pyautogui

        pyautogui.press(key)
        return ToolResult(status="success", data={"key": key}, signals={"key_pressed": True})

    def _do_scroll(self, direction: str) -> ToolResult:
        import pyautogui

        amount = -3 if direction == "scroll_down" else 3
        pyautogui.scroll(amount)
        return ToolResult(status="success", data={"direction": direction}, signals={"scrolled": True})

    def _get_active_window(self) -> ToolResult:
        vision = self._get_vision()
        if not vision:
            return ToolResult(status="error", error="ScreenVision não disponível")
        window = vision.get_active_window()
        return ToolResult(status="success", data={"active_window": window or "desktop"})

    def _encode_image(self, path: str) -> str:
        import base64

        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def verify(self, result: ToolResult) -> bool:
        if result.status == "success":
            return True
        if result.signals.get("window_changed"):
            return True
        if result.signals.get("element_clicked"):
            return True
        if result.signals.get("text_typed"):
            return True
        return bool(result.signals.get("screenshot_taken") and result.data and result.data.get("ocr"))
