#!/usr/bin/env python3
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

SKILLS_DIR = Path(__file__).parent
SKILLS_FILE = SKILLS_DIR / "skills_registry.json"

class SkillManager:
    """
    Gerencia 'Skills' da Luna — planos complexos e reutilizáveis.
    Inspirado no sistema de Skills do Antigravity/claw-code.
    """

    def __init__(self):
        self.skills = self._load_skills()

    def _load_skills(self) -> Dict[str, Any]:
        if SKILLS_FILE.exists():
            try:
                return json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def save_skill(self, name: str, description: str, steps: List[str]):
        self.skills[name] = {
            "name": name,
            "description": description,
            "steps": steps
        }
        self._persist()

    def _persist(self):
        SKILLS_FILE.write_text(json.dumps(self.skills, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_skill(self, name: str) -> Optional[Dict[str, Any]]:
        return self.skills.get(name)

    def list_skills(self) -> str:
        if not self.skills:
            return "Nenhuma skill personalizada registrada."
        return "\n".join([f"- {s['name']}: {s['description']}" for s in self.skills.values()])

_instance = None
def get_skill_manager():
    global _instance
    if _instance is None:
        _instance = SkillManager()
    return _instance
