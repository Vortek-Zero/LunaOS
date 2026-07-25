#!/usr/bin/env python3
"""
luna_diagnostic.py — Terminal transparente da Luna
Mostra TUDO que acontece internamente: loop ReAct, decisões do Router,
conversas da Crew, tool calls, respostas dos LLMs, memória, etc.

Uso:
    python luna_diagnostic.py          # modo interativo
    python luna_diagnostic.py --test   # teste rápido
"""

import io
import json
import sys
import threading
import time
from contextlib import redirect_stdout
from datetime import datetime

# ── Hooks de diagnóstico ──────────────────────────────────────

_LOGS: list[dict] = []
_INDENT = 0
_CREW_CTX = threading.local()
_CREW_CTX.current_task = None


def _log(kind: str, label: str, detail: str = "", data=None):
    """Registra um evento no log interno e printa formatado."""
    entry = {
        "ts": datetime.now().isoformat(),
        "kind": kind,
        "label": label,
        "detail": detail,
        "data": data,
    }
    _LOGS.append(entry)
    _print_entry(entry)


def _print_entry(entry: dict):
    """Printa uma entrada formatada com cores."""
    kind = entry["kind"]
    label = entry["label"]
    detail = entry["detail"]
    ts = datetime.fromisoformat(entry["ts"]).strftime("%H:%M:%S.%f")[:12]

    colors = {
        "user": "\033[36m",  # ciano
        "assistant": "\033[32m",  # verde
        "system": "\033[33m",  # amarelo
        "tool": "\033[35m",  # magenta
        "crew": "\033[34m",  # azul
        "llm": "\033[31m",  # vermelho
        "memory": "\033[33m",  # amarelo
        "router": "\033[34m",  # azul
        "error": "\033[91m",  # vermelho brilhante
        "internal": "\033[90m",  # cinza
        "step": "\033[93m",  # amarelo brilhante
        "result": "\033[32m",  # verde
    }
    reset = "\033[0m"
    color = colors.get(kind, "\033[37m")

    indent = "  " * _INDENT
    prefix = f"{color}[{ts}][{kind.upper()}]{reset}"
    print(f"{indent}{prefix} {label}")
    if detail:
        for line in detail.split("\n"):
            print(f"{indent}  {color}│{reset} {line}")


# ── Monkey-patch nos módulos da Luna ─────────────────────────


def _patch_llm():
    """Instala hooks no LLMWrapper para ver chamadas e respostas."""
    from brain.llm import get_llm

    llm = get_llm()
    original_generate = llm.generate

    def patched_generate(*args, **kwargs):
        prompt = kwargs.get("prompt") or (args[0] if args else "")
        task_type = kwargs.get("task_type", "default")
        model = kwargs.get("model", "main")
        messages = kwargs.get("messages", [])
        tools = kwargs.get("tools")

        crew_tag = ""
        if hasattr(_CREW_CTX, "current_task") and _CREW_CTX.current_task:
            crew_tag = " [CREW]"

        if messages:
            last_msg = messages[-1].get("content", "") if isinstance(messages[-1], dict) else ""
            prompt_preview = str(last_msg)
        else:
            prompt_preview = str(prompt)

        _log("llm", f"🤖 LLM chamado{crew_tag}: task={task_type}, model={model}", prompt_preview)

        if tools:
            tool_descs = []
            for t in tools:
                fn = t.get("function", {}) if isinstance(t, dict) else getattr(t, "function", {})
                name = fn.get("name", "?")
                desc = fn.get("description", "")[:120]
                params = fn.get("parameters", {})
                param_names = list(params.get("properties", {}).keys()) if isinstance(params, dict) else []
                tool_descs.append(f"    - {name}: {desc}  | params: {param_names}")
            _log("llm", f"  🛠 Tools disponíveis: {len(tools)}", "\n".join(tool_descs))

        start = time.time()
        result = original_generate(*args, **kwargs)
        elapsed = (time.time() - start) * 1000

        if isinstance(result, dict):
            tc = result.get("tool_calls", [])
            if tc:
                names = [
                    t.get("function", {}).get("name", "") if isinstance(t, dict) else getattr(t.function, "name", "")
                    for t in tc
                ]
                details = []
                for t in tc:
                    if isinstance(t, dict):
                        fn = t.get("function", {})
                        details.append(f"    {fn.get('name', '?')}(args={fn.get('arguments', '{}')})")
                    else:
                        details.append(f"    {t.function.name}(args={t.function.arguments})")
                _log(
                    "llm",
                    f"  ⚡ Tool calls retornados ({len(tc)}): {', '.join(names)}",
                    f"({elapsed:.0f}ms)\n" + "\n".join(details),
                )
            else:
                content = result.get("message", {})
                if hasattr(content, "content"):
                    text = content.content or ""
                elif isinstance(content, dict):
                    text = content.get("content", "")
                else:
                    text = str(content)
                _log("llm", f"  💬 Resposta textual ({elapsed:.0f}ms)", text)
        elif isinstance(result, str):
            _log("llm", f"  💬 Resposta string ({elapsed:.0f}ms)", result)
        elif isinstance(result, Exception):
            _log("error", f"  ❌ LLM exception ({elapsed:.0f}ms)", str(result))
        else:
            _log("llm", f"  ❓ Resposta tipo {type(result).__name__} ({elapsed:.0f}ms)", str(result)[:1000])

        return result

    llm.generate = patched_generate
    _log("system", "✓ Hook instalado no LLMWrapper.generate()")


