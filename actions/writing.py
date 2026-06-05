#!/usr/bin/env python3
"""
actions/writing.py — Luna Writing
Editor de texto com sugestões em tempo real via LLM.
"""
import threading
from typing import Callable, Optional

try:
    from brain.llm import get_llm, MODELS
except ImportError:
    from brain.llm import get_llm, MODELS


class WritingEngine:
    """Gerencia sugestões de escrita em tempo real."""

    def __init__(self):
        self._llm = get_llm()
        self._suggestion_thread: Optional[threading.Thread] = None
        self._cancel_flag = threading.Event()
        self.last_suggestion = ""

    def get_suggestion(
        self,
        text: str,
        on_token: Callable[[str], None],
        on_done: Callable[[str], None],
    ) -> None:
        """Gera sugestão de continuação/melhoria em streaming (não-bloqueante)."""
        self._cancel_flag.set()
        if self._suggestion_thread and self._suggestion_thread.is_alive():
            self._suggestion_thread.join(timeout=0.5)
        self._cancel_flag.clear()

        def _run():
            prompt = (
                "Você é um assistente de escrita criativa em português. "
                "Continue ou melhore o texto abaixo de forma natural e fluida. "
                "Responda APENAS com a continuação/melhoria, sem explicações.\n\n"
                f"Texto: {text}\n\nContinuação:"
            )
            full = ""
            try:
                for token in self._llm.generate(
                    prompt,
                    task_type="creative",
                    model=MODELS.get("fast"),
                    stream=True,
                ):
                    if self._cancel_flag.is_set():
                        return
                    full += token
                    on_token(token)
                self.last_suggestion = full
                on_done(full)
            except Exception as e:
                on_done(f"[erro: {e}]")

        self._suggestion_thread = threading.Thread(target=_run, daemon=True)
        self._suggestion_thread.start()

    def fix_text(self, text: str) -> str:
        """Corrige gramática e estilo do texto selecionado."""
        prompt = (
            "Corrija gramática, pontuação e estilo do texto abaixo em português. "
            "Responda APENAS com o texto corrigido, sem explicações.\n\n"
            f"Texto: {text}\n\nCorrigido:"
        )
        result = self._llm.generate(prompt, task_type="factual", model=MODELS.get("main"))
        # Remove JSON wrapper se vier
        import json
        try:
            data = json.loads(result)
            return data.get("response", data.get("text", result))
        except Exception:
            return result

    def summarize(self, text: str) -> str:
        """Resume o texto."""
        prompt = (
            "Resuma o texto abaixo em 2-3 frases em português.\n\n"
            f"Texto: {text}\n\nResumo:"
        )
        result = self._llm.generate(prompt, task_type="factual", model=MODELS.get("main"))
        import json
        try:
            data = json.loads(result)
            return data.get("response", data.get("text", result))
        except Exception:
            return result

    def cancel(self):
        self._cancel_flag.set()


_engine: Optional[WritingEngine] = None


def get_writing_engine() -> WritingEngine:
    global _engine
    if _engine is None:
        _engine = WritingEngine()
    return _engine
