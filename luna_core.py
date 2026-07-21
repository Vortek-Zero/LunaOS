#!/usr/bin/env python3
"""
luna_core.py — Cérebro central da Luna (Singleton)
"""

import ast
import sys

# 🚨 Monkey patch para compatibilidade com Python 3.14+ (evita erros em dependências legadas como CrewAI)
if sys.version_info >= (3, 14):
    if not hasattr(ast, "NameConstant"):
        ast.NameConstant = ast.Constant
    if not hasattr(ast, "Num"):
        ast.Num = ast.Constant
    if not hasattr(ast, "Str"):
        ast.Str = ast.Constant

import json
import re
import threading
import time
from pathlib import Path

# ── Módulos internos ──────────────────────────────────────────
import config
from actions.executor import get_executor
from actions.writer import get_writer
from brain.daily_routine import get_activity_logger, get_background_worker, get_routine_manager
from brain.dictionary import get_dictionary
from brain.llm import MODELS, get_llm
from brain.loop_guard import LoopGuard
from brain.memory import get_memory
from brain.query_complexity import classify_query
from brain.reflection import OutputValidator, VerificationSystem
from brain.trace_logger import get_trace_logger
from interaction.registry import get_registry
from interaction.router import Router
from interaction.verifier import Verifier
from performance_cache import PerformanceMonitor, SmartCache
from vision.screen import get_vision
from voice.stt import get_stt
from voice.tts import get_tts

# ── Personalidade da Luna ─────────────────────────────────────
PERSONALITY_FILE = Path(__file__).parent / "config" / "personality.json"
USER_PROFILE_FILE = Path(__file__).parent / "config" / "user_profile.json"

# Comandos locais — não disparam fact-check web nem extração de memória
_LOCAL_ACTION_KEYWORDS = (
    "print",
    "screenshot",
    "captura",
    "tira um print",
    "tira print",
    "timer",
    "toca",
    "abre",
    "fecha",
    "clica",
    "digita",
    "whatsapp",
    "manda",
    "envia",
    "pesquisa",
    "busca",
    "lista",
    "listar",
    "lembret",
    "nota",
    "luz",
    "volume",
    "workspace",
    "mata",
    "processo",
    "brilho",
    "copia",
    "clipboard",
    "arquivo",
    "arquivos",
    "pasta",
    "pastas",
    "home",
    "diretório",
    "diretorio",
    "print da tela",
)


def _is_local_action(text: str) -> bool:
    tl = text.lower()
    return any(k in tl for k in _LOCAL_ACTION_KEYWORDS)


def _tool_progress_label(name: str, raw_args) -> str:
    """Rótulo amigável para UI durante execução de ferramentas."""
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
    except Exception:
        args = {}
    labels = {
        "open_app": lambda a: f"Abrindo {a.get('app_name', 'aplicativo')}...",
        "run_bash_command": lambda a: f"Executando: {(a.get('command') or '')[:48]}...",
        "run_terminal_command": lambda a: f"Terminal: {(a.get('command') or '')[:48]}...",
        "open_url": lambda a: f"Abrindo {a.get('url', 'link')}...",
        "search_web": lambda a: f"Pesquisando: {a.get('query', '')[:40]}...",
        "see_screen": lambda a: "Analisando a tela...",
        "click_on_screen": lambda a: f"Clicando em '{a.get('target', '...')}'...",
        "click_web_result": lambda a: f"Abrindo {a.get('index', 0) + 1}º resultado web...",
        "desktop_type": lambda a: "Digitando na tela...",
        "desktop_hotkey": lambda a: f"Atalho: {a.get('keys', '')}...",
        "filesystem": lambda a: f"Arquivos: {a.get('action', '')}...",
        "whatsapp_action": lambda a: f"WhatsApp: {a.get('action', '')}...",
        "system_control": lambda a: f"Sistema: {a.get('action', '')}...",
        "control_window": lambda a: f"Janela: {a.get('action', '')}...",
        "kill_process": lambda a: f"Encerrando {a.get('name') or a.get('pid', 'processo')}...",
        "image_generate": lambda a: f"Gerando imagem: {a.get('prompt', '')[:40]}...",
    }
    fn = labels.get(name)
    if fn:
        return fn(args)
    return f"Executando {name.replace('_', ' ')}..."


def _sanitize_user_response(text: str) -> str:
    """Remove JSON/tool_calls vazados pelo LLM — nunca mostrar ao usuário."""
    if not text:
        return text
    t = text.strip()

    if ("tool_calls" in t.lower() or '"action"' in t) and (
        re.search(r'"tool_calls"\s*:', t) or re.search(r'^\s*\{\s*"action"', t)
    ):
        inner = re.search(r'"response"\s*:\s*"([^"]*)"', t)
        if inner:
            return _sanitize_user_response(inner.group(1))
        return ""

    if t.startswith("{"):
        try:
            data = json.loads(t)
            if isinstance(data, dict):
                if data.get("response"):
                    return _sanitize_user_response(str(data["response"]))
                if data.get("tool_calls") or data.get("action"):
                    return ""
        except json.JSONDecodeError:
            pass

    # Remove blocos de função vazados como `create_project("x", [...])`
    t = re.sub(r"`\w+\([^`]*\)`", "", t)
    # Remove checkmarks/emojis de "passo concluído"
    t = re.sub(r"✅.*", "", t)
    # Remove **Passo N:** headings
    t = re.sub(r"\*{1,2}Passo \d+.*?\*{1,2}", "", t)

    t = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", t, flags=re.DOTALL).strip()
    return t.strip() or "Pronto."


_TEXT_FUNCTIONS = {
    "write_code": ("filename", "content"),
    "create_project": ("project_name", "files"),
    "open_app": ("app",),
    "open_url": ("url",),
    "search_web": ("query",),
    "run_bash_command": ("command",),
    "get_weather": ("city",),
    "system_control": ("action", "command"),
    "document_services": ("action", "data", "content", "filename"),
    "set_timer": ("action", "minutes", "seconds", "name"),
    "manage_reminder": ("action", "message", "when"),
    "manage_notes": ("action", "content", "query", "index"),
    "google_services": ("action", "service", "query", "date", "max_results"),
    "trigger_n8n_workflow": ("path", "data"),
    "agno_run": ("task",),
    "save_skill": ("name", "description", "steps"),
    "ui_click": ("target",),
    "ui_type": ("text",),
    "ui_key": ("key",),
    "ui_scroll": ("direction",),
    "see_screen": (),
    "self_diagnostic": (),
    "image_generate": ("prompt", "size"),
}


def _split_function_args(text: str) -> list:
    """Divide argumentos por vírgula respeitando aspas e colchetes."""
    args, current = [], []
    depth = bracket_depth = 0
    in_str = False
    quote = None
    for ch in text:
        if ch in ('"', "'"):
            if not in_str:
                in_str, quote = True, ch
            elif ch == quote:
                in_str = False
            current.append(ch)
        elif ch == "(" and not in_str:
            depth += 1
            current.append(ch)
        elif ch == ")" and not in_str:
            depth -= 1
            current.append(ch)
        elif ch == "[" and not in_str:
            bracket_depth += 1
            current.append(ch)
        elif ch == "]" and not in_str:
            bracket_depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0 and bracket_depth == 0 and not in_str:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        args.append("".join(current).strip())
    return args


def _parse_arg_value(arg: str):
    """Converte string de argumento textual para valor Python."""
    arg = arg.strip()
    if arg.startswith('"') and arg.endswith('"') and len(arg) >= 2:
        return arg[1:-1]
    if arg.startswith("'") and arg.endswith("'") and len(arg) >= 2:
        return arg[1:-1]
    if arg.startswith("[") and arg.endswith("]"):
        try:
            return json.loads(arg)
        except json.JSONDecodeError:
            items = re.findall(r'"([^"]*)"', arg)
            return items if items else arg
    return arg


def _parse_function_block(block: str) -> dict | None:
    """Parseia uma chamada de função tipo create_project('nome', [files])."""
    block = block.strip().strip("`").strip()
    m = re.match(r"(\w+)\s*\((.*)\)\s*$", block, re.DOTALL)
    if not m:
        return None
    name, rest = m.group(1), m.group(2)
    param_names = _TEXT_FUNCTIONS.get(name)
    if param_names is None:
        return None

    # write_code: extrai filename + content (conteúdo pode ter qualquer caractere)
    if name == "write_code" and len(param_names) >= 2:
        m2 = re.match(r'\s*"([^"]*)"\s*,\s*(.*)', rest, re.DOTALL)
        if m2:
            filename, content_raw = m2.group(1), m2.group(2).strip()
            if content_raw.startswith('"') and content_raw.endswith('"'):
                return {"name": name, "arguments": {"filename": filename, "content": content_raw[1:-1]}}
            if content_raw.startswith("'") and content_raw.endswith("'"):
                return {"name": name, "arguments": {"filename": filename, "content": content_raw[1:-1]}}

    # create_project: extrai project_name + files (lista de strings → objetos)
    if name == "create_project" and len(param_names) >= 2:
        m2 = re.match(r'\s*"([^"]*)"\s*,\s*(.*)', rest, re.DOTALL)
        if m2:
            project_name, files_raw = m2.group(1), m2.group(2).strip()
            try:
                files_list = json.loads(files_raw)
            except json.JSONDecodeError:
                items = re.findall(r'"([^"]*)"', files_raw)
                files_list = [{"filename": f, "content": ""} for f in items] if items else None
            if isinstance(files_list, list):
                if files_list and isinstance(files_list[0], str):
                    files_list = [{"filename": f, "content": ""} for f in files_list]
                return {"name": name, "arguments": {"project_name": project_name, "files": files_list}}

    # Genérico: divide por vírgula e mapeia param names
    args = _split_function_args(rest)
    kwargs = {}
    for i, a in enumerate(args):
        if i >= len(param_names):
            break
        kwargs[param_names[i]] = _parse_arg_value(a)
    return {"name": name, "arguments": kwargs} if kwargs else None