def _patch_agent_tools():
    """Instala hooks no execute_tool_call para ver execução de ferramentas."""
    from brain import agent_tools

    original_execute = agent_tools.execute_tool_call

    def patched_execute(executor, tool_call):
        if isinstance(tool_call, dict):
            fn = tool_call.get("function", {})
            name = fn.get("name", "?")
            args = fn.get("arguments", "{}")
        else:
            name = getattr(tool_call.function, "name", "?")
            args = getattr(tool_call.function, "arguments", "{}")

        try:
            parsed = json.loads(args) if isinstance(args, str) else args
            formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            formatted = str(args)

        _log("tool", f"🛠 {name}", f"args:\n{formatted}")

        start = time.time()
        result = original_execute(executor, tool_call)
        elapsed = (time.time() - start) * 1000

        result_str = str(result)
        if len(result_str) > 20000:
            result_str = result_str[:20000] + f"\n... [truncado, total {len(result_str)} chars]"
        _log("tool", f"  ✅ {name} ({elapsed:.0f}ms)", result_str)
        return result

    agent_tools.execute_tool_call = patched_execute
    _log("system", "✓ Hook instalado em agent_tools.execute_tool_call()")


def _patch_crew():
    """Instala hooks no Crew Mode para ver conversas entre agentes."""
    try:
        from brain import crew

        if hasattr(crew, "run_crew_task"):
            original_crew = crew.run_crew_task

            def patched_crew(task_description):
                _log("crew", "👥 CREW MODE INICIADO", f"Tarefa: {task_description}")
                _CREW_CTX.current_task = task_description
                buf = io.StringIO()
                start = time.time()
                with redirect_stdout(buf):
                    result = original_crew(task_description)
                elapsed = (time.time() - start) * 1000
                _CREW_CTX.current_task = None
                captured = buf.getvalue()
                if captured:
                    _log("crew", "📣 CONVERSA DOS AGENTES:", captured)
                _log("crew", f"✅ CREW CONCLUÍDO ({elapsed:.0f}ms)", str(result))
                return result

            crew.run_crew_task = patched_crew
            _log("system", "✓ Hook instalado em crew.run_crew_task()")
    except Exception as e:
        _log("system", f"⚠ Crew hook não instalado: {e}")


