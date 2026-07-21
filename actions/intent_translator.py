#!/usr/bin/env python3
"""
actions/intent_translator.py — Tradutor de Intenção da Luna.
Mapeia termos genéricos (browser, navegador, editor, terminal) para as ferramentas
e aplicativos específicos preferidos pelo usuário no sistema.

Lê preferências dinâmicas de config/user_profile.json.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("luna.intent_translator")

USER_PROFILE_FILE = Path(__file__).parent.parent / "config" / "user_profile.json"

# Categorias de intenção → campo de preferência no perfil
_PREFERENCE_FIELDS = {
    "browser": "preferred_browser",
    "navegador": "preferred_browser",
    "chrome": "preferred_browser",
    "chromium": "preferred_browser",
    "web": "preferred_browser",
    "internet": "preferred_browser",
    "editor": "preferred_editor",
    "code_editor": "preferred_editor",
    "ide": "preferred_editor",
    "terminal": "preferred_terminal",
    "shell": "preferred_terminal",
    "bash": "preferred_terminal",
    "musica": "preferred_player",
    "música": "preferred_player",
    "player": "preferred_player",
}

# Defaults para cada campo de preferência (usados se o perfil não definir)
_PREFERENCE_DEFAULTS = {
    "preferred_browser": "firefox",
    "preferred_editor": "code",
    "preferred_terminal": "gnome-terminal",
    "preferred_player": "spotify",
}


class IntentTranslator:
    """Tradutor de intenções para comandos e aplicativos nativos do usuário."""

    def __init__(self):
        self._preferences: dict[str, str] = {}
        self._profile_mtime: float = 0.0
        self._load_preferences()

    def _load_preferences(self) -> None:
        """Carrega preferências do user_profile.json (com detecção de mudança por mtime)."""
        try:
            if not USER_PROFILE_FILE.exists():
                return
            mtime = USER_PROFILE_FILE.stat().st_mtime
            if mtime == self._profile_mtime:
                return  # Arquivo não mudou
            self._profile_mtime = mtime
            data = json.loads(USER_PROFILE_FILE.read_text(encoding="utf-8"))
            prefs = data.get("preferences_apps", {})
            if isinstance(prefs, dict):
                self._preferences = prefs
            # Fallback: lê de habits[] para inferir browser preferido
            if "preferred_browser" not in self._preferences:
                habits = data.get("habits", [])
                for habit in habits:
                    habit_lower = str(habit).lower()
                    if "firefox" in habit_lower:
                        self._preferences.setdefault("preferred_browser", "firefox")
                    elif "chrome" in habit_lower:
                        self._preferences.setdefault("preferred_browser", "google-chrome")
                    elif "brave" in habit_lower:
                        self._preferences.setdefault("preferred_browser", "brave-browser")
        except Exception as e:
            logger.warning(f"Erro ao carregar preferências: {e}")

    def _get_preference(self, pref_field: str) -> str:
        """Retorna a preferência do usuário para um campo, ou o default."""
        # Recarrega se o arquivo mudou (hot-reload)
        self._load_preferences()
        return self._preferences.get(pref_field, _PREFERENCE_DEFAULTS.get(pref_field, ""))

    def translate_app_name(self, raw_app_name: str) -> str:
        """
        Traduz um nome genérico de aplicativo para o nome preferido do usuário.
        Ex: 'browser' -> 'firefox' (ou 'brave-browser' se configurado)
        """
        if not raw_app_name:
            return raw_app_name
        cleaned = raw_app_name.strip().lower()
        pref_field = _PREFERENCE_FIELDS.get(cleaned)
        if pref_field:
            return self._get_preference(pref_field)
        return cleaned

    def translate_intent(self, intent_type: str, payload: Any) -> Any:
        """Traduz payloads genéricos baseados no tipo de intenção."""
        if intent_type == "open_app":
            return self.translate_app_name(str(payload))
        return payload


_translator_instance = None


def get_intent_translator() -> IntentTranslator:
    global _translator_instance
    if _translator_instance is None:
        _translator_instance = IntentTranslator()
    return _translator_instance


def translate_app(app_name: str) -> str:
    """Função rápida para tradução de aplicativos."""
    return get_intent_translator().translate_app_name(app_name)
