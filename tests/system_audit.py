#!/usr/bin/env python3
"""
Auditoria do sistema Luna — dependências, ferramentas, rotas do pipeline.
Uso: python tests/system_audit.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def ok(msg: str) -> str:
    return f"  ✓ {msg}"


def fail(msg: str) -> str:
    return f"  ✗ {msg}"


def warn(msg: str) -> str:
    return f"  ⚠ {msg}"


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def check_bin(name: str) -> bool:
    return shutil.which(name) is not None


def audit_pipeline_bypasses() -> list[str]:
    """Lê luna_core e lista fases que ainda podem pular o agente completo."""
    core = (ROOT / "luna_core.py").read_text(encoding="utf-8")
    tools_src = (ROOT / "brain" / "agent_tools.py").read_text(encoding="utf-8")
    lines = []
    for label, pattern in [
        ("Meta/admin (sem LLM)", r"_handle_internal_command"),
        ("Diálogo guiado", r"_dialog_step"),
        ("Escritor (LLM dedicado)", r"_run_writer_stream|is_writing_request"),
        ("Agente FASE 5", r"FASE 5"),
        ("Safety filter", r"check_safety"),
    ]:
        found = bool(re.search(pattern, core))
        lines.append(ok(f"{label}: {'presente' if found else 'AUSENTE'}") if found else fail(f"{label}: ausente"))
    # FASE 3 dicionário sem LLM
    if re.search(r"FASE 3.*Dicionário", core):
        lines.append(fail("FASE 3 dicionário sem LLM ainda no código"))
    else:
        lines.append(ok("FASE 3 dicionário bypass removido"))
    if re.search(r"_execute_action", core):
        lines.append(fail("_execute_action legacy ainda presente"))
    else:
        lines.append(ok("_execute_action legacy removido"))
    if re.search(r'"name":\s*"run_luna_command"', tools_src):
        lines.append(fail("run_luna_command ainda nas tools"))
    else:
        lines.append(ok("run_luna_command removido das tools"))
    return lines


def audit_tools() -> list[str]:
    lines = []
    try:
        from brain.agent_tools import LUNA_TOOLS, execute_tool_call
        names = sorted(
            t["function"]["name"]
            for t in LUNA_TOOLS
            if t.get("type") == "function"
        )
        lines.append(ok(f"{len(names)} ferramentas nativas registradas"))
        for n in names:
            lines.append(f"      · {n}")
        _ = execute_tool_call  # noqa: F841
    except Exception as e:
        lines.append(fail(f"agent_tools: {e}"))
    return lines


def audit_llm() -> list[str]:
    lines = []
    try:
        from luna_core import LunaCore
        llm = LunaCore()._llm
        ready = llm.is_ready()
        native = llm.supports_native_tools()
        lines.append(ok("LLM pronto") if ready else fail("LLM offline (Ollama/Groq/OpenRouter)"))
        lines.append(ok("Tool calls nativos") if native else warn("Sem tool calls nativos — fallback JSON"))
        from config import MODELS, GROQ_API_KEY
        lines.append(ok(f"Modelo main: {MODELS.get('main', '?')}"))
        if GROQ_API_KEY:
            lines.append(ok("GROQ_API_KEY definida"))
        else:
            lines.append(warn("GROQ_API_KEY vazia"))
    except Exception as e:
        lines.append(fail(f"LLM: {e}"))
    return lines


def audit_env() -> list[str]:
    lines = []
    from config import TAVILY_API_KEY, GROQ_API_KEY, OLLAMA_BASE_URL
    lines.append(ok(f"Ollama: {OLLAMA_BASE_URL}") if OLLAMA_BASE_URL else warn("Ollama URL"))
    lines.append(ok("Tavily") if TAVILY_API_KEY else warn("TAVILY_API_KEY ausente — search_web limitado"))
    token = ROOT / "token.json"
    creds = ROOT / "credentials.json"
    if token.exists():
        lines.append(ok("Google token.json presente"))
    else:
        lines.append(warn("token.json ausente — Google Workspace indisponível"))
    if creds.exists():
        lines.append(ok("credentials.json presente"))
    return lines


def audit_desktop_deps() -> list[str]:
    bins = [
        ("wmctrl", "focar janelas"),
        ("xdotool", "cliques/teclado X11"),
        ("gio", "abrir apps GNOME"),
        ("grim", "screenshot Wayland"),
        ("scrot", "screenshot X11"),
        ("nautilus", "abrir pastas"),
        ("ydotool", "clique/teclado Wayland"),
        ("wtype", "digitar Wayland"),
    ]
    lines = []
    for b, desc in bins:
        if check_bin(b):
            lines.append(ok(f"{b} — {desc}"))
        else:
            lines.append(warn(f"{b} ausente — {desc}"))
    session = os.environ.get("XDG_SESSION_TYPE", "?")
    lines.append(ok(f"Sessão: {session}") if session != "?" else warn("XDG_SESSION_TYPE desconhecido"))
    return lines


def audit_sample_routes() -> list[str]:
    """Simula quais entradas vão para meta vs agente (sem chamar LLM)."""
    lines = []
    try:
        from luna_core import LunaCore
        luna = LunaCore()
    except Exception as e:
        return [fail(f"Não instanciou LunaCore: {e}")]

    samples = [
        ("status", "meta"),
        ("limpa cache", "meta"),
        ("abra o firefox", "agente"),
        ("tira um print", "agente"),
        ("o que significa efêmero", "agente"),
        ("timer de 5 minutos", "agente"),
        ("pesquisa python", "agente"),
        ("mata o firefox", "agente"),
    ]
    for text, expected in samples:
        internal, _ = luna._handle_internal_command(text)
        got = "meta" if internal is not None else "agente"
        if got == expected:
            lines.append(ok(f'"{text}" → {got}'))
        else:
            lines.append(fail(f'"{text}" → {got} (esperado {expected})'))
    return lines


def main() -> int:
    print("Luna — auditoria de sistema")
    all_lines: list[str] = []

    section("Pipeline / bypasses")
    for ln in audit_pipeline_bypasses():
        print(ln)
        all_lines.append(ln)

    section("LLM")
    for ln in audit_llm():
        print(ln)

    section("Variáveis / integrações")
    for ln in audit_env():
        print(ln)

    section("Desktop (binários)")
    for ln in audit_desktop_deps():
        print(ln)

    section("Ferramentas do agente")
    for ln in audit_tools():
        print(ln)

    section("Roteamento meta vs agente (amostra)")
    for ln in audit_sample_routes():
        print(ln)

    fails = sum(1 for ln in all_lines if ln.strip().startswith("✗"))
    print(f"\n{'=' * 60}\nResumo: {fails} falha(s) crítica(s) na auditoria estática")
    print("Guia completo: docs/LUNA_CAPABILITIES_AND_BUGS.md")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
