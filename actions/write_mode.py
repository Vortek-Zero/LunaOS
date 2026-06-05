#!/usr/bin/env python3
"""
actions/write_mode.py — Gerenciador de projetos de escrita criativa
Sistema de projetos com fichas de personagem e memória de universo ficcional
"""
import json
import re
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional


DATA_DIR = Path(__file__).parent.parent / "data"
PROJECTS_FILE = DATA_DIR / "write_projects.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class CharacterSheet:
    """Ficha de personagem para manter consistência narrativa."""

    def __init__(self, name: str, age: int = 0, voice: str = "", traits: str = "", context: str = ""):
        self.name = name
        self.age = age
        self.voice = voice        # Como o personagem fala (ex: "direto, curto, usa gírias")
        self.traits = traits      # Traços de personalidade
        self.context = context    # Contexto social/situação

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "age": self.age,
            "voice": self.voice,
            "traits": self.traits,
            "context": self.context,
        }

    @staticmethod
    def from_dict(d: dict) -> "CharacterSheet":
        return CharacterSheet(
            name=d.get("name", ""),
            age=d.get("age", 0),
            voice=d.get("voice", ""),
            traits=d.get("traits", ""),
            context=d.get("context", ""),
        )

    def to_prompt_text(self) -> str:
        """Formata a ficha para injeção no prompt."""
        lines = [f"Personagem: {self.name}"]
        if self.age:
            lines.append(f"  Idade: {self.age} anos")
        if self.voice:
            lines.append(f"  Como fala: {self.voice}")
        if self.traits:
            lines.append(f"  Personalidade: {self.traits}")
        if self.context:
            lines.append(f"  Contexto: {self.context}")
        return "\n".join(lines)


class WriteProject:
    """Projeto de escrita com capítulos, personagens e histórico."""

    def __init__(
        self,
        project_id: str,
        title: str,
        genre: str = "ficção",
        style: str = "neutro",
        text: str = "",
        characters: list = None,
        chapters: list = None,
        created_at: str = "",
        updated_at: str = "",
    ):
        self.project_id = project_id
        self.title = title
        self.genre = genre
        self.style = style        # adolescente, adulto, thriller, romance, neutro
        self.text = text
        self.characters: list[CharacterSheet] = [
            CharacterSheet.from_dict(c) if isinstance(c, dict) else c
            for c in (characters or [])
        ]
        self.chapters: list[dict] = chapters or []
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "genre": self.genre,
            "style": self.style,
            "text": self.text,
            "characters": [c.to_dict() for c in self.characters],
            "chapters": self.chapters,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "WriteProject":
        return WriteProject(
            project_id=d.get("project_id", str(uuid.uuid4())),
            title=d.get("title", "Sem título"),
            genre=d.get("genre", "ficção"),
            style=d.get("style", "neutro"),
            text=d.get("text", ""),
            characters=d.get("characters", []),
            chapters=d.get("chapters", []),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )

    def get_characters_prompt(self) -> str:
        """Formata todos os personagens para injeção no prompt."""
        if not self.characters:
            return ""
        return "\n\n".join(c.to_prompt_text() for c in self.characters)

    def add_chapter(self, title: str = "") -> int:
        """Adiciona um capítulo e retorna o número."""
        chapter_num = len(self.chapters) + 1
        title = title or f"Capítulo {chapter_num}"
        marker = f"\n\n▸ {title.upper()}\n\n"
        self.text += marker
        self.chapters.append({
            "number": chapter_num,
            "title": title,
            "start_pos": len(self.text) - len(marker),
            "created_at": datetime.now().isoformat(),
        })
        self.updated_at = datetime.now().isoformat()
        return chapter_num

    def save_text(self, new_text: str) -> None:
        self.text = new_text
        self.updated_at = datetime.now().isoformat()

    def get_context_summary(self, max_chars: int = 4000) -> str:
        """Retorna o texto atual truncado para uso como contexto."""
        if len(self.text) <= max_chars:
            return self.text
        # Pega o início e o final para dar contexto geral + contexto recente
        start = self.text[:1000]
        end = self.text[-(max_chars - 1000):]
        return f"{start}\n\n[...]\n\n{end}"


class WriteModeManager:
    """Gerenciador de projetos de escrita."""

    def __init__(self):
        self._projects: dict[str, WriteProject] = {}
        self._load()

    def _load(self) -> None:
        try:
            if PROJECTS_FILE.exists():
                data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
                for p in data.get("projects", []):
                    proj = WriteProject.from_dict(p)
                    self._projects[proj.project_id] = proj
        except Exception as e:
            print(f"[WriteMode] Erro ao carregar projetos: {e}")

    def _save(self) -> None:
        try:
            PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {"projects": [p.to_dict() for p in self._projects.values()]}
            PROJECTS_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[WriteMode] Erro ao salvar projetos: {e}")

    def list_projects(self) -> list[dict]:
        return [
            {
                "project_id": p.project_id,
                "title": p.title,
                "genre": p.genre,
                "style": p.style,
                "chapter_count": len(p.chapters),
                "text_length": len(p.text),
                "updated_at": p.updated_at,
            }
            for p in sorted(self._projects.values(), key=lambda x: x.updated_at, reverse=True)
        ]

    def create_project(
        self,
        title: str,
        genre: str = "ficção",
        style: str = "neutro",
        characters: list = None,
    ) -> WriteProject:
        project_id = str(uuid.uuid4())[:8]
        proj = WriteProject(
            project_id=project_id,
            title=title,
            genre=genre,
            style=style,
            characters=characters or [],
        )
        self._projects[project_id] = proj
        self._save()
        return proj

    def get_project(self, project_id: str) -> Optional[WriteProject]:
        return self._projects.get(project_id)

    def update_text(self, project_id: str, new_text: str) -> bool:
        proj = self.get_project(project_id)
        if not proj:
            return False
        proj.save_text(new_text)
        self._save()
        return True

    def add_chapter(self, project_id: str, title: str = "") -> Optional[dict]:
        proj = self.get_project(project_id)
        if not proj:
            return None
        chapter_num = proj.add_chapter(title)
        self._save()
        return {
            "chapter_num": chapter_num,
            "title": title or f"Capítulo {chapter_num}",
            "marker": f"▸ {(title or f'CAPÍTULO {chapter_num}').upper()}",
            "updated_text": proj.text,
        }

    def add_character(self, project_id: str, character: dict) -> bool:
        proj = self.get_project(project_id)
        if not proj:
            return False
        proj.characters.append(CharacterSheet.from_dict(character))
        proj.updated_at = datetime.now().isoformat()
        self._save()
        return True

    def delete_project(self, project_id: str) -> bool:
        if project_id not in self._projects:
            return False
        del self._projects[project_id]
        self._save()
        return True

    def remember_story_fact(self, project_id: str, fact: str, category: str = "historia") -> None:
        """Persiste um fato do universo ficcional no RAG vetorial."""
        try:
            from brain.memory_rag import MemoryRAG
            rag = MemoryRAG()
            rag.remember_story_fact(project_id=project_id, fact=fact, category=category)
        except Exception:
            pass

    def recall_story_context(self, project_id: str, query: str) -> str:
        """Recupera contexto do universo ficcional para o prompt."""
        try:
            from brain.memory_rag import MemoryRAG
            rag = MemoryRAG()
            return rag.recall_story_context(project_id=project_id, query=query)
        except Exception:
            return ""


# Singleton
_write_mode_instance = None

def get_write_mode() -> WriteModeManager:
    global _write_mode_instance
    if _write_mode_instance is None:
        _write_mode_instance = WriteModeManager()
    return _write_mode_instance