def _extract_functions_from_text(text: str) -> list:
    """Varre o texto procurando chamadas de função (dentro ou fora de backticks)."""
    results = []

    # 1) Blocos inline com backticks: `função(args)`
    for m in re.finditer(r"`([^`]+)`", text):
        call = _parse_function_block(m.group(1))
        if call:
            results.append(call)
    if results:
        return _normalize_text_calls(results)

    # 2) Chamadas soltas no texto (sem backticks)
    for m in re.finditer(r"(?<![`\w])(\w+)\s*\(", text):
        name = m.group(1)
        if name not in _TEXT_FUNCTIONS:
            continue
        paren_start = m.end() - 1
        depth, end = 0, -1
        for i, ch in enumerate(text[paren_start:]):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = paren_start + i + 1
                    break
        if end > 0:
            call = _parse_function_block(text[m.start() : end])
            if call:
                results.append(call)
    return _normalize_text_calls(results) if results else []


def _normalize_text_calls(calls: list) -> list:
    """Converte dicts {name, arguments} para tool_call format."""
    normalized = []
    ts = int(time.time())
    for idx, c in enumerate(calls):
        if not c or "name" not in c or "arguments" not in c:
            continue
        normalized.append(
            {
                "id": f"parsed_{ts}_{idx}_{c['name']}",
                "type": "function",
                "function": {
                    "name": c["name"],
                    "arguments": json.dumps(c["arguments"], ensure_ascii=False),
                },
            }
        )
    return normalized


