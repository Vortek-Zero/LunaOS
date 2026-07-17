#!/usr/bin/env python3
"""
base_tool.py — Interface padronizada para todas as ferramentas da Luna.
Cada ferramenta implementa: available(), execute(), verify().
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    status: str  # "success" | "error" | "partial"
    data: Any = None
    error: str | None = None
    signals: dict = field(default_factory=dict)


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    category: str = ""  # "browser", "system", "api", "file", etc.
    priority: int = 50  # 0-100, maior = mais preferido

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def execute(self, task: dict) -> ToolResult: ...

    def verify(self, result: ToolResult) -> bool:
        return result.status == "success"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "available": self.available(),
        }
