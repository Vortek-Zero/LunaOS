#!/usr/bin/env python3
"""
brain/dictionary.py — Dicionário inteligente da Luna ("Luna Words")
Usa dictionaryapi.dev (PT) com fallback para geração pelo LLM.
"""
import re
import json
from typing import Optional
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request

# Palavras-chave que ativam o modo dicionário
DICT_TRIGGERS = [
    "o que significa",
    "o que quer dizer",
    "definição de",
    "define a palavra",
    "defina a palavra",
    "dicionário",
    "luna words",
    "significado de",
    "sinônimos de",
    "antônimos de",
    "sinonimos de",
    "antonimos de",
    "conceito de",
]

# API pública gratuita — dicionário em PT
PT_DICT_URL = "https://api.dictionaryapi.dev/api/v2/entries/pt/{word}"

# Sessão reutilizável
_session = None

def _get_session():
    global _session
    if _session is None and HAS_REQUESTS:
        _session = requests.Session()
        _session.headers.update({"Accept": "application/json"})
    return _session


class DictionaryManager:
    """Gerencia consultas ao dicionário para o modo Luna Words."""

    def is_dict_request(self, text: str) -> Optional[str]:
        """
        Verifica se o texto é uma consulta ao dicionário.
        Retorna a palavra-chave consultada ou None.
        """
        tl = text.lower().strip()
        for trigger in DICT_TRIGGERS:
            if trigger in tl:
                # Extrai a palavra após o trigger
                word = tl.replace(trigger, "").strip()
                word = re.sub(r'[^\w\s]', '', word).strip()
                # Pega a última palavra significativa
                parts = [p for p in word.split() if len(p) > 1]
                if parts:
                    return parts[-1]
        return None

    def lookup(self, word: str) -> str:
        """
        Busca definição, sinônimos e exemplos de uma palavra.
        Retorna texto formatado para a Luna responder.
        """
        word = word.strip().lower()
        if not word:
            return "Por favor, especifique qual palavra você quer consultar."

        result = self._fetch_pt_api(word)
        if result:
            return result

        # Fallback: gera definição básica offline
        return self._fallback_response(word)

    def _fetch_pt_api(self, word: str) -> Optional[str]:
        """Consulta a API pública dictionaryapi.dev para PT."""
        try:
            url = PT_DICT_URL.format(word=word)
            sess = _get_session()
            if sess:
                resp = sess.get(url, timeout=5)
            else:
                with urllib.request.urlopen(url, timeout=5) as r:
                    resp_data = r.read().decode()
                    data = json.loads(resp_data)
                    return self._parse_api_response(data, word)

            if resp.status_code != 200:
                return None

            data = resp.json()
            return self._parse_api_response(data, word)

        except Exception:
            return None

    def _parse_api_response(self, data: list, word: str) -> Optional[str]:
        """Formata a resposta da API em texto legível."""
        if not data or not isinstance(data, list):
            return None

        entry = data[0]
        phonetic = entry.get("phonetic", "")
        meanings = entry.get("meanings", [])

        if not meanings:
            return None

        lines = []
        lines.append(f"📖 {word.upper()}")
        if phonetic:
            lines.append(f"   Fonética: {phonetic}")

        for meaning in meanings[:3]:
            part_of_speech = meaning.get("partOfSpeech", "")
            definitions = meaning.get("definitions", [])
            synonyms = meaning.get("synonyms", [])
            antonyms = meaning.get("antonyms", [])

            if part_of_speech:
                lines.append(f"\n• {part_of_speech.capitalize()}")

            for i, defn in enumerate(definitions[:2]):
                definition = defn.get("definition", "")
                example = defn.get("example", "")
                if definition:
                    lines.append(f"  {i+1}. {definition}")
                if example:
                    lines.append(f"     Ex: \"{example}\"")

            def_syns = definitions[0].get("synonyms", []) if definitions else []
            all_syns = list(dict.fromkeys(synonyms + def_syns))[:5]
            if all_syns:
                lines.append(f"  Sinônimos: {', '.join(all_syns)}")

            all_ants = antonyms[:4]
            if all_ants:
                lines.append(f"  Antônimos: {', '.join(all_ants)}")

        return "\n".join(lines)

    def _fallback_response(self, word: str) -> str:
        """Resposta quando a API não retorna resultado."""
        return (
            f"Não encontrei '{word}' no dicionário. "
            f"Tente verificar a ortografia ou consulte um dicionário online como "
            f"priberam.pt ou dicio.com.br para esta palavra."
        )


# Singleton
_dict_instance = None

def get_dictionary() -> DictionaryManager:
    global _dict_instance
    if _dict_instance is None:
        _dict_instance = DictionaryManager()
    return _dict_instance
