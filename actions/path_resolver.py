#!/usr/bin/env python3
"""
actions/path_resolver.py — Mapeador e resolvedor de caminhos do sistema operacional.
Resolve apelidos e caminhos genéricos em inglês (Desktop, Documents, Downloads, etc)
para os caminhos reais do sistema em PT-BR (Área de Trabalho, Documentos, etc).
"""

import os
import shutil
import subprocess
from pathlib import Path

# Mapeamento padrão de fallback PT-BR
STANDARD_MAP = {
    "desktop": "Área de Trabalho",
    "documents": "Documentos",
    "downloads": "Downloads",
    "pictures": "Imagens",
    "music": "Música",
    "videos": "Vídeos",
    "templates": "Modelos",
}


class PathResolver:
    """Resolvedor inteligente de caminhos do sistema."""

    def __init__(self):
        self.home = Path.home()
        self.mapping = self._detect_real_user_dirs()

    def _detect_real_user_dirs(self) -> dict[str, str]:
        """Detecta o mapeamento real das pastas do usuário via xdg-user-dir ou checagem física.
        
        Retorna dicionário {apelido: caminho_absoluto} para resolução universal.
        """
        mapping: dict[str, str] = {}

        # 1. Tenta xdg-user-dir no Linux — consulta direta ao SO
        if shutil.which("xdg-user-dir"):
            xdg_keys = {
                "desktop": "DESKTOP",
                "documents": "DOCUMENTS",
                "downloads": "DOWNLOAD",
                "pictures": "PICTURES",
                "music": "MUSIC",
                "videos": "VIDEOS",
                "templates": "TEMPLATES",
            }
            for key, xdg_name in xdg_keys.items():
                try:
                    res = subprocess.run(
                        ["xdg-user-dir", xdg_name],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    path_str = res.stdout.strip()
                    if path_str and Path(path_str).exists():
                        # Armazena caminho absoluto completo, não apenas o nome
                        mapping[key] = str(Path(path_str).resolve())
                except Exception:
                    pass

        # 2. Fallback: verifica se a pasta física existe no Home
        for key, default_ptbr in STANDARD_MAP.items():
            if key not in mapping:
                candidate = self.home / default_ptbr
                if candidate.exists():
                    mapping[key] = str(candidate.resolve())
                else:
                    # Tenta nome em inglês como último recurso
                    en_name = self.home / key.capitalize()
                    if en_name.exists():
                        mapping[key] = str(en_name.resolve())
                    else:
                        # Mantém o padrão PT-BR mesmo que não exista (para criação futura)
                        mapping[key] = str(candidate)

        return mapping

    def resolve(self, path_str: str) -> str:
        """
        Recebe uma string de caminho e retorna o caminho real resolvido no sistema.
        Ex: '~/Desktop/arquivo.txt' -> '/home/pera/Área de Trabalho/arquivo.txt'
        """
        if not path_str:
            return path_str

        raw_str = str(path_str).strip()

        # Expande ~
        if raw_str.startswith("~"):
            p = self.home / raw_str[1:].lstrip("/\\")
        else:
            p = Path(raw_str)

        parts = list(p.parts)
        if not parts:
            return raw_str

        # Se já for caminho absoluto, apenas normaliza e retorna
        if p.is_absolute():
            # Mesmo absoluto pode ter apelido embutido, tenta refinar
            try:
                rel_parts = p.relative_to(self.home).parts
                if rel_parts:
                    first_dir = rel_parts[0]
                    first_dir_lower = first_dir.lower()
                    if first_dir_lower in self.mapping:
                        target_abs = Path(self.mapping[first_dir_lower])
                        # Se o mapping já é caminho absoluto completo, use-o diretamente
                        if target_abs.is_absolute():
                            new_path = target_abs.joinpath(*rel_parts[1:])
                            return str(new_path)
            except ValueError:
                pass
            return str(p.resolve())

        # Se o caminho for relativo como "Desktop/file.txt" ou "Área de Trabalho/file.txt"
        first_part_lower = parts[0].lower()
        if first_part_lower in self.mapping:
            target = self.mapping[first_part_lower]
            target_path = Path(target)
            if target_path.is_absolute():
                return str(target_path.joinpath(*parts[1:]))
            else:
                return str(self.home / target, *parts[1:])

        # Fallback: trata como relativo ao home
        return str(self.home.joinpath(*parts))


_path_resolver_instance = None


def get_path_resolver() -> PathResolver:
    global _path_resolver_instance
    if _path_resolver_instance is None:
        _path_resolver_instance = PathResolver()
    return _path_resolver_instance


def resolve_path(path_str: str) -> str:
    """Função utilitária rápida para resolver caminhos."""
    return get_path_resolver().resolve(path_str)
