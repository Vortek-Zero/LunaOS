#!/usr/bin/env python3
"""
actions/filesystem.py — Acesso ao sistema de arquivos do usuário (Arch/home).
Sem API keys — opera direto no disco local.
"""
import os
import shutil
import fnmatch
from pathlib import Path
from typing import Optional

try:
    from config import WORKSPACE_DIR
except ImportError:
    WORKSPACE_DIR = Path.home() / "Luna-programming"

HOME = Path.home()
ALLOWED_ROOTS = [HOME, Path("/tmp"), WORKSPACE_DIR]


class FilesystemManager:
    def _resolve(self, path_str: str) -> Path:
        p = Path(path_str).expanduser()
        if not p.is_absolute():
            p = HOME / p
        resolved = p.resolve()
        if not any(resolved == r or resolved.is_relative_to(r) for r in ALLOWED_ROOTS):
            raise PermissionError(f"Acesso negado fora de {HOME} e /tmp: {path_str}")
        return resolved

    def list_dir(self, path: str = "~", pattern: str = "*", max_entries: int = 100) -> str:
        try:
            target = self._resolve(path or "~")
            if not target.is_dir():
                return f"FALHOU: '{path}' não é um diretório."
            entries = []
            for item in sorted(target.iterdir()):
                if not fnmatch.fnmatch(item.name, pattern):
                    continue
                kind = "📁" if item.is_dir() else "📄"
                size = item.stat().st_size if item.is_file() else 0
                entries.append(f"{kind} {item.name}" + (f" ({size} bytes)" if size else ""))
                if len(entries) >= max_entries:
                    entries.append(f"... (+ mais arquivos, limite {max_entries})")
                    break
            if not entries:
                return f"Diretório vazio: {target}"
            return f"Conteúdo de {target}:\n" + "\n".join(entries)
        except Exception as e:
            return f"FALHOU: {e}"

    def read_text(self, path: str, max_chars: int = 12000) -> str:
        try:
            target = self._resolve(path)
            if not target.is_file():
                return f"FALHOU: arquivo não encontrado: {path}"
            text = target.read_text(encoding="utf-8", errors="replace")
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n... (truncado, {len(text)} chars total)"
            return f"Arquivo {target.name}:\n{text}"
        except Exception as e:
            return f"FALHOU: {e}"

    def write_text(self, path: str, content: str, append: bool = False) -> str:
        try:
            target = self._resolve(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if append and target.exists():
                with target.open("a", encoding="utf-8") as f:
                    f.write(content)
            else:
                target.write_text(content, encoding="utf-8")
            return f"Arquivo salvo: {target}"
        except Exception as e:
            return f"FALHOU: {e}"

    def mkdir(self, path: str) -> str:
        try:
            target = self._resolve(path)
            target.mkdir(parents=True, exist_ok=True)
            return f"Pasta criada: {target}"
        except Exception as e:
            return f"FALHOU: {e}"

    def move(self, src: str, dst: str) -> str:
        try:
            s, d = self._resolve(src), self._resolve(dst)
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(s), str(d))
            return f"Movido: {s.name} → {d}"
        except Exception as e:
            return f"FALHOU: {e}"

    def delete(self, path: str) -> str:
        try:
            target = self._resolve(path)
            if target.is_dir():
                shutil.rmtree(target)
            elif target.is_file():
                target.unlink()
            else:
                return f"FALHOU: não encontrado: {path}"
            return f"Removido: {target}"
        except Exception as e:
            return f"FALHOU: {e}"

    def stat(self, path: str) -> str:
        try:
            target = self._resolve(path)
            if not target.exists():
                return f"FALHOU: não existe: {path}"
            st = target.stat()
            kind = "pasta" if target.is_dir() else "arquivo"
            return (
                f"{target}\n"
                f"Tipo: {kind}\n"
                f"Tamanho: {st.st_size} bytes\n"
                f"Modificado: {st.st_mtime}"
            )
        except Exception as e:
            return f"FALHOU: {e}"

    def search(self, query: str, root: str = "~", max_results: int = 30) -> str:
        try:
            base = self._resolve(root or "~")
            if not base.is_dir():
                return f"FALHOU: root inválido: {root}"
            q = query.lower()
            hits = []
            skip = {".cache", ".local/share/Trash", "node_modules", ".git", ".venv", "__pycache__"}
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
                rel = Path(dirpath).relative_to(base)
                if any(s in str(rel) for s in skip):
                    continue
                for name in filenames + dirnames:
                    if q in name.lower():
                        hits.append(str(Path(dirpath) / name))
                        if len(hits) >= max_results:
                            break
                if len(hits) >= max_results:
                    break
            if not hits:
                return f"Nenhum resultado para '{query}' em {base}"
            return "Resultados:\n" + "\n".join(f"  • {h}" for h in hits)
        except Exception as e:
            return f"FALHOU: {e}"


_fs_instance: Optional[FilesystemManager] = None


def get_filesystem() -> FilesystemManager:
    global _fs_instance
    if _fs_instance is None:
        _fs_instance = FilesystemManager()
    return _fs_instance