def _patch_router():
    """Instala hooks no Router para ver decisões."""
    try:
        from interaction.router import Router

        original_resolve = Router.resolve

        def patched_resolve(self, goal, context=None):
            _log("router", "🔀 Router: decidindo abordagem", f"goal: {goal}")
            start = time.time()
            result = original_resolve(self, goal, context)
            elapsed = (time.time() - start) * 1000
            status = result.get("status", "?")
            tool_name = result.get("tool", "?")
            plan = result.get("plan", {})
            error = result.get("error", "")
            data = result.get("data", "")

            detail_parts = [f"Status: {status}", f"Ferramenta: {tool_name}"]
            if error:
                detail_parts.append(f"Erro: {error}")
            if plan:
                approaches = plan.get("approaches", [])
                if approaches:
                    detail_parts.append("\n--- PLANO DO CONSELHO ---")
                    for i, ap in enumerate(approaches, 1):
                        detail_parts.append(
                            f"  {i}. tool={ap.get('tool', '?')} | rationale: {ap.get('rationale', '')[:200]}"
                        )
                        params = ap.get("params", {})
                        if params:
                            detail_parts.append(f"     params: {json.dumps(params, ensure_ascii=False)}")
            if data:
                detail_parts.append(f"\nDados: {str(data)[:1000]}")

            _log("router", f"  ✅ Decisão: {status} via {tool_name} ({elapsed:.0f}ms)", "\n".join(detail_parts))
            return result

        Router.resolve = patched_resolve
        _log("system", "✓ Hook instalado em Router.resolve()")
    except Exception as e:
        _log("system", f"⚠ Router hook não instalado: {e}")


def _patch_memory():
    """Instala hooks na memória para ver存取."""
    try:
        from brain.memory import get_memory

        mem = get_memory()
        original_remember = mem.remember

        def patched_remember(fact, category="geral", importance=0.8):
            _log("memory", f"🧠 Memória salva [{category}] (imp: {importance})", str(fact))
            return original_remember(fact, category, importance)

        mem.remember = patched_remember
        _log("system", "✓ Hook instalado em Memory.remember()")
    except Exception as e:
        _log("system", f"⚠ Memory hook não instalado: {e}")


def _patch_core():
    """Instala hooks no LunaCore para ver o fluxo completo."""
    from luna_core import LunaCore

    # Hook no _run_autonomous_loop
    original_loop = LunaCore._run_autonomous_loop

    def patched_loop(self, text, mode="", extra_context=""):
        global _INDENT
        _log("step", f"▶ INÍCIO DO LOOP (mode={mode}, extra={extra_context!r})", text)
        _INDENT += 1
        start = time.time()
        result = original_loop(self, text, mode, extra_context)
        elapsed = (time.time() - start) * 1000
        _INDENT -= 1
        _log("result", f"⏹ RESPOSTA FINAL ({elapsed:.0f}ms)", result)
        return result

    LunaCore._run_autonomous_loop = patched_loop

    # Hook no _handle_internal_command
    original_internal = LunaCore._handle_internal_command

    def patched_internal(self, text):
        result = original_internal(self, text)
        if result[0] is not None:
            _log("internal", f"⚙ Comando interno: {text}", result[0])
        return result

    LunaCore._handle_internal_command = patched_internal

    _log("system", "✓ Hooks instalados no LunaCore")


def _patch_build_context():
    """Hook no _build_context para ver o contexto montado."""
    from luna_core import LunaCore

    original_build = LunaCore._build_context

    def patched_build(self, text, mode="", extra_context=""):
        result = original_build(self, text, mode, extra_context)
        if result:
            _log("system", "📦 Contexto montado", result)
        return result

    LunaCore._build_context = patched_build
    _log("system", "✓ Hook instalado em _build_context()")


# ── Inicialização dos hooks ──────────────────────────────────


def install_all_hooks():
    """Instala todos os hooks de diagnóstico."""
    print("\n" + "=" * 60)
    print("   🔍 LUNA — MODO DIAGNÓSTICO (visão interna total)")
    print("=" * 60)
    print("   Mostrando: LLM calls, tool executions, Crew conversations,")
    print("   Router decisions, memory operations, internal commands,")
    print("   contexto montado, e cada passo do loop ReAct.")
    print("=" * 60 + "\n")

    _patch_llm()
    _patch_agent_tools()
    _patch_crew()
    _patch_router()
    _patch_memory()
    _patch_core()
    _patch_build_context()

    print("\n" + "-" * 60)
    print("   ✅ Todos os hooks instalados. Luna pronta.")
    print("-" * 60 + "\n")


# ── CLI interativa ───────────────────────────────────────────


