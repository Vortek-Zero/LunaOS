"""
brain/tool_registry.py — Sistema de registro de ferramentas inspirado no Agent-S
Usa decorator @tool_action para auto-registro e documentação dinâmica
"""
import inspect
import functools
from pathlib import Path
from typing import Any, Callable


class ToolRegistry:
    """
    Registro central de ferramentas da Luna.
    Inspirado no @agent_action decorator do Agent-S.

    Cada ferramenta registrada:
    - Nome, descrição, assinatura, parâmetros
    - Função de execução
    - Função de verificação (reflection-style)
    - Categoria (filesystem, code, google, system, etc)
    """

    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, name: str, description: str, category: str = "geral",
                 verify_fn: Callable = None):
        """
        Decorator para registrar uma ferramenta.
        Uso:
            @registry.register("write_code", "Cria um arquivo de código", "code", verify_fn=check_file_exists)
            def write_code(filename, content):
                ...
        """
        def decorator(func: Callable):
            sig = inspect.signature(func)
            params = []
            for param_name, param in sig.parameters.items():
                param_type = "string"
                if param.annotation != inspect.Parameter.empty:
                    if param.annotation == int:
                        param_type = "integer"
                    elif param.annotation == bool:
                        param_type = "boolean"
                    elif param.annotation == list:
                        param_type = "array"
                    elif param.annotation == dict:
                        param_type = "object"
                params.append({
                    "name": param_name,
                    "type": param_type,
                    "required": param.default == inspect.Parameter.empty,
                    "description": "",
                })

            self._tools[name] = {
                "name": name,
                "description": description,
                "category": category,
                "params": params,
                "fn": func,
                "verify": verify_fn,
                "signature": str(sig),
            }

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                result = func(*args, **kwargs)
                if verify_fn:
                    try:
                        # Passa apenas os kwargs que a função de verificação aceita
                        sig = inspect.signature(verify_fn)
                        filtered_kwargs = {k: v for k, v in kwargs.items()
                                           if k in sig.parameters}
                        verified = verify_fn(**filtered_kwargs)
                    except Exception:
                        verified = False
                    if not verified:
                        return f"FALHOU: {result} — verificação pós-execução falhou (arquivo não encontrado no disco)."
                return result
            return wrapper
        return decorator

    def get_tool(self, name: str) -> dict | None:
        return self._tools.get(name)

    def list_tools(self, category: str = None) -> list[dict]:
        if category:
            return [t for t in self._tools.values() if t["category"] == category]
        return list(self._tools.values())

    def build_tools_prompt_section(self, category: str = None) -> str:
        """
        Constrói um bloco de texto formatado com todas as ferramentas disponíveis
        para incluir no prompt do Planner/Scheduler/Executor.
        Inspirado no Procedural Memory do Agent-S.
        """
        tools = self.list_tools(category)
        if not tools:
            tools = self.list_tools()

        lines = []
        for t in tools:
            params_str = ", ".join(
                f"{p['name']}: {p['type']}{' (obrigatório)' if p['required'] else ''}"
                for p in t["params"]
            ) if t["params"] else "sem parâmetros"
            lines.append(f"- {t['name']}({params_str}): {t['description']}")

        return "\n".join(lines)

    def execute(self, name: str, **kwargs) -> str:
        """Executa uma ferramenta registrada com verificação."""
        tool = self._tools.get(name)
        if not tool:
            return f"FALHOU: Ferramenta '{name}' não encontrada no registro."

        try:
            fn = tool["fn"]
            result = fn(**kwargs)

            verify = tool.get("verify")
            if verify:
                sig = inspect.signature(verify)
                filtered_kwargs = {k: v for k, v in kwargs.items()
                                   if k in sig.parameters}
                verified = verify(**filtered_kwargs)
                if not verified:
                    return f"FALHOU: Ação executada mas verificação pós-execução falhou. Resultado: {result}"

            return str(result) if result else "SUCESSO: Operação concluída."
        except Exception as e:
            return f"FALHOU: Erro ao executar {name}: {e}"


# ── Funções de verificação ─────────────────────────────────

from config import WORKSPACE_DIR

def verify_file_exists(filename: str = "", path: str = "") -> bool:
    """Verifica se um arquivo foi realmente criado no disco."""
    WORKSPACE = WORKSPACE_DIR

    if filename:
        fp = WORKSPACE / filename
        if fp.exists() and fp.stat().st_size > 0:
            return True
    if path:
        fp = Path(path)
        if fp.exists():
            return True
    return False


def verify_project_files(project_name: str = "", files: list = None) -> bool:
    """Verifica se os arquivos de um projeto foram realmente criados."""
    WORKSPACE = WORKSPACE_DIR

    if not project_name:
        return False
    project_dir = WORKSPACE / project_name
    if not project_dir.exists():
        return False

    if files:
        for f in files:
            fname = f.get("filename", "") if isinstance(f, dict) else ""
            if fname:
                fp = project_dir / fname
                if not (fp.exists() and fp.stat().st_size > 0):
                    return False
    return True


# Singleton
_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
