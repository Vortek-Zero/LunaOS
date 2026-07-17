#!/usr/bin/env python3
"""
scoring.py — Sistema de pontuação para ferramentas.
Cada execução bem-sucedida aumenta a nota; falhas diminuem.
O router consulta o scoring para decidir qual ferramenta tentar primeiro.
"""

import json
from pathlib import Path

SCORE_FILE = Path(__file__).parent.parent / "data" / "tool_scores.json"


class ToolScorer:
    def __init__(self):
        self._scores: dict[str, dict] = self._load()
        self._session_scores: dict[str, dict] = {}

    def _load(self) -> dict:
        if SCORE_FILE.exists():
            try:
                return json.loads(SCORE_FILE.read_text())
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        SCORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCORE_FILE.write_text(json.dumps(self._scores, indent=2, ensure_ascii=False))

    def record(self, tool_name: str, category: str, success: bool, elapsed: float = 0) -> None:
        if tool_name not in self._scores:
            self._scores[tool_name] = {
                "attempts": 0,
                "successes": 0,
                "total_time": 0,
                "categories": [],
                "score": 50,
            }
        entry = self._scores[tool_name]
        entry["attempts"] += 1
        entry["total_time"] += elapsed
        if success:
            entry["successes"] += 1
        if category and category not in entry["categories"]:
            entry["categories"].append(category)

        success_rate = entry["successes"] / entry["attempts"] if entry["attempts"] > 0 else 0
        time_factor = max(0, 1 - (entry["total_time"] / entry["attempts"]) / 30) if entry["attempts"] > 0 else 0.5
        entry["score"] = int(success_rate * 70 + time_factor * 30)

        self._save()

    def best_tool(self, category: str = "") -> str | None:
        candidates = []
        for name, entry in self._scores.items():
            if category and category not in entry.get("categories", []):
                continue
            candidates.append((entry.get("score", 0), name))

        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    def get_score(self, tool_name: str) -> int:
        entry = self._scores.get(tool_name)
        if not entry:
            return 50
        return entry.get("score", 50)

    def to_dict(self) -> dict:
        return dict(self._scores)


_scorer: ToolScorer | None = None


def get_scorer() -> ToolScorer:
    global _scorer
    if _scorer is None:
        _scorer = ToolScorer()
    return _scorer