def run_diagnostic_cli():
    """Terminal interativo com visão interna total."""
    install_all_hooks()

    from luna_core import get_luna

    luna = get_luna()

    print("\n" + "=" * 60)
    print("   🌙 LUNA DIAGNOSTIC — Terminal Interativo")
    print("=" * 60)
    print("   Digite 'sair' para encerrar")
    print("   Digite 'status' para ver estado interno")
    print("   Digite 'log' para ver últimas entradas do log")
    print("=" * 60 + "\n")

    while True:
        try:
            text = input("\033[36mVocê >>> \033[0m").strip()
            if not text:
                continue
            if text.lower() == "sair":
                print("\n[Diagnostic] Encerrando...")
                break
            if text.lower() == "log":
                print(f"\n[Diagnostic] Últimas {min(20, len(_LOGS))} entradas do log:")
                for entry in _LOGS[-20:]:
                    _print_entry(entry)
                continue
            if text.lower() == "stats":
                kinds = {}
                for e in _LOGS:
                    kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
                print(f"\n[Diagnostic] Estatísticas do log ({len(_LOGS)} entradas):")
                for k, v in sorted(kinds.items(), key=lambda x: -x[1]):
                    print(f"  {k}: {v}")
                continue

            _log("user", f"👤 USUÁRIO: {text}")

            start = time.time()
            resposta = luna.process(text)
            elapsed = (time.time() - start) * 1000

            _log("assistant", f"🤖 LUNA: {resposta}", f"({elapsed:.0f}ms)")

        except KeyboardInterrupt:
            print("\n[Diagnostic] Encerrando...")
            break
        except Exception as e:
            _log("error", f"💥 ERRO: {e}")
            import traceback

            traceback.print_exc()


