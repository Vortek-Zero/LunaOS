#!/usr/bin/env python3
"""
actions/math_board.py — Luna Math
Lousa digital matemática: avalia expressões e pede ajuda à Luna.
"""
import re
import json
from typing import Optional

try:
    from brain.llm import get_llm, MODELS
except ImportError:
    from brain.llm import get_llm, MODELS


class MathBoard:
    """Avalia expressões matemáticas e explica via LLM."""

    _SAFE_NAMES = {
        "abs": abs, "round": round, "min": min, "max": max,
        "sum": sum, "pow": pow,
    }

    def __init__(self):
        self._llm = get_llm()
        self.history: list[dict] = []  # [{expr, result, explanation}]

    def evaluate(self, expression: str) -> tuple[str, bool]:
        """
        Avalia expressão matemática de forma segura.
        Retorna (resultado_str, sucesso).
        """
        # Normaliza: vírgula → ponto, × → *, ÷ → /
        expr = expression.replace(",", ".").replace("×", "*").replace("÷", "/").replace("^", "**")
        # Remove caracteres não permitidos
        if re.search(r"[a-zA-Z_]", expr.replace("abs", "").replace("round", "")
                     .replace("min", "").replace("max", "").replace("sum", "").replace("pow", "")):
            return "Expressão inválida", False
        try:
            result = eval(expr, {"__builtins__": {}}, self._SAFE_NAMES)  # noqa: S307
            result_str = f"{result:g}" if isinstance(result, float) else str(result)
            self.history.append({"expr": expression, "result": result_str})
            return result_str, True
        except ZeroDivisionError:
            return "Divisão por zero", False
        except Exception as e:
            return f"Erro: {e}", False

    def explain(self, expression: str, result: str) -> str:
        """Pede à Luna para explicar o cálculo passo a passo."""
        prompt = (
            "Explique o cálculo matemático abaixo passo a passo em português, "
            "de forma clara e didática. Seja conciso.\n\n"
            f"Expressão: {expression}\nResultado: {result}\n\nExplicação:"
        )
        raw = self._llm.generate(prompt, task_type="factual", model=MODELS.get("main"))
        try:
            data = json.loads(raw)
            return data.get("response", data.get("explanation", raw))
        except Exception:
            return raw

    def ask(self, question: str) -> str:
        """Pergunta matemática em linguagem natural."""
        ctx = ""
        if self.history:
            last = self.history[-1]
            ctx = f"Último cálculo: {last['expr']} = {last['result']}\n"
        prompt = (
            "Você é um professor de matemática. Responda a pergunta abaixo "
            "de forma clara e didática em português.\n\n"
            f"{ctx}Pergunta: {question}\n\nResposta:"
        )
        raw = self._llm.generate(prompt, task_type="factual", model=MODELS.get("main"))
        try:
            data = json.loads(raw)
            return data.get("response", data.get("answer", raw))
        except Exception:
            return raw

    def clear(self):
        self.history.clear()


_board: Optional[MathBoard] = None


def get_math_board() -> MathBoard:
    global _board
    if _board is None:
        _board = MathBoard()
    return _board
