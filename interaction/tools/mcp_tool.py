#!/usr/bin/env python3
"""
mcp_tool.py — Ferramenta MCP (Model Context Protocol).
Prioridade: 90 (segunda tentativa para tarefas de navegador, depois de DOM).

Usa servidores MCP para interagir com serviços que expõem API via MCP.
"""

from interaction.tools.base_tool import BaseTool, ToolResult


class MCPTool(BaseTool):
    name = "mcp"
    description = "Acesso a serviços via Model Context Protocol (MCP)"
    category = "browser"
    priority = 90

    def __init__(self):
        self._servers = {}

    def available(self) -> bool:
        try:
            return True
        except Exception:
            return False

    def register_server(self, name: str, config: dict) -> None:
        self._servers[name] = config

    def execute(self, task: dict) -> ToolResult:
        server = task.get("server", "")
        tool = task.get("tool", "")
        params = task.get("params", {})

        if not server or server not in self._servers:
            available = list(self._servers.keys())
            return ToolResult(
                status="error" if available else "error",
                data={"available_servers": available},
                error=f"Servidor MCP '{server}' não encontrado" if server else "Nenhum servidor MCP especificado",
            )

        try:
            import json as _json
            import subprocess

            cfg = self._servers[server]
            cmd = cfg.get("command", "")
            if not cmd:
                return ToolResult(status="error", error=f"Servidor MCP '{server}' sem comando")

            args = cfg.get("args", [])
            result = subprocess.run(
                [cmd] + args,
                input=_json.dumps({"tool": tool, "params": params}),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return ToolResult(
                    status="success",
                    data={"stdout": result.stdout, "server": server},
                    signals={"mcp_success": True},
                )
            return ToolResult(
                status="error",
                error=result.stderr[:500],
                signals={"mcp_error": True},
            )

        except Exception as e:
            return ToolResult(status="error", error=str(e))
