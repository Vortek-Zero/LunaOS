#!/usr/bin/env python3
"""
api_tool.py — Ferramenta para chamadas a APIs externas via HTTP.
Prioridade: 70 (tentativa principal para tarefas de API).
"""

import json as _json
import urllib.error
import urllib.request

from interaction.tools.base_tool import BaseTool, ToolResult


class APITool(BaseTool):
    name = "api"
    description = "Chamadas a APIs externas via HTTP (GET, POST, PUT, DELETE)"
    category = "api"
    priority = 70

    def available(self) -> bool:
        return True

    def execute(self, task: dict) -> ToolResult:
        url = task.get("url", "")
        method = task.get("method", "GET").upper()
        headers = task.get("headers", {})
        body = task.get("body", {})
        timeout = task.get("timeout", 15)

        if not url:
            return ToolResult(status="error", error="URL não fornecida")

        data = None
        if method in ("POST", "PUT", "PATCH") and body:
            data = _json.dumps(body).encode("utf-8")
            if "Content-Type" not in headers:
                headers["Content-Type"] = "application/json"

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    parsed = _json.loads(raw)
                except Exception:
                    parsed = raw[:2000]

                return ToolResult(
                    status="success",
                    data={"status": resp.status, "body": parsed},
                    signals={"http_ok": resp.status < 400},
                )
        except urllib.error.HTTPError as e:
            return ToolResult(
                status="error",
                data={"status": e.code, "body": e.read().decode("utf-8", errors="ignore")[:500]},
                error=f"HTTP {e.code}",
                signals={"http_error": True},
            )
        except Exception as e:
            return ToolResult(status="error", error=str(e), signals={"exception": True})

    def verify(self, result: ToolResult) -> bool:
        if result.status == "success":
            return True
        return bool(result.signals.get("http_ok"))
