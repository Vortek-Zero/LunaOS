#!/usr/bin/env python3
"""
registry.py — Catálogo de capacidades da Luna.
Cada categoria mapeia para uma lista ordenada de ferramentas candidatas.
O roteador consulta o registry para saber o que tentar.
"""

from typing import Any


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, list[dict]] = {}
        self._tool_instances: dict[str, Any] = {}

    def register(self, category: str, tool) -> None:
        if category not in self._tools:
            self._tools[category] = []
        entry = {
            "name": tool.name,
            "priority": tool.priority,
            "instance": tool,
        }
        self._tools[category].append(entry)
        self._tools[category].sort(key=lambda x: x["priority"], reverse=True)
        self._tool_instances[tool.name] = tool

    def find(self, category: str) -> list[Any]:
        """Retorna instâncias de ferramentas para uma categoria, ordenadas por prioridade."""
        entries = self._tools.get(category, [])
        return [e["instance"] for e in entries]

    def find_by_name(self, name: str) -> Any | None:
        return self._tool_instances.get(name)

    def categories(self) -> list[str]:
        return list(self._tools.keys())

    def all_tools(self) -> list[Any]:
        seen = set()
        result = []
        for cat in self._tools.values():
            for entry in cat:
                inst = entry["instance"]
                if inst.name not in seen:
                    seen.add(inst.name)
                    result.append(inst)
        return result

    def to_dict(self) -> dict:
        return {
            cat: [
                {
                    "name": e["name"],
                    "priority": e["priority"],
                    "available": e["instance"].available(),
                }
                for e in entries
            ]
            for cat, entries in self._tools.items()
        }


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _auto_register()
    return _registry


def _auto_register() -> None:
    tools = [
        ("interaction.tools.dom_tool", "DOMTool", "browser"),
        ("interaction.tools.mcp_tool", "MCPTool", "browser"),
        ("interaction.tools.vision_tool", "VisionTool", "browser"),
        ("interaction.tools.bash_tool", "BashTool", "system"),
        ("interaction.tools.python_tool", "PythonTool", "system"),
        ("interaction.tools.api_tool", "APITool", "api"),
    ]
    for mod_path, cls_name, category in tools:
        try:
            import importlib

            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name, None)
            if cls:
                instance = cls()
                if instance.available():
                    _registry.register(category, instance)
        except Exception:
            pass