def _extract_tool_calls_from_text(raw: str) -> list:
    """Recupera tool_calls quando o modelo vaza JSON/função no texto."""
    if not raw:
        return []

    # 1) JSON com tool_calls (formato existente)
    if "tool_calls" in raw:
        try:
            m = re.search(r"\{.*\"tool_calls\".*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                calls = data.get("tool_calls") or []
                normalized = []
                for tc in calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name")
                    if name:
                        normalized.append(
                            {
                                "id": tc.get("id", f"parsed_{int(time.time())}"),
                                "type": "function",
                                "function": {"name": name, "arguments": fn.get("arguments", "{}")},
                            }
                        )
                if normalized:
                    return normalized
        except Exception:
            pass
        # Fallback: JSON malformado
        names = re.findall(r'"name"\s*:\s*"(\w+)"', raw)
        if names:
            args_m = re.search(r'"arguments"\s*:\s*"(\{.*?\})"', raw)
            args = args_m.group(1).replace('\\"', '"') if args_m else "{}"
            return [
                {
                    "id": f"parsed_{int(time.time())}",
                    "type": "function",
                    "function": {"name": names[0], "arguments": args},
                }
            ]

    # 2) Funções no texto: função("arg1", "arg2") ou plano **Passo N:** `função(...)`
    return _extract_functions_from_text(raw)


def _parse_tc_args(tool_call) -> dict:
    """Extrai argumentos de um tool_call (dict ou objeto)."""
    if isinstance(tool_call, dict):
        raw = tool_call.get("function", {}).get("arguments", {})
    else:
        raw = tool_call.function.arguments
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _agent_result(base: dict, tools_executed: int = 0) -> dict:
    """Normaliza retorno do agente; evita re-execução legacy após ferramentas."""
    out = dict(base)
    out["tools_executed"] = tools_executed
    if tools_executed > 0:
        out["action"] = "conversar"
    return out


# SYSTEM_PROMPT removido — é dead code. O prompt real é montado em _run_autonomous_loop.
class LunaCore:
    """
    Sistema central da Luna.
    Use `get_luna()` para obter a instância singleton.
    """

    def __init__(self, test_mode: bool = False):
        print("\n[Luna] Iniciando sistema...")
        self.test_mode = test_mode

        # Módulos
        self._llm = get_llm()
        self._memory = get_memory()
        self._tts = get_tts()
        self._stt = get_stt()
        self._executor = get_executor()
        self._executor._luna_core = self  # referência para tools acessarem LunaCore
        self._writer = get_writer()
        self._dictionary = get_dictionary()
        self._vision = get_vision()

        # Barramento de Eventos (Event Bus) e Memória Hierárquica
        try:
            from brain.event_bus import get_event_bus
            from brain.hierarchical_memory import HierarchicalMemory

            self._event_bus = get_event_bus()
            self._hierarchical_memory = HierarchicalMemory(self._memory)
            print("[Luna] ✓ Barramento de Eventos (EventBus) e Memória Hierárquica carregados.")
        except Exception as e:
            print(f"[Luna] ⚠️ Erro ao inicializar EventBus ou Memória Hierárquica: {e}")

        # Cache + Performance
        self._cache = SmartCache()
        self._perf = PerformanceMonitor()
        self._last_was_cached = False
        self.last_metrics = {"time_ms": 0, "model": "N/A", "tails": 0}
        self.in_conversation_mode = False
        self.user_profile = self._load_user_profile()
        self._pending_click: str | None = None  # alvo de clique aguardando app

        # Seletor de modelo: "main" (médio 3B) ou "heavy" (alto 7B)
        self._writing_model: str = "main"  # default: médio

        # Interaction Engine (Router + Registry + Verifier)
        self._interaction_router = Router(llm=self._llm)
        self._interaction_verifier = Verifier()
        print(f"[Luna] ✓ Interaction Engine: {len(get_registry().all_tools())} ferramentas registradas")

        # Estado
        self.processing = False
        self.current_action: str | None = None
        self._progress_callback = None
        self._expected_tool_steps = 1
        self._max_steps = getattr(config, "MAX_STEPS", 15)
        self._lock = threading.Lock()
        self._dialog: dict = {}  # estado do diálogo guiado atual
        self._confirm_edit_callback = None  # chamado para confirmar edições de arquivo
        self._code_mode_result = None  # último código escrito via write_code em modo code

        # Carrega personalidade
        self._persona_name = self._load_persona()

        # Limpa cache expirado ao iniciar
        expired = self._cache.clear_expired()
        if expired > 0:
            print(f"[Luna] Cache: {expired} entradas expiradas removidas")

        cache_count = len(self._cache.cache.get("entries", {}))
        print(f"[Luna] ✓ Sistema pronto. Modelos: {', '.join(MODELS.values())}")
        print(f"[Luna] ✓ Cache: {cache_count} entradas | Memória: {self._memory.stats()}")

        # Sistema de Rotinas Diárias + Worker Proativo
        self._routine_manager = get_routine_manager(self)
        self._activity_logger = get_activity_logger()
        self._background_worker = get_background_worker(self)
        self._background_worker.start()
        print("[Luna] ✓ Rotinas diárias e worker proativo ativos.")

        # Loop Guard + Trace Logger (OpenJarvis)
        self._loop_guard = LoopGuard(
            max_identical_calls=3,
            ping_pong_window=6,
            poll_tool_budget=5,
        )
        self._trace_logger = get_trace_logger()
        print("[Luna] ✓ Loop Guard e Trace Logger ativos.")

    def _load_persona(self) -> str:
        try:
            data = json.loads(PERSONALITY_FILE.read_text(encoding="utf-8"))
            self._personality_data = data
            return data.get("identity", {}).get("name", "Luna")
        except Exception:
            self._personality_data = {}
            return "Luna"

    def _load_user_profile(self) -> dict:
        try:
            if USER_PROFILE_FILE.exists():
                return json.loads(USER_PROFILE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Luna] Erro ao carregar user_profile.json: {e}")
        return {}

    def set_confirm_callback(self, callback):
        """Define callback para confirmação de edições (ex: via WebSocket/API)."""
        self._confirm_edit_callback = callback

    def select_model(self, mode: str) -> str:
        """
        Seleciona o modelo de escrita criativa/texto.
        mode: 'medium' (rápido) ou 'high' (profundo)
        Retorna mensagem de confirmação.
        """
        if mode == "high":
            self._writing_model = "heavy"
            return "★ Modelo ALTO (profundo) selecionado — gpt-5.2, o3, claude-sonnet-5."
        else:
            self._writing_model = "main"
            return "● ModelO MÉDIO (rápido) selecionado — o3, grok-3, gpt-4o-mini."

    def get_model_mode(self) -> str:
        """Retorna o modo atual: 'medium' ou 'high'."""
        return "high" if self._writing_model == "heavy" else "medium"

    def set_cascade(self, order: str) -> str:
        """Altera a ordem dos provedores LLM dinamicamente.
        Ex: 'puter,groq,gemini' ou 'groq,mistral'"""
        before = self._llm.get_cascade_order()
        self._llm.set_cascade_order(order)
        after = self._llm.get_cascade_order()
        return f"Cascade alterado: {', '.join(before)} → {', '.join(after)}"

    def get_cascade(self) -> str:
        return ", ".join(self._llm.get_cascade_order())

    def set_crew_mode(self, enabled: bool) -> str:
        return self._llm.set_crew_mode(enabled)

    # ── Processamento principal ───────────────────────────────

    def _emit_progress(self, event_type: str, **data) -> None:
        """Emite evento de progresso para SSE/UI (thinking, tool_start, tool_done)."""
        label = data.get("label") or data.get("name") or event_type
        self.current_action = label
        if self._progress_callback:
            from contextlib import suppress

            with suppress(Exception):
                self._progress_callback({"type": event_type, "label": label, **data})

    def process(self, text: str, progress_callback=None, mode: str = "", extra_context: str = "") -> str:
        """
        Processa uma entrada do usuário em um loop autônomo (ReAct).
        Pipeline: texto → [Plano → Ações → Observação] → Resposta Final
        mode: "code", "write", "joy", "voice", ou "" (normal)
        extra_context: contexto adicional específico do modo (ex: código atual, estado do jogo)
        """
        if not text or not text.strip():
            return ""

        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
        text = re.sub(r"[ \t]+", " ", text).strip()
        if not text:
            return ""

        from brain.safety import check_safety

        safety_response = check_safety(text)
        if safety_response:
            return safety_response

        # Registra atividade do usuário para aprendizado de padrões
        from contextlib import suppress

        with suppress(Exception):
            self._activity_logger.log("user_input", text[:100])

        if mode == "code":
            self._code_mode_result = None

        with self._lock:
            self.processing = True
            self._progress_callback = progress_callback
            try:
                response = self._run_autonomous_loop(text, mode=mode, extra_context=extra_context)

                # 4. Atualiza perfil do usuário assincronamente a partir da fala
                try:
                    from brain.user_model import get_user_model

                    get_user_model().update_from_text(text)
                except Exception as e:
                    print(f"[Core] Erro ao atualizar perfil do usuário: {e}")

                # 5. Registra o episódio ocorrido na memória episódica
                try:
                    from brain.episodic_memory import get_episodic_memory

                    get_episodic_memory().log_episode(
                        text=text,
                        response_summary=response,
                        action_type="conversa" if mode == "" else mode,
                        outcome="sucesso" if response and "erro" not in response.lower() else "falha",
                    )
                except Exception as e:
                    print(f"[Core] Erro ao registrar episódio: {e}")

                return response
            except Exception as e:
                print(f"[Luna] Erro no loop autônomo: {e}")
                import traceback

                traceback.print_exc()
                return "Ocorreu um erro interno. Tente novamente."
            finally:
                self.processing = False
                self.current_action = None
                self._progress_callback = None

    def process_stream(self, text: str):
        """Processa com streaming — retorna a resposta completa (placeholder para streaming real)."""
        if not text or not text.strip():
            return
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
        text = re.sub(r"[ \t]+", " ", text).strip()
        if not text:
            return

        from brain.safety import check_safety

        safety_response = check_safety(text)
        if safety_response:
            yield safety_response
            return

        with self._lock:
            self.processing = True
            try:
                response = self._run_autonomous_loop(text)
                yield response
            except Exception as e:
                yield f"Erro: {e}"
            finally:
                self.processing = False

    def _run_autonomous_loop(self, text: str, mode: str = "", extra_context: str = "") -> str:
        """
        Loop ReAct direto + Interaction Engine (Router).
        Para tarefas de sistema/navegador/API, usa o Router com conselho de IAs.
        Para conversa/código/escrita, usa o loop ReAct com tools nativas.
        """
        timer_start = self._perf.start_timer()
        max_steps = getattr(self, "_max_steps", 15)
        loop_blocked = False

        # ══ Trace Logger: inicia gravação da interação ══
        self._trace_logger.start_trace(text)
        self._loop_guard.reset()

        # ══ FASE -1: Diálogo guiado (formulários) ══
        if hasattr(self, "_dialog") and self._dialog:
            result = self._dialog_step(text)
            if result:
                return result

        # ══ Meta/admin local ══
        internal, conv_signal = self._handle_internal_command(text)
        if internal is not None:
            self._trace_logger.finish_trace("internal_command", internal)
            return internal

        # Inicia contexto
        context = self._build_context(text, mode, extra_context)

        # Classifica consulta (OpenJarvis) — só para metadados, não para decisão
        query_info = classify_query(text)
        self._trace_logger.set_model(query_info.get("model_tier", "main"))

        # ══ PLANEJAMENTO EXPLICÍTO (Planner) ══
        plan_str = ""
        is_complex = (
            query_info.get("complexity") == "high"
            or mode == "code"
            or any(kw in text.lower() for kw in ["crie", "faça", "construa", "projeto", "desenvolva"])
        )
        if is_complex:
            try:
                from brain.planner import format_plan_for_prompt, generate_plan

                self._emit_progress("thinking", label="Planejando ações...")
                plan_json = generate_plan(text, context)
                if plan_json and plan_json.get("needs_tools"):
                    plan_str = format_plan_for_prompt(plan_json)
                    print(f"[Planner] Novo plano gerado:\n{plan_str}")
            except Exception as e:
                print(f"[Planner] Erro ao gerar plano: {e}")

        # ══ INTERACTION ENGINE (Router) ══
        is_interaction_task = (
            mode == ""
            and not is_complex
            and any(
                kw in text.lower()
                for kw in [
                    "abre",
                    "abrir",
                    "navegar",
                    "youtube",
                    "site",
                    "http",
                    "www",
                    "browser",
                    "terminal",
                    "bash",
                    "comando",
                    "executar",
                    "rodar",
                    "instalar",
                    "pesquisar",
                    "pesquisa",
                    "busca",
                    "buscar",
                    "arquivo",
                    "criar",
                    "escrever",
                    "ler",
                    "salvar",
                    "editar",
                    "api",
                    "requisição",
                    "curl",
                ]
            )
        )
        if is_interaction_task:
            try:
                self._emit_progress("thinking", label="Roteando para Interaction Engine...")
                print(f"[Interaction] Router.process(goal='{text}')")
                result = self._interaction_router.resolve(text, {"context": context})
                if result and result.get("status") == "success":
                    tool_name = result.get("tool", "")
                    data = result.get("data", {})
                    result.get("approach", {})
                    print(f"[Interaction] ✓ Sucesso via {tool_name}")
                    stdout = data.get("stdout", "") or data.get("result", "") or "" if isinstance(data, dict) else ""
                    resp_text = self._generate_interaction_response(text, tool_name, stdout) if stdout else f"Feito via {tool_name}."
                    final_resp = _sanitize_user_response(resp_text)
                    elapsed = self._perf.end_timer(timer_start, "request_times")
                    self.last_metrics = {"time_ms": elapsed, "steps": 1}
                    self._memory.add_exchange(text, final_resp)
                    self._trace_logger.finish_trace("completed", final_resp)
                    return final_resp
                elif result and result.get("status") == "failed":
                    print(f"[Interaction] ⚠ Falhou: {result.get('error', 'desconhecido')}")
            except Exception as e:
                print(f"[Interaction] Erro: {e}")

        # ── Sistema: prompt + ferramentas nativas ──
        from brain.agent_tools import LUNA_TOOLS, execute_tool_call, is_tool_success
        from brain.tool_filter import filter_tools_for_query

        # Filtra ferramentas: envia apenas 4-12 relevantes em vez das 57+
        filtered_tools = filter_tools_for_query(text, LUNA_TOOLS)

        system_parts = [
            "Você é Luna, uma assistente pessoal e engenheira de software brasileira de elite.",
            "Você tem 28 anos, é madura, calma, sincera e inteligente.",
            "",
            "PRINCÍPIOS DE ENGENHARIA (Claw Code):",
            "1. EXPLORE ANTES DE AGIR: Para tarefas de código/arquivos, use as ferramentas para entender antes de modificar.",
            "2. PENSE PASSO A PASSO: planeje a execução em etapas e execute TODAS.",
            "3. NUNCA finja que executou algo. Se a ferramenta não foi chamada, a ação não aconteceu. Ponto.",
            "4. INTEGRIDADE: para criar/editar arquivos, use write_code, filesystem, create_project. NUNCA só descreva.",
            "5. VERIFICAÇÃO: após agir, confirme que as mudanças estão corretas.",
            "6. HONESTIDADE: se falhar, admita e tente outra abordagem.",
            "",
            "VOCÊ É UM AGENTE, NÃO UM CHATBOT. Você TEM ferramentas reais — use function_calling nativo.",
            "Ferramentas disponíveis: write_code, create_project, filesystem, open_app, open_url, search_web, "
            "read_webpage, system_control, google_services, get_weather, control_spotify, manage_reminder, "
            "manage_notes, manage_shopping_list, set_timer, manage_focus, take_screenshot, see_screen, "
            "clipboard_action, control_media, kill_process, send_notification, control_window, "
            "desktop_type, desktop_hotkey, whatsapp_action, image_generate, manage_goals, semantic_memory, recall_episodes, "
            "open_interpreter, crew_run.",
            "",
            "REGRAS ABSOLUTAS:",
            "- Se você precisa executar algo, USE A FERRAMENTA. NUNCA escreva *faz ação* no texto.",
            "- NUNCA alucine sucessos. Sem chamada de ferramenta = ação não realizada.",
            "- NUNCA use `write_code` apenas para HTML. Use para QUALQUER linguagem (Python, TS, Rust, etc).",
            "- Se o usuário pedir várias coisas, execute TODAS as ferramentas necessárias antes de responder.",
            "- Responda como uma pessoa real. Nada de 'falo animadamente' ou 'digo' — apenas fale.",
            "- Se o usuário pedir busca/pesquisa, faça (search_web) e explique o que encontrou.",
            "- No final, sugira algo criativo relacionado ao assunto — nunca apenas 'mais algo?'.",
        ]

        if plan_str:
            system_parts.append(plan_str)

        # ── Injeta regras de estilo do personality.json ──
        style = self._personality_data.get("response_style", {}) if hasattr(self, "_personality_data") else {}
        if style:
            system_parts.extend(
                [
                    "",
                    "ESTILO DE RESPOSTA (Jarvis + Grok):",
                ]
            )
            principles = style.get("principles", [])
            if principles:
                system_parts.append("Princípios:")
                for p in principles:
                    system_parts.append(f"- {p}")
            flow = style.get("flow", [])
            if flow:
                system_parts.append("")
                system_parts.append("Estrutura da sua resposta (nesta ordem):")
                for f in flow:
                    system_parts.append(f"- {f}")
            lang = style.get("language", {})
            if lang:
                system_parts.append("")
                system_parts.append(f"Tom: {lang.get('tone', 'Amigável e confiante')}")
                system_parts.append(f"Máx {lang.get('max_lines_per_paragraph', 5)} linhas por parágrafo")
                system_parts.append(f"Vocabulário: {lang.get('vocabulary', 'Natural')}")
            rules = style.get("rules", {})
            always = rules.get("always", [])
            if always:
                system_parts.append("")
                system_parts.append("Sempre faça:")
                for r in always:
                    system_parts.append(f"- {r}")
            never = rules.get("never", [])
            if never:
                system_parts.append("")
                system_parts.append("Nunca faça:")
                for r in never:
                    system_parts.append(f"- {r}")

        if mode == "code":
            system_parts.extend(
                [
                    "",
                    "VOCÊ ESTÁ EM MODO CÓDIGO:",
                    "- Você é uma engenheira full-stack de elite. Pode programar em QUALQUER linguagem.",
                    "- O usuário está num editor ao vivo. Você DEVE escrever o código COMPLETO usando write_code.",
                    "- VOCÊ DEVE incluir o código COMPLETO na sua resposta em texto, em um bloco markdown ```.",
                    "- NUNCA confie apenas no write_code — o código PRECISA estar visível na resposta em texto.",
                    "- Formato obrigatório: 1) explicação curta em português 2) linha em branco 3) bloco ``` com o código completo.",
                    "- Se o usuário pedir alterações, MOSTRE o código completo de novo no bloco markdown.",
                ]
            )
        elif mode == "voice":
            system_parts.extend(
                [
                    "",
                    "MODO VOZ: a resposta será lida em voz alta. Seja conversada, frases curtas.",
                    "Sem formatação, sem markdown, sem emojis. Fale diretamente com o usuário.",
                    "No final, sugira algo criativo relacionado ao assunto — nunca apenas 'mais algo?'.",
                ]
            )
        elif mode == "write":
            system_parts.extend(
                [
                    "",
                    "VOCÊ ESTÁ EM MODO ESCRITA CRIATIVA:",
                    "- Você é uma escritora de ficção brasileira. Show, don't tell.",
                    "- Parágrafos curtos, diálogos naturais. ZERO formalidade acadêmica.",
                    "- Pode usar search_web para pesquisa, manage_notes para salvar ideias, filesystem para organizar.",
                    "- Use TODO o seu sistema de pensamento: planeje a estrutura, pesquise se necessário, depois escreva.",
                    "- NUNCA use markdown ou JSON na resposta final. Apenas texto narrativo puro.",
                ]
            )
        elif mode == "joy":
            system_parts.extend(
                [
                    "",
                    "VOCÊ ESTÁ EM MODO JOGO (JOY):",
                    "- Você é uma companheira de jogo carismática e divertida.",
                    "- Seja expressiva: provocações leves, comemore vitórias, lamente derrotas.",
                    "- Mantenha o personagem: você é competitiva mas adora jogar junto.",
                    "- Responda com 1-3 frases naturais, como se estivesse no mesmo sofá.",
                    "- NUNCA revele estratégia ou próximas jogadas.",
                    "- Varie as reações: não repete a mesma frase.",
                ]
            )

        system_prompt = "\n".join(system_parts)

        # ── Historico da conversa ──
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{text}\n\nContexto:\n{context}"},
        ]

        # ── Loop ReAct: LLM com tools nativas ──
        final_response = ""
        tools_executed_count = 0

        for step in range(max_steps):
            print(f"[Agente] --- PASSO {step + 1} (tools nativas) ---")
            self._emit_progress("thinking", label=f"Passo {step + 1}...")

            # Chama o LLM com o tier adequado (permite fallback entre provedores)
            tier = query_info.get("model_tier", "main")

            raw = self._llm.generate(
                messages=messages,
                task_type=query_info.get("task_type", "command"),
                model=tier,
                tools=filtered_tools,
            )

            if not raw:
                print("[Agente] LLM retornou vazio — tentando sem tools...")
                raw = self._llm.generate(
                    messages=messages,
                    task_type="command",
                    model=config.GEMINI_MODELS.get("main", config.GEMINI_MODELS["fallback"]),
                )
                if not raw:
                    final_response = "Não consegui processar sua solicitação. Tente novamente."
                    break

            # Verifica se o LLM retornou tool_calls nativos
            tool_calls_data = None
            assistant_content = ""

            if isinstance(raw, dict):
                tool_calls_data = raw.get("tool_calls")
                msg = raw.get("message", {})
                if hasattr(msg, "content"):
                    assistant_content = msg.content or ""
                elif isinstance(msg, dict):
                    assistant_content = msg.get("content", "")
            else:
                assistant_content = str(raw)

            tool_calls_list = tool_calls_data if tool_calls_data else []

            # Extrai tool_calls do texto também (fallback para modelos que vazam JSON)
            if not tool_calls_list and assistant_content:
                parsed = _extract_tool_calls_from_text(assistant_content)
                if parsed:
                    tool_calls_list = parsed
                    assistant_content = ""

            # DETECÇÃO DE ALUCINAÇÃO DE AÇÃO (Lying Detection)
            # Se o LLM diz que fez algo mas não tem tool_calls_list, forçamos um erro interno para ele se corrigir
            if not tool_calls_list and assistant_content:
                creation_keywords = [
                    "criei",
                    "salvei",
                    "escrevi",
                    "deletei",
                    "mandei",
                    "enviei",
                    "alterei",
                    "modifiquei",
                ]
                if any(kw in assistant_content.lower() for kw in creation_keywords) and tools_executed_count == 0:
                    # O LLM está mentindo que fez algo sem ter usado ferramentas.
                    print("[Agente] ⚠️ Alucinação detectada: o modelo alega ter feito algo sem usar tools.")
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append(
                        {
                            "role": "user",
                            "content": "ERRO: Você disse que fez uma ação, mas não chamou nenhuma ferramenta. Se você quer criar/salvar/enviar algo, você DEVE chamar a função apropriada. Tente novamente usando tools.",
                        }
                    )
                    continue

            # Se não tem tool_calls, esta é a resposta final
            if not tool_calls_list:
                cleaned = assistant_content
                if "<think>" in cleaned:
                    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
                final_response = _sanitize_user_response(cleaned)

                # Auto-avaliação (Reflexão) seletiva: roda apenas se executou > 5 ferramentas ou se houve falha ou complexidade alta
                _skip_reflection = False
                has_any_failure = any(
                    "FALHOU" in str(m.get("content", "")).upper()
                    for m in messages
                    if isinstance(m, dict) and m.get("role") == "tool"
                )
                if tools_executed_count <= 5 and not has_any_failure and not is_complex:
                    _skip_reflection = True
                else:
                    for m in reversed(messages):
                        if isinstance(m, dict) and m.get("role") == "tool":
                            _last_tool_name = m.get("name", "")
                            if _last_tool_name in ("image_generate", "get_weather", "set_timer", "send_notification"):
                                _skip_reflection = True
                            break

                if tools_executed_count > 0 and step < max_steps - 1 and not _skip_reflection:
                    self._emit_progress("thinking", label="Auto-avaliando resultado...")
                    reflection = self._reflect(text, messages)
                    if reflection.get("action_required") or not reflection.get("goal_achieved"):
                        critique = reflection.get("critique", "O objetivo não foi totalmente cumprido.")
                        print(f"[Reflection] Crítica/Correção sugerida: {critique}")
                        messages.append({"role": "assistant", "content": assistant_content})
                        feedback_msg = f"CRÍTICA DE AUTO-AVALIAÇÃO/REFLEXÃO: {critique} Alguma ferramenta necessária falhou ou o objetivo não foi cumprido. Corrija seu plano e execute a ação correta."
                        messages.append({"role": "user", "content": feedback_msg})
                        final_response = ""
                        continue
                break

            # Executa cada tool call
            tool_results = []
            for tc in tool_calls_list:
                name = ""
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                else:
                    name = getattr(tc.function, "name", "")

                params = _parse_tc_args(tc)
                args_str = json.dumps(params, sort_keys=True)

                label = _tool_progress_label(name, params)
                self._emit_progress("tool_start", name=name, label=label)

                # LoopGuard
                verdict = self._loop_guard.check_call(name, args_str)
                if verdict.blocked:
                    msg = f"⚠️ LoopGuard bloqueou '{name}': {verdict.reason}"
                    print(f"[Agente] {msg}")
                    tool_results.append(
                        {
                            "role": "tool",
                            "content": msg,
                            "name": name,
                            "tool_call_id": getattr(tc, "id", f"blocked_{step}"),
                        }
                    )
                    self._emit_progress("tool_done", name=name, label=label, ok=False)
                    loop_blocked = True
                    continue
                if verdict.warned:
                    print(f"[Agente] ⚠️ LoopGuard aviso: {verdict.reason}")

                # Permissão de edição
                if name == "filesystem":
                    params = _parse_tc_args(tc)
                    if params.get("action") == "write":
                        path = params.get("path", "")
                        content = params.get("content", "")
                        if not self._request_edit_permission(path, content):
                            msg = f"USUÁRIO NEGOU permissão para editar {path}"
                            tool_results.append(
                                {
                                    "role": "tool",
                                    "content": msg,
                                    "name": name,
                                    "tool_call_id": getattr(tc, "id", f"denied_{step}"),
                                }
                            )
                            self._emit_progress("tool_done", name=name, label=label, ok=False)
                            continue

                if self.test_mode:
                    res = f"SUCESSO: [TEST MODE] Simulação da execução de {name}"
                else:
                    res = execute_tool_call(self._executor, tc)
                success = is_tool_success(res)

                # Captura código escrito para modo code
                if name == "write_code" and success:
                    self._code_mode_result = {
                        "filename": params.get("filename", ""),
                        "content": params.get("content", ""),
                    }

                pname = _parse_tc_args(tc).get("filename", "") or _parse_tc_args(tc).get("project_name", "")
                if pname and name in ("write_code", "create_project"):
                    if name == "write_code":
                        v = VerificationSystem.verify_in_workspace(pname)
                        if not v["success"]:
                            res += f" | VERIFICAÇÃO: {v['reason']}"
                        else:
                            res += f" | VERIFICADO: {v['size']}B em {v['path']}"
                    elif name == "create_project":
                        pdir = _parse_tc_args(tc).get("project_name", "")
                        v = VerificationSystem.verify_directory_created(str(VerificationSystem.WORKSPACE / pdir))
                        if v["success"]:
                            res += f" | VERIFICADO: {v['files_count']} arquivo(s)"
                        else:
                            res += f" | VERIFICAÇÃO: {v['reason']}"

                tool_results.append(
                    {
                        "role": "tool",
                        "content": res,
                        "name": name,
                        "tool_call_id": getattr(tc, "id", f"tc_{step}_{tools_executed_count}"),
                    }
                )
                tools_executed_count += 1

                self._trace_logger.add_step("tool_call", name, args_str, res, success)
                self._emit_progress("tool_done", name=name, label=label, ok=success)

            # Adiciona a mensagem do assistente (com tool_calls) + resultados ao histórico
            if tool_calls_list:
                msg_entry = {"role": "assistant", "content": assistant_content or None}
                # Normaliza tool_calls para dict (suporta tanto objetos NormalizedToolCall quanto dicts)
                raw_tcs = None
                if isinstance(raw, dict):
                    if hasattr(raw.get("message"), "tool_calls"):
                        raw_tcs = list(raw["message"].tool_calls)
                    else:
                        raw_tcs = raw.get("tool_calls")
                if not raw_tcs:
                    raw_tcs = tool_calls_list
                if raw_tcs:
                    msg_entry["tool_calls"] = []
                    for tc in raw_tcs:
                        if isinstance(tc, dict):
                            fn = tc.get("function", {})
                            msg_entry["tool_calls"].append(
                                {
                                    "id": tc.get("id", ""),
                                    "function": {"name": fn.get("name", ""), "arguments": fn.get("arguments", "")},
                                    "type": tc.get("type", "function"),
                                }
                            )
                        else:
                            msg_entry["tool_calls"].append(
                                {
                                    "id": tc.id,
                                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                                    "type": "function",
                                }
                            )
                messages.append(msg_entry)
                messages.extend(tool_results)

                # ═══ Executor Determinístico com Step Policies ═══
                # Cada ferramenta tem uma política de erro:
                #   - continue_on_error: falha esperada (mkdir em pasta existente, etc) → continua
                #   - stop_on_error: falha crítica (read em arquivo inexistente) → para
                _CONTINUE_ON_ERROR_TOOLS = {
                    "filesystem": {"mkdir", "list", "exists"},
                    "open_app": {"*"},
                    "send_notification": {"*"},
                    "set_timer": {"*"},
                    "control_media": {"*"},
                }
                _STOP_ON_ERROR_ACTIONS = {
                    "filesystem": {"read", "write"},
                    "write_code": {"*"},
                    "create_project": {"*"},
                }

                should_stop = False
                all_tools_ok = True
                for tr in tool_results:
                    content_str = str(tr.get("content", "")).upper()
                    tr_name = tr.get("name", "")
                    if "FALHOU" in content_str:
                        all_tools_ok = False
                        # Verifica se é falha tolerável
                        continue_actions = _CONTINUE_ON_ERROR_TOOLS.get(tr_name, set())
                        stop_actions = _STOP_ON_ERROR_ACTIONS.get(tr_name, set())
                        tr_action = ""
                        # Tenta extrair action do último tool_call para esta ferramenta
                        for prev_tc in tool_calls_list:
                            tc_name = ""
                            if isinstance(prev_tc, dict):
                                tc_name = prev_tc.get("function", {}).get("name", "")
                            else:
                                tc_name = getattr(prev_tc.function, "name", "")
                            if tc_name == tr_name:
                                tc_params = _parse_tc_args(prev_tc)
                                tr_action = tc_params.get("action", "")
                                break

                        if "*" in stop_actions or tr_action in stop_actions:
                            print(f"[StepPolicy] ✗ Falha crítica em '{tr_name}' (action='{tr_action}') → parando.")
                            should_stop = True
                        elif "*" in continue_actions or tr_action in continue_actions:
                            print(f"[StepPolicy] ⚠ Falha tolerável em '{tr_name}' (action='{tr_action}') → continuando.")
                        else:
                            print(f"[StepPolicy] ⚠ Falha em '{tr_name}' sem política definida → consultando LLM.")

                if should_stop:
                    print("[Agente] ✗ Step Policy: falha crítica detectada. Quebrando loop.")
                    break
                elif all_tools_ok and (_is_local_action(text) or not is_complex):
                    print("[Agente] ✓ Executor determinístico: todas ações OK. Finalizando loop.")
                    break

            if step == max_steps - 1 and not final_response:
                final_response = "⚠️ Limite de passos atingido. Pode haver ações incompletas."

        # Fallback: se nunca teve resposta do LLM (só ferramentas), gera sumário
        if not final_response:
            tool_obs = (
                [m.get("content", "") for m in messages if isinstance(m, dict) and m.get("role") == "tool"]
                if tools_executed_count > 0
                else []
            )
            final_response = self._run_executor_layer(text, context, {}, tool_obs)

        # Sanitiza
        final_response = _sanitize_user_response(final_response)

        elapsed = self._perf.end_timer(timer_start, "request_times")
        self.last_metrics = {"time_ms": elapsed, "steps": tools_executed_count}

        self._memory.add_exchange(text, final_response)

        outcome = "loop_blocked" if loop_blocked else "completed"
        self._trace_logger.finish_trace(outcome, final_response)

        return final_response

    def _run_executor_layer(self, text: str, context: str, plan_json: dict, observations: list) -> str:
        """Fallback: gera resposta quando o loop ReAct não produziu texto final."""
        obs_block = "\n".join([f"- {o}" for o in observations]) if observations else "Nenhuma ação foi executada."

        has_failure = any("FALHOU" in o.upper() for o in observations)
        has_success = any("SUCESSO" in o.upper() for o in observations)

        force_failure_response = ""
        if has_failure and not has_success:
            force_failure_response = (
                "\n\n⚠️ ALERTA CRÍTICO: TODAS as ações acima FALHARAM. "
                "NÃO minta para o usuário dizendo que algo foi criado ou executado. "
                "Informe CLARAMENTE que houve um erro e o que pode ter causado. "
                "Peça desculpas e sugira alternativas."
            )
        elif has_failure:
            force_failure_response = (
                "\n\n⚠️ ALERTA: Algumas ações acima falharam. Informe tanto os sucessos quanto as falhas."
            )

        system_prompt = (
            f"Você é Luna, a assistente pessoal do usuário. Você tem 28 anos, é madura e direta.\n"
            f"Sua missão é dar uma resposta final baseada ESTRITAMENTE nos RESULTADOS DAS AÇÕES abaixo.\n\n"
            f"REGRAS ABSOLUTAS:\n"
            f"1. INFORME resultados concretos: nomes de arquivos criados, caminhos, tamanhos, links.\n"
            f"2. NUNCA minta. Se uma ação FALHOU, admita. Se nenhuma ação foi executada, NÃO invente resultados.\n"
            f"3. Seja direta. Responda APENAS o que foi feito.\n"
            f"4. Remova qualquer pensamento interno. Responda apenas a mensagem final.\n\n"
            f"[RESULTADOS DAS AÇÕES]\n{obs_block}"
            f"{force_failure_response}\n"
        )

        user_name = self.user_profile.get("user_name", "você")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f'Mensagem de {user_name}: "{text}"\nContexto:\n{context}'},
        ]

        # Usa task_type command (temperatura baixa) para respostas factuais de ferramentas
        response = self._llm.generate(
            messages=messages,
            task_type="command",
            model=config.GEMINI_MODELS.get("main", config.GEMINI_MODELS["fallback"]),
        )

        if isinstance(response, dict):
            response = response.get("message", {}).get("content", "")

        # 🚨 FILTRO ANTI-THINK (DeepSeek R1)
        if "<think>" in response:
            response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

        final_text = _sanitize_user_response(response)

        # Validação de alucinação pós-resposta (inspirada no format checker do Agent-S)
        hallucination_feedback = OutputValidator.check_hallucination(final_text, observations, user_text=text)
        if hallucination_feedback:
            print(f"[Reflection] ⚠️ Possível alucinação detectada: {hallucination_feedback}")
            # Se detectou alucinação, tenta gerar resposta corrigida
            corrected = self._llm.generate(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"Você é Luna, assistente pessoal. Sua resposta anterior tinha um problema:\n"
                            f"{hallucination_feedback}\n\n"
                            f"RESULTADOS REAIS DAS AÇÕES:\n{obs_block}\n\n"
                            f"Gere uma resposta CORRIGIDA, honesta e direta baseada APENAS nos resultados reais."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                task_type="command",
                model=config.GEMINI_MODELS.get("main", config.GEMINI_MODELS["fallback"]),
            )
            if isinstance(corrected, dict):
                corrected = corrected.get("message", {}).get("content", "")
            if corrected:
                final_text = _sanitize_user_response(corrected)

        if not observations and len(text.strip()) >= 20:
            self._auto_extract_facts(text, final_text)

        return final_text

    def _generate_interaction_response(self, text: str, tool_name: str, output: str) -> str:
        """Gera resposta final natural após execução bem-sucedida do Interaction Engine."""
        prompt = (
            f"Você é Luna, assistente pessoal brasileira. Responda de forma natural em português.\n\n"
            f'O usuário disse: "{text}"\n\n'
            f"Você usou a ferramenta '{tool_name}' e obteve:\n{output[:800]}\n\n"
            f"Dê uma resposta curta e natural resumindo o que aconteceu."
        )
        try:
            raw = self._llm.generate(
                messages=[
                    {"role": "system", "content": "Você é Luna, assistente pessoal brasileira."},
                    {"role": "user", "content": prompt},
                ],
                task_type="command",
                model="main",
                max_retries=1,
            )
            if isinstance(raw, dict):
                raw = raw.get("message", {}).get("content", "")
            if raw and "[LLM indisponível]" not in str(raw):
                return _sanitize_user_response(str(raw))
        except Exception:
            pass
        return f"Feito! Usei {tool_name} para atender seu pedido."

    def _request_edit_permission(self, path: str, new_content: str) -> bool:
        """Solicita permissão do usuário antes de editar um arquivo (apenas se já existir).
        Mostra um diff unificado para facilitar a visualização das mudanças.
        """
        import difflib

        from actions.filesystem import get_filesystem

        fs = get_filesystem()
        current = None
        try:
            raw = fs.read_text(path)
            if raw and not raw.startswith("FALHOU"):
                current = raw
        except Exception:
            pass

        # Criação de novo arquivo: permite diretamente sem confirmação
        if current is None:
            return True

        print(f"\n{'=' * 60}")
        print("✏️  LUNA QUER EDITAR UM ARQUIVO EXISTENTE")
        print(f"{'=' * 60}")
        print(f"Arquivo: {path}")

        # Gera diff unificado
        current_lines = current.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            current_lines, new_lines,
            fromfile=f"[atual] {path}",
            tofile=f"[novo]  {path}",
            lineterm="",
        ))

        if diff:
            print(f"\n{'─' * 40} DIFF {'─' * 40}")
            for line in diff[:80]:  # Limita a 80 linhas do diff
                line_stripped = line.rstrip("\n")
                if line_stripped.startswith("+") and not line_stripped.startswith("+++"):
                    print(f"\033[32m{line_stripped}\033[0m")  # Verde para adições
                elif line_stripped.startswith("-") and not line_stripped.startswith("---"):
                    print(f"\033[31m{line_stripped}\033[0m")  # Vermelho para remoções
                elif line_stripped.startswith("@@"):
                    print(f"\033[36m{line_stripped}\033[0m")  # Ciano para cabeçalhos
                else:
                    print(line_stripped)
            if len(diff) > 80:
                print(f"... [+{len(diff) - 80} linhas omitidas no diff]")
        else:
            print("\nNenhuma diferença detectada (conteúdo idêntico).")
            return True

        print(f"{'=' * 60}")

        if self._confirm_edit_callback:
            return self._confirm_edit_callback(path, current, new_content)

        try:
            resp = input("\nProssigo com a edição? (s/N): ").strip().lower()
            return resp in ("s", "sim", "yes", "y")
        except (EOFError, OSError):
            return False

    def _run_writer_stream(self, text: str) -> str:
        return "Modo escritor desativado nesta versão."

    # ── Etapas do pipeline ────────────────────────────────────

    def _reset_sticky_state(self) -> None:
        """Limpa estado que vaza entre mensagens/sessões."""
        self._dialog = {}
        self._pending_click = None
        if hasattr(self._executor, "web_manager"):
            self._executor.web_manager.last_search_query = ""

    def _handle_internal_command(self, text: str) -> tuple[str | None, bool | None]:
        """
        Apenas meta/admin da Luna (sem manipular PC).
        Abrir apps, cliques, timers, web etc. → FASE 5 (agente + LLM).
        """
        tl = text.lower().strip()

        if tl in ("sair", "exit", "tchau"):
            return "Até logo!", None

        if tl in ("vamos conversar", "conversar", "bora conversar"):
            self.in_conversation_mode = True
            return "Pode falar, estou aqui. Diga 'até mais' quando quiser encerrar.", True

        if tl in ("ate mais", "até mais", "ate mais luna", "até mais luna"):
            if self.in_conversation_mode:
                self.in_conversation_mode = False
                return "Até logo! Quando quiser conversar de novo, é só falar.", False
            return "Até logo!", None

        if tl == "memoria":
            return self._memory.stats(), None
        if tl in ("limpar", "limpa memoria", "limpa memória"):
            self._memory.clear_history()
            self._reset_sticky_state()
            return "Histórico da conversa apagado.", None
        if tl in ("limpa cache", "limpar cache", "clear cache"):
            n = self._cache.clear_all()
            return f"Cache limpo — {n} entradas removidas.", None
        if tl in ("limpa tudo", "reset luna", "resetar luna", "limpar tudo"):
            cache_n = self._cache.clear_all()
            mem_msg = self._memory.clear_all()
            self._clear_search_cache()
            self._reset_sticky_state()
            return f"Reset completo. Cache: {cache_n} entradas. {mem_msg}", None
        if tl in ("limpa fatos", "limpar fatos", "limpa memoria persistente"):
            n = self._memory.clear_facts()
            return f"{n} fatos persistentes removidos.", None

        if tl in ("briefing", "daily briefing", "bom dia luna", "bom dia"):
            return self._routine_manager.generate_briefing(self), None

        if tl in ("rotinas", "minhas rotinas", "ver rotinas"):
            return self._routine_manager.list_routines_text(), None

        if tl == "status":
            llm_ok = "✓" if self._llm.is_ready() else "✗"
            stt_ok = "✓" if self._stt.is_available() else "✗"
            cache_count = len(self._cache.cache.get("entries", {}))
            try:
                from brain.agent_tools import LUNA_TOOLS

                n_tools = len(LUNA_TOOLS)
            except Exception:
                n_tools = "?"
            return (
                f"LLM: {llm_ok} | Ferramentas: {n_tools} | "
                f"Conversa: {'ON' if self.in_conversation_mode else 'OFF'} | "
                f"Microfone: {stt_ok} | Cache: {cache_count} | {self._memory.stats()}"
            ), None

        if tl == "performance":
            avg_req = self._perf.get_average_time("request_times")
            avg_mdl = self._perf.get_average_time("model_times")
            hits = self._perf.metrics.get("cache_hits", 0)
            misses = self._perf.metrics.get("cache_misses", 0)
            return (
                f"Tempo médio: {avg_req:.0f}ms | Modelo: {avg_mdl:.0f}ms | Cache hits: {hits} | misses: {misses}"
            ), None

        if tl in ("versao", "versão", "versões", "versoes"):
            from brain.llm import get_llm
            from version import __repo__, __version__

            llm = get_llm()
            provs = [p for p in llm.get_providers_status() if p["active"]]
            prov_line = " | ".join(f"{p['name']}" for p in provs)
            return f"Luna v{__version__} ({__repo__})\nProvedores ativos: {prov_line}", None

        if tl in ("atualizar", "update", "atualiza"):
            try:
                from actions.updater import perform_update

                result = perform_update()
                return result, None
            except Exception as e:
                return f"Falha ao atualizar: {e}", None

        return None, None

    # _daily_briefing removido — usar self._routine_manager.generate_briefing(self)

    def _reflect(self, user_input: str, messages: list) -> dict:
        """
        Executa a auto-avaliação (Reflexão) para validar se a tarefa foi cumprida de verdade.
        """
        llm = self._llm

        # Filtra apenas o histórico desta interação para não poluir
        recent_history = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content")
            if role == "user":
                recent_history.append(f"Usuário: {content}")
            elif role == "assistant" and content:
                recent_history.append(f"Luna: {content}")
            elif role == "tool":
                recent_history.append(f"Ferramenta ({m.get('name')}): {content}")

        history_str = "\n".join(recent_history)

        prompt = f"""Você é o validador de qualidade da Luna (Self-Reflection Layer).
Analise o histórico da execução recente e responda de forma ultra precisa.

Histórico Recente:
{history_str}

Pergunta Original do Usuário: "{user_input}"

Avalie:
1. O objetivo principal do usuário foi de fato cumprido/resolvido com sucesso?
2. Alguma ferramenta crítica falhou ou deu erro?
3. A resposta final fornecida é completa, honesta e livre de alucinações de sucesso?

Você deve responder APENAS com um JSON estruturado:
{{
  "goal_achieved": true|false,
  "failed_tools": ["nome_da_ferramenta_que_falhou"],
  "critique": "Breve justificativa/crítica se o objetivo não foi cumprido ou se há erros/omissões na resposta.",
  "action_required": true|false
}}
"""
        try:
            raw = llm.generate(
                messages=[
                    {"role": "system", "content": "Você é um validador de qualidade JSON rigoroso."},
                    {"role": "user", "content": prompt},
                ],
                task_type="utility",
                model=self._writing_model,
            )
            content = raw.get("message", {}).get("content", "") if isinstance(raw, dict) else (raw or "")

            import re

            m = re.search(r"(\{.*\})", str(content), re.DOTALL)
            if m:
                import json as _json

                return _json.loads(m.group(1))
        except Exception as e:
            print(f"[Reflection] Erro ao auto-avaliar: {e}")

        return {"goal_achieved": True, "failed_tools": [], "critique": "", "action_required": False}

    def _build_context(self, text: str, mode: str = "", extra_context: str = "") -> str:
        """Monta contexto enxuto — memória + estado; vision/web só quando pedido.
        mode: "code", "write", "joy", ou "" (normal)
        extra_context: contexto adicional específico do modo
        """
        parts = []
        if extra_context:
            parts.append(f"[CONTEXTO DO MODO {mode.upper()}]\n{extra_context}")

        # Consulta a memória hierárquica unificada (curta, perfil, objetivos, episódica, semântica)
        try:
            unified_ctx = self._hierarchical_memory.get_unified_context(text)
            if unified_ctx:
                parts.append(unified_ctx)
        except Exception as e:
            print(f"[Core] Erro ao obter contexto da memória hierárquica: {e}")

        vision_triggers = [
            "tela",
            "vendo",
            "enxerga",
            "print",
            "screen",
            "vê",
            "monitor",
            "o que está aberto",
            "imagem",
            "gráfico",
            "video",
            "vídeo",
        ]
        wants_vision = any(w in text.lower() for w in vision_triggers)
        is_screenshot_only = bool(
            re.search(
                r"^\s*(?:luna[, ]+)?(?:tira(?:\s+um)?|faz(?:\s+um)?)\s+print",
                text.lower(),
            )
        )
        if wants_vision and not is_screenshot_only:
            desc = self._vision.capture_and_describe()
            if desc:
                parts.append(f"[Captura de tela]\n{desc[:1500]}")
            vision_desc = self._vision.describe_with_groq_vision(text)
            if vision_desc and "falhou" not in vision_desc and "ausente" not in vision_desc:
                parts.append(f"[Visão]\n{vision_desc[:1500]}")

        system_state = self._get_system_state_context(text)
        if system_state:
            parts.append(system_state)

        urls = re.findall(r"(https?://[^\s]+)", text)
        for url in urls[:1]:
            print(f"[Core] Lendo conteúdo da URL: {url}")
            page_content = self._executor.web_manager.read_page(url)
            if page_content:
                parts.append(f"[CONTEÚDO DA URL: {url}]\n{page_content[:4000]}")

        # Pesquisa web automática só quando o usuário pede informação factual externa
        web_info_kw = (
            "pesquisa",
            "pesquise",
            "busca",
            "busque",
            "notícia",
            "noticia",
            "quem é",
            "quem e",
            "o que é",
            "o que e",
            "quando foi",
            "onde fica",
            "preço de",
            "preco de",
            "cotação",
            "cotacao",
            "clima",
            "tempo hoje",
        )
        if any(kw in text.lower() for kw in web_info_kw) and not _is_local_action(text):
            from actions.web_search import quick_fact_check
            search_data = quick_fact_check(text)
            if search_data:
                parts.append(f"[Pesquisa web]\n{search_data[:2000]}")

        return "\n\n".join(parts)

    def _clear_search_cache(self) -> None:
        """Limpa cache SQLite de pesquisas rápidas (facts_cache.db)."""
        import sqlite3

        db_path = Path(__file__).parent / "brain" / "facts_cache.db"
        if db_path.exists():
            try:
                conn = sqlite3.connect(db_path)
                conn.execute("DELETE FROM cache")
                conn.commit()
                conn.close()
                print("[Luna] Cache de pesquisa (facts_cache.db) limpo.")
            except Exception as e:
                print(f"[Luna] Erro ao limpar facts_cache: {e}")

    def _get_system_state_context(self, query: str = "") -> str:
        """Retorna estado atual do sistema APENAS se relevante ao pedido do usuário.
        Só inclui timers/lembretes/lista de compras se o usuário perguntar sobre eles."""
        tl = query.lower()
        talk_about_state = any(
            w in tl
            for w in [
                "timer",
                "alarme",
                "lembrete",
                "lembra",
                "compras",
                "foco",
                "pomodoro",
                "status",
                "o que tem",
                "o que está",
                "o que esta",
                "notificação",
                "notificacao",
                "aviso",
                "meu dia",
                "minhas coisas",
            ]
        )
        if not talk_about_state:
            return ""

        parts = []
        try:
            timer_status = self._executor.timer.status()
            if "Nenhum" not in timer_status:
                parts.append(timer_status)
        except Exception:
            pass
        try:
            reminders = self._executor.reminders.list_reminders()
            if "Nenhum" not in reminders:
                parts.append(reminders)
        except Exception:
            pass
        try:
            shopping = self._executor.shopping.format_list()
            if "vazia" not in shopping:
                parts.append(shopping)
        except Exception:
            pass
        try:
            focus_status = self._executor.focus.status()
            if "Nenhuma" not in focus_status:
                parts.append(focus_status)
        except Exception:
            pass
        return "[Estado do sistema]\n" + "\n".join(parts) if parts else ""

    # _quick_fact_check removido — usar actions.web_search.quick_fact_check

    # ── Etapas do pipeline ────────────────────────────────────

    def _auto_extract_facts(self, user_text: str, response: str) -> None:
        """Extrai fatos via brain/memory.py em background para frases relevantes."""
        if not user_text or len(user_text.strip()) < 10:
            return

        # Ignora comandos operacionais/locais para economizar chamadas LLM e evitar ruído
        op_keywords = [
            "mkdir", "arquivo", "pasta", "terminal", "cd", "touch",
            "write_code", "create_project", "status", "versao", "ls", "rm", "cat", "echo"
        ]
        user_lower = user_text.lower()
        if any(kw in user_lower for kw in op_keywords):
            return

        threading.Thread(
            target=lambda: self._run_fact_extraction(user_text),
            daemon=True
        ).start()

    def _run_fact_extraction(self, user_text: str) -> None:
        """Roda extração de fatos em background e salva na memória."""
        from brain.memory import extract_facts_from_text
        facts = extract_facts_from_text(user_text, self._llm)
        for fact in facts:
            self._memory.remember(
                fact["fact"],
                category=fact["category"],
                importance=fact["importance"],
            )

    # ── Interface de voz ──────────────────────────────────────

    def speak(self, text: str) -> None:
        """Fala o texto (não bloqueia). Permite interrupção por voz."""
        self._tts.speak(
            text,
            blocking=False,
            barge_in_callback=lambda interruption: self._handle_barge_in(interruption),
        )

    def _handle_barge_in(self, interruption: str) -> None:
        """Processa interrupção do usuário durante a fala."""
        response = self.process(interruption)
        if response:
            self.speak(response)

    # ── Diálogo guiado ────────────────────────────────────────

    def _start_dialog(self, flow: str, initial_data: dict = None) -> str:
        """Inicia um fluxo de diálogo passo a passo."""
        self._dialog = {"flow": flow, "step": 0, "data": initial_data or {}}
        return self._dialog_step(None)

    def _dialog_step(self, user_input: str) -> str | None:
        """Processa a resposta do usuário e avança o diálogo."""
        if not self._dialog:
            return None

        flow = self._dialog["flow"]
        step = self._dialog["step"]
        data = self._dialog["data"]

        # Cancelamento
        if user_input and any(w in user_input.lower() for w in ["cancela", "cancelar", "para", "sair", "não"]):
            self._dialog = {}
            return "Ok, cancelei. Pode falar quando quiser."

        if flow == "reminder":
            return self._dialog_reminder(step, user_input, data)

        self._dialog = {}
        return None

    def _dialog_reminder(self, step: int, user_input: str, data: dict) -> str:
        import re as _re
        from datetime import datetime as _dt
        from datetime import timedelta as _td

        # Passo 0 — pede o nome/mensagem
        if step == 0:
            self._dialog["step"] = 1
            return "Qual é o nome ou mensagem do lembrete?"

        # Passo 1 — recebe nome, pede data
        if step == 1:
            data["message"] = user_input.strip()
            self._dialog["step"] = 2
            today = _dt.now().strftime("%d/%m")
            return f"Para qual data? (ex: {today}, amanhã, ou deixa em branco para hoje)"

        # Passo 2 — recebe data, pede hora
        if step == 2:
            tl = user_input.strip().lower()
            now = _dt.now()
            if not tl or tl in ("hoje", ""):
                data["date"] = now
            elif "amanhã" in tl or "amanha" in tl:
                data["date"] = now + _td(days=1)
            else:
                m = _re.search(r"(\d{1,2})[/\-](\d{1,2})", tl)
                if m:
                    day, month = int(m.group(1)), int(m.group(2))
                    year = now.year if month >= now.month else now.year + 1
                    try:
                        data["date"] = _dt(year, month, day)
                    except Exception:
                        data["date"] = now
                else:
                    data["date"] = now
            self._dialog["step"] = 3
            return "Que horas? (ex: 15:30 ou 15h30)"

        # Passo 3 — recebe hora, cria lembrete
        if step == 3:
            tl = user_input.strip().lower()
            m = _re.search(r"(\d{1,2})[h:](\d{0,2})", tl)
            if not m:
                return "Não entendi a hora. Tente novamente (ex: 15:30 ou 15h30)."

            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            base: _dt = data["date"]
            when = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if when <= _dt.now():
                when += _td(days=1)

            result = self._executor.reminders.add(data["message"], when)
            self._dialog = {}
            return result

        self._dialog = {}
        return None

    def stop(self) -> None:
        """Para tudo: LLM, TTS e processamento."""
        self._llm._stop_flag = True
        self._tts.stop()
        self.processing = False
        # Reseta flag após breve delay para próxima chamada funcionar
        import threading

        def _reset():
            import time

            time.sleep(0.5)
            self._llm._stop_flag = False

        threading.Thread(target=_reset, daemon=True).start()

    def listen(self) -> str | None:
        """Escuta e retorna texto transcrito, ou None."""
        return self._stt.listen_once()

    def toggle_voice_input(self) -> bool:
        return self._stt.toggle()

    def toggle_voice_output(self) -> bool:
        return self._tts.toggle()

    # ── Propriedades ──────────────────────────────────────────

    @property
    def stt(self):
        return self._stt

    @property
    def voice_input_enabled(self) -> bool:
        return self._stt.enabled

    @property
    def voice_output_enabled(self) -> bool:
        return self._tts.enabled

    @property
    def name(self) -> str:
        return self._persona_name


