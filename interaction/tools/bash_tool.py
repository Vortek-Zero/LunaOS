#!/usr/bin/env python3
"""
bash_tool.py — Executa comandos no terminal.
Prioridade: 100 (sempre preferido para tarefas de sistema).
"""

import subprocess

from interaction.tools.base_tool import BaseTool, ToolResult


class BashTool(BaseTool):
    name = "bash"
    description = "Executa comandos no terminal do sistema Linux"
    category = "system"
    priority = 100

    def available(self) -> bool:
        return True

    def execute(self, task: dict) -> ToolResult:
        command = task.get("command") or task.get("goal", "")
        cwd = task.get("cwd")
        timeout = task.get("timeout", 30)

        if not command:
            return ToolResult(status="error", error="Nenhum comando fornecido")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd or None,
                timeout=timeout,
            )
            signals = {
                "returncode": result.returncode,
                "stdout_length": len(result.stdout),
                "stderr_length": len(result.stderr),
            }
            if result.returncode == 0:
                return ToolResult(
                    status="success",
                    data={"stdout": result.stdout, "stderr": result.stderr},
                    signals=signals,
                )
            return ToolResult(
                status="error",
                data={"stdout": result.stdout, "stderr": result.stderr},
                error=result.stderr[:500],
                signals=signals,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(status="error", error=f"Timeout de {timeout}s excedido")
        except Exception as e:
            return ToolResult(status="error", error=str(e))

    def verify(self, result: ToolResult) -> bool:
        if result.status == "success":
            return True
        return result.signals.get("returncode") == 0
