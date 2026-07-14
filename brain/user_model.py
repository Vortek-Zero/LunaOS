#!/usr/bin/env python3
"""
brain/user_model.py — Modelo Interno do Usuário
Rastreia dinamicamente conhecimentos, preferências, habilidades e fatos do usuário.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Any

try:
    from config import PERSONALITY_FILE, USER_PROFILE_FILE
except ImportError:
    USER_PROFILE_FILE = Path(__file__).parent.parent / "config" / "user_profile.json"

logger = logging.getLogger("luna.user_model")


class UserModel:
    """
    Mantém o perfil dinâmico do usuário, adaptando as explicações
    e a postura da Luna de acordo com o nível de conhecimento, preferências e hábitos.
    """

    def __init__(self):
        self.file_path = Path(USER_PROFILE_FILE)
        self._lock = threading.Lock()
        self.profile = self._load()

    def _load(self) -> dict[str, Any]:
        default_profile = {
            "user_name": "Pera",
            "assistant_name": "Luna",
            "personality_mode": "atenciosa, feminina, amigável e solta",
            "preferences": [],
            "skills": {"python": "avançado", "html/css": "avançado"},
            "hobbies": ["Programação", "IAs", "música", "robótica", "Histórias", "Ficção científica"],
            "habits": [],
            "notes": "Lembre-se sempre de ler o contexto de histórico antes de dar uma resposta. Se o modo conversa for iniciado, não procure executar aplicativos nem vasculhar a internet.",
            "system_rules": {"emotion_adaptation": True, "forbid_robotic_tone": True, "empathy_first": True},
        }

        if not self.file_path.exists():
            return default_profile

        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            # Garante campos novos
            if "skills" not in data:
                data["skills"] = default_profile["skills"]
            if "preferences" not in data:
                data["preferences"] = []
            elif isinstance(data["preferences"], str):
                data["preferences"] = [data["preferences"]]
            if "habits" not in data:
                data["habits"] = []
            return data
        except Exception as e:
            logger.error(f"Erro ao carregar user_profile.json: {e}")
            return default_profile

    def save(self):
        """Salva o perfil em arquivo JSON de forma thread-safe."""
        with self._lock:
            try:
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                self.file_path.write_text(json.dumps(self.profile, ensure_ascii=False, indent=4), encoding="utf-8")
            except Exception as e:
                logger.error(f"Erro ao salvar user_profile.json: {e}")

    def update_from_llm(self, key: str, value: Any):
        """Atualiza um campo específico no perfil."""
        with self._lock:
            if key in ["preferences", "hobbies", "habits"]:
                if isinstance(value, list):
                    self.profile[key] = list(set(self.profile.get(key, []) + value))
                elif isinstance(value, str) and value not in self.profile.get(key, []):
                    self.profile.setdefault(key, []).append(value)
            elif key == "skills" and isinstance(value, dict):
                self.profile.setdefault("skills", {}).update(value)
            else:
                self.profile[key] = value
        self.save()

    def update_from_text(self, text: str):
        """
        Gera um update assíncrono analisando a entrada do usuário para descobrir novos fatos.
        Usa o LLM principal de forma rápida para extrair fatos de perfil.
        """

        def _async_extract():
            try:
                from brain.llm import get_llm

                llm = get_llm()

                prompt = f"""Analise a frase do usuário e extraia de forma extremamente objetiva novas informações sobre ele.
Proprocione as informações APENAS se houver autodeclarações explícitas de preferências, conhecimentos/habilidades novas ou hábitos.

Frase: "{text}"

Responda APENAS um JSON com os campos que encontrar ou vazio {{}} se não houver nada relevante:
{{
  "skills": {{ "nome_da_tecnologia": "iniciante|intermediario|avancado" }},
  "preferences": ["nova preferência encontrada"],
  "hobbies": ["novo hobby encontrado"],
  "habits": ["novo hábito percebido"]
}}"""
                messages = [
                    {"role": "system", "content": "Você é um extrator de metadados JSON silencioso e preciso."},
                    {"role": "user", "content": prompt},
                ]

                raw = llm.generate(messages=messages, task_type="utility", model="main")
                content = raw.get("message", {}).get("content", "") if isinstance(raw, dict) else (raw or "")

                # Limpa markdown e parseia
                import re

                m = re.search(r"(\{.*\})", str(content), re.DOTALL)
                if m:
                    extracted = json.loads(m.group(1))
                    if extracted:
                        for k, v in extracted.items():
                            if v:
                                self.update_from_llm(k, v)
                        logger.info(f"Perfil do usuário atualizado dinamicamente: {extracted}")
            except Exception as e:
                # Silencioso em produção
                logger.debug(f"Erro na extração assíncrona do perfil: {e}")

        # Roda em thread separada para não travar a resposta principal da Luna
        threading.Thread(target=_async_extract, daemon=True).start()

    def get_context(self) -> str:
        """Formata o perfil do usuário para ser injetado no system prompt."""
        p = self.profile
        skills_str = ", ".join([f"{k} ({v})" for k, v in p.get("skills", {}).items()])
        pref_list = p.get("preferences", [])
        pref_str = "\n".join([f"- {pr}" for pr in pref_list]) if isinstance(pref_list, list) else f"- {pref_list}"
        hobbies_str = ", ".join(p.get("hobbies", []))
        habits_str = ", ".join(p.get("habits", []))

        ctx = (
            f"[PERFIL E MODELO DO USUÁRIO]\n"
            f"Nome: {p.get('user_name', 'Usuário')}\n"
            f"Habilidades conhecidas: {skills_str}\n"
            f"Hobbies: {hobbies_str}\n"
        )
        if habits_str:
            ctx += f"Hábitos: {habits_str}\n"
        if pref_str:
            ctx += f"Preferências:\n{pref_str}\n"

        return ctx


# Singleton
_user_model_instance: UserModel | None = None


def get_user_model() -> UserModel:
    global _user_model_instance
    if _user_model_instance is None:
        _user_model_instance = UserModel()
    return _user_model_instance