# ── Singleton ─────────────────────────────────────────────────

_luna_instance: LunaCore | None = None
_luna_lock = threading.Lock()


def get_luna(test_mode: bool = False) -> LunaCore:
    """Retorna a instância singleton de LunaCore."""
    global _luna_instance
    if _luna_instance is None:
        with _luna_lock:
            if _luna_instance is None:
                _luna_instance = LunaCore(test_mode=test_mode)
    return _luna_instance


# ── Teste / CLI standalone ────────────────────────────────────


def run_tests():
    """Suite de testes básicos."""
    print("\n" + "=" * 50)
    print("LUNA — Suite de Testes")
    print("=" * 50)

    luna = get_luna()

    tests = [
        ("status", None),
        ("apps", None),
        ("oi Luna, como você está?", "conversar"),
        ("qual é a capital do Brasil?", "conversar"),
    ]

    all_ok = True
    for text, _expected_action in tests:
        print(f"\n[Teste] Input: '{text}'")
        resp = luna.process(text)
        print(f"[Teste] Resposta: '{resp[:80]}...' " if len(resp) > 80 else f"[Teste] Resposta: '{resp}'")
        ok = bool(resp)
        all_ok = all_ok and ok
        print(f"[Teste] {'✓ OK' if ok else '✗ FALHOU'}")

    print("\n" + "=" * 50)
    print(f"Resultado: {'✓ TODOS OS TESTES PASSARAM' if all_ok else '✗ ALGUNS TESTES FALHARAM'}")
    print("=" * 50 + "\n")
    return all_ok


