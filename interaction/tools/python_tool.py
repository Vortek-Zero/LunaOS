#!/usr/bin/env python3
"""
python_tool.py — Executa código Python arbitrário.
Prioridade: 80 (preferido para tarefas de dados/script).
"""

import io
import sys
import traceback

from interaction.tools.base_tool import BaseTool, ToolResult


class PythonTool(BaseTool):
    name = "python"
    description = "Executa código Python com suporte a bibliotecas instaladas"
    category = "system"
    priority = 80

    def available(self) -> bool:
        return True

    def execute(self, task: dict) -> ToolResult:
        code = task.get("code") or task.get("goal", "")
        if not code:
            return ToolResult(status="error", error="Nenhum código fornecido")

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        try:
            compiled = compile(code, "<luna_python>", "exec", flags=0)
            local_vars = {"__builtins__": __builtins__}
            exec(compiled, local_vars)
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            stdout = stdout_capture.getvalue()
            stderr = stderr_capture.getvalue()
            result = {k: v for k, v in local_vars.items() if not k.startswith("_")}
            return ToolResult(
                status="success",
                data={"stdout": stdout, "stderr": stderr, "variables": result},
                signals={"has_stdout": bool(stdout), "has_stderr": bool(stderr)},
            )
        except Exception:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            tb = traceback.format_exc()
            return ToolResult(
                status="error",
                data={"stdout": stdout_capture.getvalue(), "traceback": tb},
                error=tb[:500],
            )

    def verify(self, result: ToolResult) -> bool:
        return result.status == "success"
