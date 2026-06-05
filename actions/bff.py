#!/usr/bin/env python3
"""
actions/bff.py — Luna BFF
Modo amiga: hobbys, apoio emocional e wiki rápida.
"""
import json
import os
from pathlib import Path
from typing import Optional

try:
    from brain.llm import get_llm, MODELS
except ImportError:
    from brain.llm import get_llm, MODELS

DATA_PATH = Path(__file__).parent.parent / "data" / "bff_profile.json"

_DEFAULT_PROFILE = {
    "hobbies": [],
    "mood_log": [],
    "wiki_cache": {},
}

BFF_SYSTEM = (
    "Você é Luna, a melhor amiga do usuário. Você é carinhosa, divertida, empática e honesta. "
    "Você conhece os hobbys e interesses do usuário. Responda sempre em português, "
    "de forma natural e afetuosa, como uma amiga de verdade faria."
)


class BFFMode:
    def __init__(self):
        self._llm = get_llm()
        self._profile = self._load_profile()

    def _load_profile(self) -> dict:
        if DATA_PATH.exists():
            try:
                return json.loads(DATA_PATH.read_text())
            except Exception:
                pass
        return dict(_DEFAULT_PROFILE)

    def _save_profile(self):
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        DATA_PATH.write_text(json.dumps(self._profile, ensure_ascii=False, indent=2))

    # ── Hobbys ────────────────────────────────────────────────

    def add_hobby(self, hobby: str) -> str:
        hobby = hobby.strip()
        if hobby and hobby not in self._profile["hobbies"]:
            self._profile["hobbies"].append(hobby)
            self._save_profile()
            return f"Anotei! Agora sei que você curte {hobby} 🎉"
        return f"Já sabia que você curte {hobby}!"

    def list_hobbies(self) -> str:
        if not self._profile["hobbies"]:
            return "Ainda não sei seus hobbys. Me conta o que você curte!"
        return "Seus hobbys: " + ", ".join(self._profile["hobbies"])

    # ── Apoio emocional ───────────────────────────────────────

    def emotional_support(self, message: str) -> str:
        hobbies_ctx = ""
        if self._profile["hobbies"]:
            hobbies_ctx = f"Hobbys do usuário: {', '.join(self._profile['hobbies'])}. "
        prompt = (
            f"{BFF_SYSTEM}\n{hobbies_ctx}\n"
            f"O usuário disse: \"{message}\"\n\n"
            "Responda com empatia e carinho, como uma boa amiga faria:"
        )
        raw = self._llm.generate(prompt, task_type="conversational", model=MODELS.get("main"))
        try:
            data = json.loads(raw)
            return data.get("response", data.get("message", raw))
        except Exception:
            return raw

    # ── Wiki rápida ───────────────────────────────────────────

    def wiki(self, topic: str) -> str:
        """Explica um tópico de forma amigável e resumida."""
        if topic in self._profile["wiki_cache"]:
            return self._profile["wiki_cache"][topic]

        prompt = (
            f"{BFF_SYSTEM}\n"
            f"Explique \"{topic}\" de forma simples, amigável e resumida (máx 4 frases) em português:"
        )
        raw = self._llm.generate(prompt, task_type="factual", model=MODELS.get("main"))
        try:
            data = json.loads(raw)
            result = data.get("response", data.get("explanation", raw))
        except Exception:
            result = raw

        # Cache simples (máx 50 entradas)
        if len(self._profile["wiki_cache"]) >= 50:
            oldest = next(iter(self._profile["wiki_cache"]))
            del self._profile["wiki_cache"][oldest]
        self._profile["wiki_cache"][topic] = result
        self._save_profile()
        return result

    # ── Chat geral BFF ────────────────────────────────────────

    def chat(self, message: str) -> str:
        hobbies_ctx = ""
        if self._profile["hobbies"]:
            hobbies_ctx = f"Hobbys do usuário: {', '.join(self._profile['hobbies'])}. "
        prompt = (
            f"{BFF_SYSTEM}\n{hobbies_ctx}\n"
            f"Usuário: {message}\nLuna:"
        )
        raw = self._llm.generate(prompt, task_type="conversational", model=MODELS.get("main"))
        try:
            data = json.loads(raw)
            return data.get("response", data.get("message", raw))
        except Exception:
            return raw


_bff: Optional[BFFMode] = None


def get_bff() -> BFFMode:
    global _bff
    if _bff is None:
        _bff = BFFMode()
    return _bff