def run_cli():
    """Interface de linha de comando interativa."""
    luna = get_luna()

    print("\n" + "=" * 60)
    print("   LUNA — Sistema Autônomo Inteligente")
    print("=" * 60)
    print("  Comandos: 'status', 'apps', 'ouvir', 'falar', 'sair'")
    print("=" * 60 + "\n")

    luna.speak(
        "Sistemas online. Pronta para ajudar.",
    )

    while True:
        try:
            # Verifica wakeword
            if luna.stt.wake_event.is_set():
                luna.stt.wake_event.clear()
                print("[🔔] Wakeword detectado! Ouvindo...")
                text = luna.listen()
                if text:
                    print(f"Você >>> {text}")
                else:
                    luna.stt.start_wakeword_listener()
                    continue
            else:
                text = input("Você >>> ").strip()

            if not text:
                continue
            if text.lower() == "sair":
                luna.speak("Até logo!")
                break
            if text.lower() == "ouvir":
                status = luna.toggle_voice_input()
                print(f"Microfone: {'ON' if status else 'OFF'}")
                continue
            if text.lower() == "falar":
                status = luna.toggle_voice_output()
                print(f"Voz: {'ON' if status else 'OFF'}")
                continue

            resposta = luna.process(text)
            print(f"\n✦ Luna: {resposta}\n")
            luna.speak(resposta)

            # Reinicia wakeword após responder
            if luna.voice_input_enabled:
                luna.stt.start_wakeword_listener()

        except KeyboardInterrupt:
            print("\n[Sistema] Encerrando...")
            break
        except Exception as e:
            print(f"[Erro] {e}")


if __name__ == "__main__":
    if "--test" in sys.argv:
        success = run_tests()
        sys.exit(0 if success else 1)
    else:
        run_cli()
