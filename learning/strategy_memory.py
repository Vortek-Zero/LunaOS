#!/usr/bin/env python3
"""
strategy_memory.py — Memória de estratégias.
Aprende qual ferramenta funciona melhor para cada tipo de tarefa.
"""

import json
from pathlib import Path

MEMORY_FILE = Path(__file__).parent.parent / "data" / "strategy_memory.json"


class StrategyMemory:
    def __init__(self):
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if MEMORY_FILE.exists():
            try:
                return json.loads(MEMORY_FILE.read_text())
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))

    def record(self, goal: str, tool: str, params: dict, success: bool) -> None:
        key = self._normalize_goal(goal)
        if key not in self._data:
            self._data[key] = {
                "attempts": 0,
                "successes": 0,
                "best_tool": None,
                "best_time": None,
                "times": [],
            }
        entry = self._data[key]
        entry["attempts"] += 1
        if success:
            entry["successes"] += 1
            if entry["best_tool"] is None:
                entry["best_tool"] = tool
            else:
                old_rate = entry["successes"] / entry["attempts"]
                if entry["successes"] / entry["attempts"] > old_rate:
                    entry["best_tool"] = tool
        self._save()

    def best_approach(self, goal: str) -> str | None:
        key = self._normalize_goal(goal)
        entry = self._data.get(key)
        if entry and entry["successes"] > 0 and entry["successes"] / entry["attempts"] > 0.5:
            return entry["best_tool"]
        return None

    def success_rate(self, goal: str) -> float:
        key = self._normalize_goal(goal)
        entry = self._data.get(key)
        if not entry or entry["attempts"] == 0:
            return 0.0
        return entry["successes"] / entry["attempts"]

    def _normalize_goal(self, goal: str) -> str:
        return goal.lower().strip().rstrip(".!?")

    def to_dict(self) -> dict:
        return dict(self._data)