def run_diagnostic_test():
    """
    Raio X completo do sistema Luna.
    Testa todos os subsistemas SEM depender de LLM online:
      1. Boot dos módulos (config, imports)
      2. Verificação de provedores LLM (quais estão ativos vs inativos)
      3. Ferramentas registradas (LUNA_TOOLS)
      4. Memória, Router, Crew, Voice/STT
      5. Comandos internos (status, versão, memória)
      6. Diagnóstico de ferramentas (_run_diagnostics)
      7. (Opcional) Teste de LLM live — apenas reporta, não falha
    """

    print("\n" + "=" * 60)
    print("   🔬 LUNA — RAIO X DO SISTEMA (diagnóstico completo)")
    print("=" * 60)
    print("   Testando todos os subsistemas sem depender de LLM online")
    print("=" * 60 + "\n")

    results: list[tuple[str, bool, str]] = []  # (nome, ok, detalhe)

    def check(name: str, ok: bool, detail: str = ""):
        status = "✅" if ok else "❌"
        results.append((name, ok, detail))
        color = "\033[32m" if ok else "\033[91m"
        reset = "\033[0m"
        print(f"  {status} {color}{name}{reset}: {'OK' if ok else 'FALHOU'}{' — ' + detail if detail else ''}")

    # ── 1. CONFIG & BOOT ──────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("  📦 1. CONFIG & BOOT")
    print(f"{'─' * 60}")

    try:
        import config as cfg

        check("config.py importado", True, f"BASE_DIR={cfg.BASE_DIR}")
    except Exception as e:
        check("config.py importado", False, str(e))

    try:
        import dotenv

        check("python-dotenv", True, "disponível")
    except ImportError:
        check("python-dotenv", False, "pip install python-dotenv")

    try:
        check("WORKSPACE_DIR", cfg.WORKSPACE_DIR.exists(), str(cfg.WORKSPACE_DIR))
    except Exception as e:
        check("WORKSPACE_DIR", False, str(e))

    try:
        check("DATA_DIR", cfg.DATA_DIR.exists(), str(cfg.DATA_DIR))
    except Exception as e:
        check("DATA_DIR", False, str(e))

    env_file = cfg.BASE_DIR / ".env"
    check(".env presente", env_file.exists(), f"{env_file.stat().st_size} bytes" if env_file.exists() else "AUSENTE")

    # ── 2. LLM PROVIDERS ─────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("  🤖 2. PROVEDORES LLM (cascade)")
    print(f"{'─' * 60}")

    try:
        from brain.llm import get_llm

        llm = get_llm()
        check("LLMWrapper instanciado", True)

        providers = llm.get_providers_status()
        active_count = 0
        for p in providers:
            name = p["name"]
            active = p.get("active", False)
            available = p.get("available", False)
            if active:
                active_count += 1
            status_str = "ATIVO" if active else "inativo"
            if active and not available:
                status_str += " (rate-limited)"
            model = p.get("model", "")
            models = p.get("models", {})
            model_str = (
                model if model else ", ".join(f"{k}={v.get('name', '?')}" for k, v in models.items()) if models else ""
            )
            check(f"  Provider: {name}", active, f"{status_str} | {model_str[:80]}")

        check(
            f"Cascade total ({active_count}/{len(providers)} ativos)",
            active_count > 0,
            f"Ordem: {', '.join(cfg.CASCADE_ORDER[:5])}...",
        )
        check(
            "LLM is_ready()",
            llm.is_ready(),
            "pelo menos 1 provider configurado" if llm.is_ready() else "NENHUM provider ativo!",
        )
        check("Crew mode", cfg.CREW_ENABLED, f"Modelos: {list(cfg.CREW_MODELS.keys())[:4]}...")
    except Exception as e:
        check("LLMWrapper", False, str(e))

    # ── 3. TOOLS ──────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("  🛠  3. FERRAMENTAS (LUNA_TOOLS)")
    print(f"{'─' * 60}")

    try:
        from brain.agent_tools import LUNA_TOOLS

        check("LUNA_TOOLS carregadas", True, f"{len(LUNA_TOOLS)} ferramentas registradas")
        tool_names = [t.get("function", {}).get("name", "?") for t in LUNA_TOOLS]
        # Mostra em colunas
        cols = 4
        for i in range(0, len(tool_names), cols):
            row = tool_names[i : i + cols]
            print(f"    │ {', '.join(row)}")
    except Exception as e:
        check("LUNA_TOOLS", False, str(e))

    # ── 4. MEMÓRIA ────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("  🧠 4. MEMÓRIA")
    print(f"{'─' * 60}")

    try:
        from brain.memory import get_memory

        mem = get_memory()
        stats = mem.stats()
        check("Memory carregada", True, stats[:80])
    except Exception as e:
        check("Memory", False, str(e))

    try:
        from brain.memory_rag import MemoryRAG

        rag = MemoryRAG()
        check("MemoryRAG (ChromaDB)", rag is not None, "instância criada")
    except Exception as e:
        check("MemoryRAG (ChromaDB)", False, str(e))

    try:
        from brain.episodic_memory import get_episodic_memory

        ep = get_episodic_memory()
        check("Episodic Memory", ep is not None, "instância criada")
    except Exception as e:
        check("Episodic Memory", False, str(e))

    try:
        from learning.strategy_memory import StrategyMemory

        sm = StrategyMemory()
        check("Strategy Memory", sm is not None, "instância criada")
    except Exception as e:
        check("Strategy Memory", False, str(e))

    # ── 5. INTERACTION ENGINE ─────────────────────────────────
    print(f"\n{'─' * 60}")
    print("  🔀 5. INTERACTION ENGINE")
    print(f"{'─' * 60}")

    try:
        from interaction.router import Router

        Router()
        check("Router instanciado", True)
    except Exception as e:
        check("Router", False, str(e))

    try:
        from interaction.registry import ToolRegistry

        ToolRegistry()
        check("ToolRegistry", True, "registro de ferramentas acessível")
    except Exception as e:
        check("ToolRegistry", False, str(e))

    try:
        from interaction.verifier import Verifier

        v = Verifier()
        check("Verifier", v is not None, "instância criada")
    except Exception as e:
        check("Verifier", False, str(e))

    # ── 6. VOICE ──────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("  🎤 6. VOICE (TTS + STT)")
    print(f"{'─' * 60}")

    try:
        from voice.tts import get_tts

        tts = get_tts()
        check("TTS engine", tts is not None, f"prioridade: {', '.join(cfg.TTS_PRIORITY[:3])}")
    except Exception as e:
        check("TTS engine", False, str(e))

    try:
        from voice.stt import STTEngine

        stt = STTEngine()
        avail = stt.is_available()
        check("STT engine", True, f"microfone={'disponível' if avail else 'indisponível'}")
    except Exception as e:
        check("STT engine", False, str(e))

    # ── 7. LUNA CORE — COMANDOS INTERNOS ──────────────────────
    print(f"\n{'─' * 60}")
    print("  🌙 7. LUNA CORE (comandos internos — sem LLM)")
    print(f"{'─' * 60}")

    try:
        from luna_core import get_luna

        luna = get_luna()
        check("LunaCore instanciado", True)

        # Testa comandos internos que NÃO usam LLM
        internal_tests = [
            ("status", "LLM:"),
            ("memoria", None),
            ("versao", "Luna v"),
            ("performance", "Tempo"),
        ]
        for cmd, expected in internal_tests:
            try:
                start = time.time()
                resp = luna.process(cmd)
                elapsed = (time.time() - start) * 1000
                ok = bool(resp) and (expected is None or expected in resp)
                check(f"  Cmd '{cmd}'", ok, f"({elapsed:.0f}ms) {resp[:80]}" if resp else "sem resposta")
            except Exception as e:
                check(f"  Cmd '{cmd}'", False, str(e))
    except Exception as e:
        check("LunaCore", False, str(e))

    # ── 8. DIAGNÓSTICO DE FERRAMENTAS ─────────────────────────
    print(f"\n{'─' * 60}")
    print("  🧪 8. DIAGNÓSTICO DE FERRAMENTAS (agent_tools)")
    print(f"{'─' * 60}")

    try:
        from brain.agent_tools import _run_diagnostics

        diag_result = _run_diagnostics()
        lines = diag_result.strip().split("\n")
        ok_count = sum(1 for line in lines if line.startswith("✅"))
        fail_count = sum(1 for line in lines if line.startswith("❌"))
        check("Ferramentas testadas", ok_count > 0, f"{ok_count} OK, {fail_count} falhas")
        # Mostra apenas falhas
        for line in lines:
            if line.startswith("❌"):
                print(f"    \033[91m{line}\033[0m")
    except Exception as e:
        check("_run_diagnostics()", False, str(e))

    # ── 9. TESTE LLM LIVE (bônus) ─────────────────────────────
    print(f"\n{'─' * 60}")
    print("  ⚡ 9. TESTE LLM LIVE (bônus — não bloqueia diagnóstico)")
    print(f"{'─' * 60}")

    try:
        llm = get_llm()
        if llm.is_ready():
            start = time.time()
            resp = llm.generate(prompt="Responda apenas 'ok' em uma palavra.", task_type="command")
            elapsed = (time.time() - start) * 1000
            is_ok = isinstance(resp, str) and len(resp) < 200 and "indisponível" not in resp.lower()
            check("LLM resposta live", is_ok, f"({elapsed:.0f}ms) {str(resp)[:60]}")
        else:
            check("LLM resposta live", False, "nenhum provider ativo — pule esta etapa")
    except Exception as e:
        check("LLM resposta live", False, f"erro: {e}")

    # ── RESUMO FINAL ──────────────────────────────────────────
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed

    print(f"\n{'=' * 60}")
    if failed == 0:
        print(f"   ✅ RAIO X COMPLETO — {passed}/{total} testes passaram")
    else:
        print(f"   ⚠️  RAIO X COMPLETO — {passed}/{total} OK, {failed} falha(s)")
    print(f"{'=' * 60}")

    if failed > 0:
        print("\n  Falhas encontradas:")
        for name, ok, detail in results:
            if not ok:
                print(f"    ❌ {name}: {detail}")

    # ── 10. DEMONSTRAÇÃO REAL (MÁQUINA TRABALHANDO) ───────────
    print(f"\n{'─' * 60}")
    print("  🔥 10. ENGRENAGENS GIRANDO (Teste Real Completo sem UI)")
    print(f"{'─' * 60}")

    print("\nIniciando simulação de interação real...")

    # Ativa os hooks visuais
    install_all_hooks()

    try:
        from luna_core import get_luna

        luna = get_luna()

        prompt = "Consulte o clima atual no Rio de Janeiro e me retorne uma breve frase."
        print(f"\n👤 PROMPT: {prompt}\n")

        start = time.time()
        # process já loga internamente graças ao install_all_hooks()
        final_answer = luna.process(prompt)
        elapsed = time.time() - start

        print(f"\n🤖 RESPOSTA FINAL ({elapsed:.1f}s):\n{final_answer}\n")

    except Exception as e:
        print(f"Erro durante a simulação: {e}")

    print()


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_diagnostic_test()
    else:
        run_diagnostic_cli()
