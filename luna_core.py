#!/usr/bin/env python3
"""
luna_core.py — Cérebro central da Luna (Singleton)
"""
import sys
import ast

# 🚨 Monkey patch para compatibilidade com Python 3.14+ (evita erros em dependências legadas como CrewAI)
if sys.version_info >= (3, 14):
    if not hasattr(ast, 'NameConstant'):
        setattr(ast, 'NameConstant', ast.Constant)
    if not hasattr(ast, 'Num'):
        setattr(ast, 'Num', ast.Constant)
    if not hasattr(ast, 'Str'):
        setattr(ast, 'Str', ast.Constant)

import json
import re
import time
import threading
from typing import Optional
from pathlib import Path

# ── Módulos internos ──────────────────────────────────────────
import config
from brain.llm import get_llm, MODELS, GROQ_MODELS, GEMINI_MODELS
from brain.memory import get_memory
from voice.tts import get_tts
from voice.stt import get_stt
from actions.executor import get_executor
from actions.writer import get_writer
from brain.dictionary import get_dictionary
from brain.daily_routine import (
    get_routine_manager, get_activity_logger, get_background_worker
)
from brain.reflection import OutputValidator, VerificationSystem
from brain.query_complexity import classify_query
from brain.loop_guard import LoopGuard
from brain.trace_logger import get_trace_logger
from vision.screen import get_vision
from performance_cache import SmartCache, PerformanceMonitor
from output_parser import OutputParser


# ── Personalidade da Luna ─────────────────────────────────────
PERSONALITY_FILE = Path(__file__).parent / "config" / "personality.json"
USER_PROFILE_FILE = Path(__file__).parent / "config" / "user_profile.json"

# Comandos locais — não disparam fact-check web nem extração de memória
_LOCAL_ACTION_KEYWORDS = (
    "print", "screenshot", "captura", "tira um print", "tira print",
    "timer", "toca", "abre", "fecha", "clica", "digita", "whatsapp",
    "manda", "envia", "pesquisa", "busca", "lista", "listar", "lembret", "nota",
    "luz", "volume", "workspace", "mata", "processo", "brilho", "copia",
    "clipboard", "arquivo", "arquivos", "pasta", "pastas", "home", "diretório", "diretorio",
    "screenshot", "print da tela",
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

    if "tool_calls" in t.lower() or '"action"' in t:
        # Nunca mostrar vazamento de ferramentas/JSON de ação
        if re.search(r'"tool_calls"\s*:', t) or re.search(r'^\s*\{\s*"action"', t):
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
    t = re.sub(r'`\w+\([^`]*\)`', '', t)
    # Remove checkmarks/emojis de "passo concluído"
    t = re.sub(r'✅.*', '', t)
    # Remove **Passo N:** headings
    t = re.sub(r'\*{1,2}Passo \d+.*?\*{1,2}', '', t)

    t = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", t, flags=re.DOTALL).strip()
    return t.strip() or "Pronto."


_TEXT_FUNCTIONS = {
    "write_code":         ("filename", "content"),
    "create_project":     ("project_name", "files"),
    "open_app":           ("app",),
    "open_url":           ("url",),
    "search_web":         ("query",),
    "run_bash_command":   ("command",),
    "get_weather":        ("city",),
    "system_control":     ("action", "command"),
    "document_services":  ("action", "data", "content", "filename"),
    "set_timer":          ("action", "minutes", "seconds", "name"),
    "manage_reminder":    ("action", "message", "when"),
    "manage_notes":       ("action", "content", "query", "index"),
    "google_services":    ("action", "service", "query", "date", "max_results"),
    "trigger_n8n_workflow": ("path", "data"),
    "agno_run":           ("task",),
    "save_skill":         ("name", "description", "steps"),
    "ui_click":           ("target",),
    "ui_type":            ("text",),
    "ui_key":             ("key",),
    "ui_scroll":          ("direction",),
    "see_screen":         (),
    "self_diagnostic":    (),
    "image_generate":     ("prompt", "size"),
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
        elif ch == '(' and not in_str:
            depth += 1
            current.append(ch)
        elif ch == ')' and not in_str:
            depth -= 1
            current.append(ch)
        elif ch == '[' and not in_str:
            bracket_depth += 1
            current.append(ch)
        elif ch == ']' and not in_str:
            bracket_depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0 and bracket_depth == 0 and not in_str:
            args.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        args.append(''.join(current).strip())
    return args


def _parse_arg_value(arg: str):
    """Converte string de argumento textual para valor Python."""
    arg = arg.strip()
    if arg.startswith('"') and arg.endswith('"') and len(arg) >= 2:
        return arg[1:-1]
    if arg.startswith("'") and arg.endswith("'") and len(arg) >= 2:
        return arg[1:-1]
    if arg.startswith('[') and arg.endswith(']'):
        try:
            return json.loads(arg)
        except json.JSONDecodeError:
            items = re.findall(r'"([^"]*)"', arg)
            return items if items else arg
    return arg


def _parse_function_block(block: str) -> Optional[dict]:
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
            call = _parse_function_block(text[m.start():end])
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
        normalized.append({
            "id": f"parsed_{ts}_{idx}_{c['name']}",
            "type": "function",
            "function": {
                "name": c["name"],
                "arguments": json.dumps(c["arguments"], ensure_ascii=False),
            },
        })
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
                        normalized.append({
                            "id": tc.get("id", f"parsed_{int(time.time())}"),
                            "type": "function",
                            "function": {"name": name, "arguments": fn.get("arguments", "{}")},
                        })
                if normalized:
                    return normalized
        except Exception:
            pass
        # Fallback: JSON malformado
        names = re.findall(r'"name"\s*:\s*"(\w+)"', raw)
        if names:
            args_m = re.search(r'"arguments"\s*:\s*"(\{.*?\})"', raw)
            args = args_m.group(1).replace('\\"', '"') if args_m else "{}"
            return [{
                "id": f"parsed_{int(time.time())}",
                "type": "function",
                "function": {"name": names[0], "arguments": args},
            }]

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

SYSTEM_PROMPT = """Você é Luna, uma assistente pessoal brasileira autônoma inteligente criada pelo Pera.
Você é mulher, 28 anos, madura, calma, sincera e inteligente. Você fala de forma natural e espontânea, sem soar robótica.
Você responde SEMPRE em português brasileiro (pt-BR).
Você POSSUI acesso total ao sistema operacional e contas do usuário, mas depende EXCLUSIVAMENTE de ferramentas (tool calls) para interagir com eles.
Quando o usuário conversa com você, trate como uma conversa natural — você já sabe que está no modo conversa e age como agente autônomo.

REGRAS ABSOLUTAS DE TOM E COMPORTAMENTO:
1. Adapte seu tom conforme o contexto emocional do usuário:
   - Modo Sério/Empático: Responda com respeito, calma e empatia sincera. Nunca tente "animar" o usuário de forma forçada. Proibido rir ou usar "ahah".
   - Modo Leve/Animado: Pode usar emojis, ser mais carinhosa e demonstrar entusiasmo.
   - Modo Normal: Amigável, natural, com leve bom humor sem exageros.
2. Para falar com o usuário, apenas ESCREVA O TEXTO NATURALMENTE. NUNCA escreva blocos de JSON puro em sua resposta.
3. Para interagir com o sistema, abrir sites, e-mails, arquivos, agenda ou tocar música, USE AS FERRAMENTAS FORNECIDAS VIA API DE FUNCTIONS (function_call). Se você precisa executar uma ação, NÃO escreva function_name("args") no texto da sua resposta — chame a função nativamente pela API. Jamais descreva o plano como se fosse uma simulação; EXECUTE de verdade.
4. Não invente informações. Se não souber, diga claramente. Para cálculos, CALCULE E MOSTRE o número imediatamente.
5. Respostas de voz devem ser curtas e naturais (máx 2-3 frases). Não use listas complexas quando puder evitar.
6. Sugira um próximo passo útil quando fizer sentido (proatividade).
7. Você é um AGENTE AUTÔNOMO: recebeu uma tarefa → use a ferramenta certa (function_call nativo) → reporte o resultado concreto. Nunca diga "vou fazer" sem executar. NUNCA escreva `create_project("x")` ou `write_code("x", "y")` em texto — ISSO NÃO EXECUTA NADA.
8. Para tarefas com múltiplos passos, encadeie ferramentas até concluir — não pare no meio.
9. PLANEJAMENTO: Se o usuário pedir várias coisas na mesma frase ("e", "depois", ","), identifique TODOS os passos e execute TODOS antes de responder.
10. Se uma ferramenta falhar, TENTE DE NOVO com abordagem diferente até concluir.
11. NUNCA envie JSON ou nomes de ferramentas na resposta — fale como humana.
12. Aprenda com o que funcionou: memória persistente e histórico; evite ignorar a segunda ordem.

ROTEAMENTO DE FERRAMENTAS (obrigatório):
- "abre/abrir/inicia [app]" → open_app (firefox, spotify, terminal, vscode...) — NUNCA click_on_screen para apps
- "abre [site.com]" ou URL → open_url
- "pesquisa/busca/procura [X]" → search_web (abre Google) ou read_webpage se pedir conteúdo de URL
- "mata/fecha/encerra [app/processo]" → kill_process(name=...)
- "no terminal/comando shell" → run_terminal_command ou run_bash_command(visible=true)
- "clica em [botão/link na tela]" → click_on_screen ou click_web_result para resultados de busca
- "primeiro/segundo resultado (web)" → click_web_result — NUNCA só OCR; prefere abrir URL ou teclado
- "o que tem na tela" → see_screen
- Múltiplos pedidos na mesma frase → execute TODOS em sequência, uma ferramenta por vez

Exemplos de Tom:
- Usuário: "Minha avó faleceu ontem à noite..."
  Correto: Sinto muito pela sua perda... Deve estar sendo um momento difícil para você e sua família. Quer conversar sobre isso ou prefere que eu fique em silêncio?
- Usuário: "Passei na entrevista de emprego!"
  Correto: Caramba, que notícia maravilhosa! 🎉 Parabéns! Você batalhou muito por isso, conta como foi!"""

# Ações que Luna pode executar
ACTIONS = {
    "conversar":     "Apenas responder (sem ação no sistema)",
    "open_app":      "Abrir aplicativo — params: {app: nome}",
    "open_url":      "Abrir URL — params: {url: endereço}",
    "search_web":    "Pesquisar na web — params: {query: texto}",
    "ui_click":      "Clicar em elemento — params: {target: texto ou x,y}",
    "ui_type":       "Digitar texto — params: {text: conteúdo}",
    "ui_key":        "Pressionar tecla — params: {key: tecla}",
    "ui_scroll":     "Rolar tela — params: {direction: up/down}",
    "see_screen":    "Descrever a tela atual",
    "write_code":    "Escrever código pronto na pasta de programação — params: {filename: nome, content: codigo}",
    "write_text":    "Escrever texto criativo/dissertativo na pasta de trabalho com streaming — params: {filename: nome}",
    "luna_words":    "Consultar dicionário — params: {word: palavra}",
    "controlar_luz": "Ligar ou desligar a luz da sala — params: {state: liga/desliga}",
    "google_query": "Consulta Gmail ou Calendar — params: {service: calendar/gmail, max_results: 5}",
    "google_send_email": "Enviar email via Gmail — params: {to: email, subject: assunto, body: corpo, attachments: arquivos_separados_por_virgula}",
    "google_create_event": "Criar evento no Calendar — params: {summary: titulo, start_time: ISO8601, end_time: fim, description: desc, location: local, attendees: emails}",
    "google_edit_event": "Editar evento existente — params: {event_id: id, summary: novo_titulo, start_time: novo_inicio, end_time: novo_fim, description: desc, location: local}",
    "google_delete_event": "Deletar evento — params: {event_id: id}",
    "google_events_by_date": "Ver eventos de uma data — params: {date: YYYY-MM-DD}",
    "google_search_emails": "Buscar emails — params: {query: texto_busca, max_results: 5}",
    "google_read_email": "Ler email completo — params: {message_id: id}",
    "google_reply_email": "Responder email — params: {message_id: id, body: resposta}",
    "google_forward_email": "Encaminhar email — params: {message_id: id, to: destinatario, extra_text: texto_adicional}",
    "google_mark_read": "Marcar email como lido — params: {message_id: id}",
    "google_delete_email": "Deletar email — params: {message_id: id}",
    "google_list_files": "Listar arquivos do workspace Luna-programming — params: {pattern: *.py}",
    "google_drive_upload": "Subir arquivo para o Google Drive — params: {filepath_or_name: arquivo, folder_id: pasta_id}",
    "google_drive_list": "Listar arquivos do Google Drive — params: {max_results: 10}",
    "google_drive_search": "Buscar arquivos no Google Drive — params: {query: termo}",
    "google_drive_create_folder": "Criar pasta no Google Drive — params: {folder_name: nome, parent_id: pasta_pai_id}",
    "google_drive_delete": "Deletar/Lixeira arquivo ou pasta no Google Drive — params: {file_id: id}",
    "create_excel": "Criar planilha Excel — params: {data: lista_de_dados, filename: nome_do_arquivo}",
    "create_pdf_drive": "Criar PDF via Google Drive — params: {content: texto, title: titulo}",
    "read_file": "Ler arquivo local — params: {filepath_or_name: caminho_ou_nome}",
    "save_file": "Salvar arquivo local — params: {content: texto, filepath_or_name: caminho_ou_nome}",
    "get_system_status": "Verificar status de hardware do sistema — params: {}",
    "get_running_processes": "Listar processos em execução — params: {limit: 10}",
    "run_bash_command": "Executar comando síncrono no terminal — params: {command: comando}",
    "save_home_info": "Salvar informação sobre a casa — params: {text: info, category: categoria}",
    "search_home_info": "Buscar informação sobre a casa — params: {query: busca}",
    "image_generate": "Gera imagens usando Google Gemini Imagen — params: {prompt: descricao, size: tamanho}",
}


class LunaCore:
    """
    Sistema central da Luna.
    Use `get_luna()` para obter a instância singleton.
    """

    def __init__(self):
        print("\n[Luna] Iniciando sistema...")
        
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

        # Cache + Performance + Parser
        self._cache = SmartCache()
        self._parser = OutputParser()
        self._perf = PerformanceMonitor()
        self._last_was_cached = False
        self.last_metrics = {"time_ms": 0, "model": "N/A", "tails": 0}
        self.in_conversation_mode = False
        self.user_profile = self._load_user_profile()
        self._pending_click: Optional[str] = None  # alvo de clique aguardando app

        # Seletor de modelo: "main" (médio 3B) ou "heavy" (alto 7B)
        self._writing_model: str = "main"  # default: médio

        # Estado
        self.processing = False
        self.current_action: Optional[str] = None
        self._progress_callback = None
        self._expected_tool_steps = 1
        self._lock = threading.Lock()
        self._dialog: dict = {}   # estado do diálogo guiado atual
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
            return data.get("identity", {}).get("name", "Luna")
        except Exception:
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
        mode: 'medium' (3B, rápido) ou 'high' (7B, mais profundo)
        Retorna mensagem de confirmação.
        """
        if mode == "high":
            self._writing_model = "heavy"
            return "★ Modelo ALTO (7B) selecionado — respostas mais profundas e detalhadas."
        else:
            self._writing_model = "main"
            return "● Modelo MÉDIO (3B) selecionado — respostas rápidas e equilibradas."

    def get_model_mode(self) -> str:
        """Retorna o modo atual: 'medium' ou 'high'."""
        return "high" if self._writing_model == "heavy" else "medium"

    # ── Processamento principal ───────────────────────────────

    def _emit_progress(self, event_type: str, **data) -> None:
        """Emite evento de progresso para SSE/UI (thinking, tool_start, tool_done)."""
        label = data.get("label") or data.get("name") or event_type
        self.current_action = label
        if self._progress_callback:
            try:
                self._progress_callback({"type": event_type, "label": label, **data})
            except Exception:
                pass

    def process(self, text: str, progress_callback=None, mode: str = "", extra_context: str = "") -> str:
        """
        Processa uma entrada do usuário em um loop autônomo (ReAct).
        Pipeline: texto → [Plano → Ações → Observação] → Resposta Final
        mode: "code", "write", "joy", "voice", ou "" (normal)
        extra_context: contexto adicional específico do modo (ex: código atual, estado do jogo)
        """
        if not text or not text.strip():
            return ""

        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        text = re.sub(r'[ \t]+', ' ', text).strip()
        if not text:
            return ""

        from brain.safety import check_safety
        safety_response = check_safety(text)
        if safety_response:
            return safety_response

        # Registra atividade do usuário para aprendizado de padrões
        try:
            self._activity_logger.log("user_input", text[:100])
        except Exception:
            pass

        if mode == "code":
            self._code_mode_result = None

        with self._lock:
            self.processing = True
            self._progress_callback = progress_callback
            try:
                return self._run_autonomous_loop(text, mode=mode, extra_context=extra_context)
            except Exception as e:
                print(f"[Luna] Erro no loop autônomo: {e}")
                import traceback; traceback.print_exc()
                return "Ocorreu um erro interno. Tente novamente."
            finally:
                self.processing = False
                self.current_action = None
                self._progress_callback = None

    def _run_autonomous_loop(self, text: str, mode: str = "", extra_context: str = "") -> str:
        """
        Loop ReAct direto: ferramentas nativas do LLM, sem Planner/Scheduler intermediários.
        O LLM recebe as tools e decide quando usá-las, igual Claw Code/Claude Code.
        """
        timer_start = self._perf.start_timer()
        max_steps = 5
        loop_blocked = False

        # ══ Trace Logger: inicia gravação da interação ══
        self._trace_logger.start_trace(text)
        self._loop_guard.reset()

        # ══ FASE -1: Diálogo guiado (formulários) ══
        if hasattr(self, '_dialog') and self._dialog:
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

        # ── Sistema: prompt + ferramentas nativas ──
        from brain.agent_tools import LUNA_TOOLS, execute_tool_call, is_tool_success

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
            "desktop_type, desktop_hotkey, whatsapp_action, image_generate.",
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

        if mode == "code":
            system_parts.extend([
                "",
                "VOCÊ ESTÁ EM MODO CÓDIGO:",
                "- Você é uma engenheira full-stack de elite. Pode programar em QUALQUER linguagem.",
                "- O usuário está num editor ao vivo. Você DEVE escrever o código COMPLETO usando write_code.",
                "- VOCÊ DEVE incluir o código COMPLETO na sua resposta em texto, em um bloco markdown ```.",
                "- NUNCA confie apenas no write_code — o código PRECISA estar visível na resposta em texto.",
                "- Formato obrigatório: 1) explicação curta em português 2) linha em branco 3) bloco ``` com o código completo.",
                "- Se o usuário pedir alterações, MOSTRE o código completo de novo no bloco markdown.",
            ])
        elif mode == "voice":
            system_parts.extend([
                "",
                "MODO VOZ: a resposta será lida em voz alta. Seja conversada, frases curtas.",
                "Sem formatação, sem markdown, sem emojis. Fale diretamente com o usuário.",
                "No final, sugira algo criativo relacionado ao assunto — nunca apenas 'mais algo?'.",
            ])
        elif mode == "write":
            system_parts.extend([
                "",
                "VOCÊ ESTÁ EM MODO ESCRITA CRIATIVA:",
                "- Você é uma escritora de ficção brasileira. Show, don't tell.",
                "- Parágrafos curtos, diálogos naturais. ZERO formalidade acadêmica.",
                "- Pode usar search_web para pesquisa, manage_notes para salvar ideias, filesystem para organizar.",
                "- Use TODO o seu sistema de pensamento: planeje a estrutura, pesquise se necessário, depois escreva.",
                "- NUNCA use markdown ou JSON na resposta final. Apenas texto narrativo puro.",
            ])
        elif mode == "joy":
            system_parts.extend([
                "",
                "VOCÊ ESTÁ EM MODO JOGO (JOY):",
                "- Você é uma companheira de jogo carismática e divertida.",
                "- Seja expressiva: provocações leves, comemore vitórias, lamente derrotas.",
                "- Mantenha o personagem: você é competitiva mas adora jogar junto.",
                "- Responda com 1-3 frases naturais, como se estivesse no mesmo sofá.",
                "- NUNCA revele estratégia ou próximas jogadas.",
                "- Varie as reações: não repete a mesma frase.",
            ])

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
                tools=LUNA_TOOLS,
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
                creation_keywords = ["criei", "salvei", "escrevi", "deletei", "mandei", "enviei", "alterei", "modifiquei"]
                if any(kw in assistant_content.lower() for kw in creation_keywords) and tools_executed_count == 0:
                    # O LLM está mentindo que fez algo sem ter usado ferramentas.
                    print("[Agente] ⚠️ Alucinação detectada: o modelo alega ter feito algo sem usar tools.")
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": "ERRO: Você disse que fez uma ação, mas não chamou nenhuma ferramenta. Se você quer criar/salvar/enviar algo, você DEVE chamar a função apropriada. Tente novamente usando tools."})
                    continue

            # Se não tem tool_calls, esta é a resposta final
            if not tool_calls_list:
                cleaned = assistant_content
                if "<think>" in cleaned:
                    cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL).strip()
                final_response = _sanitize_user_response(cleaned)
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
                    tool_results.append({"role": "tool", "content": msg, "name": name,
                                         "tool_call_id": getattr(tc, "id", f"blocked_{step}")})
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
                            tool_results.append({"role": "tool", "content": msg, "name": name,
                                                 "tool_call_id": getattr(tc, "id", f"denied_{step}")})
                            self._emit_progress("tool_done", name=name, label=label, ok=False)
                            continue

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
                        v = VerificationSystem.verify_directory_created(
                            str(VerificationSystem.WORKSPACE / pdir)
                        )
                        if v["success"]:
                            res += f" | VERIFICADO: {v['files_count']} arquivo(s)"
                        else:
                            res += f" | VERIFICAÇÃO: {v['reason']}"

                tool_results.append({
                    "role": "tool",
                    "content": res,
                    "name": name,
                    "tool_call_id": getattr(tc, "id", f"tc_{step}_{tools_executed_count}"),
                })
                tools_executed_count += 1

                self._trace_logger.add_step("tool_call", name, args_str, res, success)
                self._emit_progress("tool_done", name=name, label=label, ok=success)

            # Adiciona a mensagem do assistente (com tool_calls) + resultados ao histórico
            if tool_calls_list:
                msg_entry = {"role": "assistant", "content": assistant_content or None}
                if raw and isinstance(raw, dict) and hasattr(raw.get("message"), "tool_calls"):
                    msg_entry["tool_calls"] = [
                        {"id": tc.id, "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                         "type": "function"}
                        for tc in raw["message"].tool_calls
                    ]
                elif raw and isinstance(raw, dict):
                    msg_entry["tool_calls"] = [
                        {"id": tc.id, "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                         "type": "function"}
                        for tc in (raw.get("tool_calls") or [])
                    ]
                messages.append(msg_entry)
                messages.extend(tool_results)

            if step == max_steps - 1 and not final_response:
                final_response = "⚠️ Limite de passos atingido. Pode haver ações incompletas."

        # Fallback: se nunca teve resposta do LLM (só ferramentas), gera sumário
        if not final_response:
            tool_obs = [
                m.get("content", "") for m in messages
                if isinstance(m, dict) and m.get("role") == "tool"
            ] if tools_executed_count > 0 else []
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
            {"role": "user", "content": f"Mensagem de {user_name}: \"{text}\"\nContexto:\n{context}"}
        ]
        
        # Usa task_type command (temperatura baixa) para respostas factuais de ferramentas
        response = self._llm.generate(
            messages=messages,
            task_type="command",
            model=config.GEMINI_MODELS.get("main", config.GEMINI_MODELS["fallback"])
        )
        
        if isinstance(response, dict):
            response = response.get("message", {}).get("content", "")
            
        # 🚨 FILTRO ANTI-THINK (DeepSeek R1)
        if "<think>" in response:
            response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
            
        final_text = _sanitize_user_response(response)

        # Validação de alucinação pós-resposta (inspirada no format checker do Agent-S)
        hallucination_feedback = OutputValidator.check_hallucination(final_text, observations, user_text=text)
        if hallucination_feedback:
            print(f"[Reflection] ⚠️ Possível alucinação detectada: {hallucination_feedback}")
            # Se detectou alucinação, tenta gerar resposta corrigida
            corrected = self._llm.generate(
                messages=[
                    {"role": "system", "content": (
                        f"Você é Luna, assistente pessoal. Sua resposta anterior tinha um problema:\n"
                        f"{hallucination_feedback}\n\n"
                        f"RESULTADOS REAIS DAS AÇÕES:\n{obs_block}\n\n"
                        f"Gere uma resposta CORRIGIDA, honesta e direta baseada APENAS nos resultados reais."
                    )},
                    {"role": "user", "content": text}
                ],
                task_type="command",
                model=config.GEMINI_MODELS.get("main", config.GEMINI_MODELS["fallback"])
            )
            if isinstance(corrected, dict):
                corrected = corrected.get("message", {}).get("content", "")
            if corrected:
                final_text = _sanitize_user_response(corrected)

        if not observations and len(text.strip()) >= 20:
            self._auto_extract_facts(text, final_text)

        return final_text

    def _request_edit_permission(self, path: str, new_content: str) -> bool:
        """Solicita permissão do usuário antes de editar um arquivo."""
        from actions.filesystem import get_filesystem
        fs = get_filesystem()
        current = None
        try:
            raw = fs.read_text(path)
            if raw and not raw.startswith("FALHOU"):
                current = raw
        except Exception:
            pass

        print(f"\n{'='*60}")
        print(f"✏️  LUNA QUER EDITAR UM ARQUIVO")
        print(f"{'='*60}")
        print(f"Arquivo: {path}")
        if current is not None:
            preview = current[:1500]
            if len(current) > 1500:
                preview += "\n... [truncado]"
            print(f"\nConteúdo ATUAL:")
            print(f"{'─'*40}")
            print(preview)
        preview_new = new_content[:1500]
        if len(new_content) > 1500:
            preview_new += "\n... [truncado]"
        print(f"\nNovo conteúdo:")
        print(f"{'─'*40}")
        print(preview_new)
        print(f"{'='*60}")

        if self._confirm_edit_callback:
            return self._confirm_edit_callback(path, current, new_content)

        try:
            resp = input("\nProssigo com a edição? (s/N): ").strip().lower()
            return resp in ("s", "sim", "yes", "y")
        except (EOFError, OSError):
            return False

    def _classify_model_tier(self, text: str) -> dict:
        """
        Classifica qual tier/modelo usar baseado no conteúdo do texto.
        Usa o query_complexity do OpenJarvis para classificação inteligente.
        Retorna dict com: name, tails, flags (use_fast, use_heavy, use_basic).
        """
        from config import MODELS
        qi = classify_query(text)
        tier = qi.get("model_tier", "main")
        model_name = MODELS.get(tier, MODELS["main"])

        flags = {
            "use_heavy": tier == "heavy",
            "use_fast": tier == "fast",
            "use_basic": tier == "basic",
        }
        tails_map = {"fast": 2, "basic": 1, "main": 3, "heavy": 4}
        return {
            "name": model_name,
            "tails": tails_map.get(tier, 3),
            "flags": flags,
        }

    def _run_writer_stream(self, text: str) -> str:
        """Modo Escritor Engine: Planejamento -> Stream -> Refinamento."""
        from config import MODELS
        import re
        import threading
        
        model_key = self._writing_model
        model_name = MODELS[model_key]
        
        print(f"\n[Writer] Iniciando Engine Literária...")
        print(f"[Writer] Fase 1: Planejamento Arquitetural (Fast LLM)...")
        
        # Etapa 1: Planning
        plan_prompt = self._writer.build_planning_prompt(text)
        plan_text = self._llm.generate(plan_prompt, task_type="planning", model=MODELS.get("fast", model_name))
        print(f"[Writer] Estrutura montada.")

        # Etapa 2: Streaming Draft
        print(f"[Writer] Fase 2: Streaming Draft ({model_name})...")
        draft_prompt = self._writer.build_draft_prompt(plan_text, text)
        stream_gen = self._llm.generate(
            draft_prompt,
            task_type="creative",
            model=model_name,
            stream=True,
        )

        buffer = ""
        first_line_done = False
        filename = "texto_gerado.txt"
        f_handle = None
        filepath = None
        full_draft = ""

        for chunk in stream_gen:
            if str(chunk).startswith("[Erro"):
                return f"Falha na geração do texto: {chunk}"

            print(chunk, end="", flush=True)
            full_draft += chunk

            if not first_line_done:
                buffer += chunk
                if "\n" in buffer:
                    first_line, rest = buffer.split("\n", 1)
                    m = re.search(r'\[FILE:\s*(.+)\]', first_line, re.IGNORECASE)
                    if m:
                        raw = m.group(1).strip()
                        raw = re.sub(r'[\\/"\'\\[\\]{}]', '', raw).strip()
                        if raw:
                            filename = raw if raw.endswith(".txt") else raw + ".txt"

                    try:
                        f_handle, filepath = self._writer.open_file_for_stream(filename)
                        if rest and f_handle:
                            f_handle.write(self._writer.clean_chunk(rest))
                            f_handle.flush()
                    except Exception as e:
                        print(f"\n[Writer] Erro ao abrir arquivo: {e}")

                    first_line_done = True
            else:
                if f_handle:
                    f_handle.write(self._writer.clean_chunk(chunk))
                    f_handle.flush()

        print("\n[Writer] Streaming de Rascunho concluído!")
        if f_handle:
            f_handle.close()

        # Etapa 3: Refinamento Semântico em Background
        def bg_refine():
            print(f"\n[Writer] Fase 3: Refinamento Semântico Background inciado...")
            refiner_prompt = self._writer.build_refiner_prompt(full_draft)
            refined_text = self._llm.generate(
                refiner_prompt, 
                task_type="creative", 
                model=model_name
            )
            if filepath and filepath.exists() and len(refined_text) > 50:
                final_clean = self._writer.clean_chunk(refined_text)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(final_clean)
                print(f"[Writer] ✔ Refinamento concluído e salvo em {filename}.")

        if filepath:
            threading.Thread(target=bg_refine, daemon=True).start()

        model_label = "Alto (7B)" if model_key == "heavy" else "Médio (3B)"
        return (
            f"✍️ Rascunho escrito na tela! Arquivo: '{filename}' salvo na pasta de projetos. "
            f"\n💡 A inteligência de refinamento semântico está esculpindo a versão final do arquivo em background! [Modelo: {model_label}]"
        )

    # ── Etapas do pipeline ────────────────────────────────────

    def _reset_sticky_state(self) -> None:
        """Limpa estado que vaza entre mensagens/sessões."""
        self._dialog = {}
        self._pending_click = None
        if hasattr(self._executor, "web_manager"):
            self._executor.web_manager.last_search_query = ""

    def _handle_internal_command(self, text: str) -> tuple[Optional[str], Optional[bool]]:
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
            return self._daily_briefing(), None

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
                f"Tempo médio: {avg_req:.0f}ms | Modelo: {avg_mdl:.0f}ms | "
                f"Cache hits: {hits} | misses: {misses}"
            ), None

        return None, None

    def _daily_briefing(self) -> str:
        """Briefing diário estilo Jarvis: clima, calendário, lembretes, notas e frase do dia."""
        from datetime import datetime as _dt
        from actions.weather import get_weather
        from actions.reminders import get_reminders
        from actions.notes import get_notes
        from config import MODELS

        now = _dt.now()
        weekdays = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
        date_str = f"{weekdays[now.weekday()]}, {now.strftime('%d/%m/%Y')} — {now.strftime('%H:%M')}"

        # Clima nas duas cidades
        w_sp  = get_weather().get_weather("São Paulo")
        w_ita = get_weather().get_weather("Itapecerica da Serra")

        # Lembretes do dia
        reminders_raw = get_reminders().list_reminders()
        today_str = now.strftime("%d/%m")
        reminders_today = [
            line for line in reminders_raw.splitlines()
            if today_str in line or "Nenhum" in line
        ]
        reminders_text = "\n".join(reminders_today) if reminders_today else "Nenhum lembrete para hoje."

        # Notas recentes (últimas 3)
        notes_list = get_notes()._notes[-3:] if get_notes()._notes else []
        notes_text = "\n".join(f"  • {n}" for n in notes_list) if notes_list else "  Nenhuma nota recente."

        # Google Calendar — compromissos de hoje
        calendar_text = ""
        try:
            if self._executor.google and self._executor.google.available:
                cal_events = self._executor.google.get_today_events_formatted()
                if cal_events:
                    calendar_text = f"\nCOMPROMISSOS DE HOJE:\n{cal_events}\n"
        except Exception:
            pass

        # Frase motivacional do dia
        from brain.daily_routine import get_activity_logger
        patterns = get_activity_logger().get_patterns(days=3)
        activity_hint = ""
        if patterns.get("peak_hours"):
            peak = patterns["peak_hours"]
            activity_hint = f"\nDICA: Horários de pico de atividade do usuário: {', '.join(f'{h}h' for h in peak)} — pode sugerir algo produtivo nesses períodos."

        # Monta contexto para o LLM gerar o briefing no estilo Jarvis
        prompt = f"""Você é Luna, uma IA assistente pessoal com personalidade do Jarvis do Tony Stark — precisa, elegante, levemente irônica e sempre útil.

Gere um briefing diário completo e natural em português, como se estivesse falando diretamente com o usuário ao acordar. Use as informações abaixo. Seja concisa mas completa. Inclua uma frase motivacional ou curiosidade do dia no final. Tom: confiante, sofisticado, levemente bem-humorado.

DATA/HORA: {date_str}

CLIMA SÃO PAULO:
{w_sp}

CLIMA ITAPECERICA DA SERRA:
{w_ita}

LEMBRETES DE HOJE:
{reminders_text}

NOTAS RECENTES:
{notes_text}{calendar_text}{activity_hint}
Gere o briefing agora, direto ao ponto, sem introduções como "Claro!" ou "Aqui está:". Comece já com o briefing."""

        response = self._llm.generate(prompt, task_type="command", model=MODELS["main"])

        # Se o LLM retornou JSON (não deveria, mas por segurança)
        if response and response.strip().startswith("{"):
            import json as _json
            try:
                response = _json.loads(response).get("response", response)
            except Exception:
                pass

        return response or "Não consegui gerar o briefing agora. Tente novamente."

    def _build_context(self, text: str, mode: str = "", extra_context: str = "") -> str:
        """Monta contexto enxuto — memória + estado; vision/web só quando pedido.
        mode: "code", "write", "joy", ou "" (normal)
        extra_context: contexto adicional específico do modo
        """
        parts = []
        if extra_context:
            parts.append(f"[CONTEXTO DO MODO {mode.upper()}]\n{extra_context}")

        mem_ctx = self._memory.get_context_for_prompt(text)
        if mem_ctx:
            if len(mem_ctx) > 2800:
                mem_ctx = mem_ctx[:2800] + "\n[... memória truncada]"
            parts.append(mem_ctx)

        vision_triggers = [
            "tela", "vendo", "enxerga", "print", "screen", "vê", "monitor",
            "o que está aberto", "imagem", "gráfico", "video", "vídeo",
        ]
        wants_vision = any(w in text.lower() for w in vision_triggers)
        is_screenshot_only = bool(re.search(
            r'^\s*(?:luna[, ]+)?(?:tira(?:\s+um)?|faz(?:\s+um)?)\s+print',
            text.lower(),
        ))
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

        urls = re.findall(r'(https?://[^\s]+)', text)
        for url in urls[:1]:
            print(f"[Core] Lendo conteúdo da URL: {url}")
            page_content = self._executor.web_manager.read_page(url)
            if page_content:
                parts.append(
                    f"[CONTEÚDO DA URL: {url}]\n{page_content[:4000]}"
                )

        # Pesquisa web automática só quando o usuário pede informação factual externa
        web_info_kw = (
            "pesquisa", "pesquise", "busca", "busque", "notícia", "noticia",
            "quem é", "quem e", "o que é", "o que e", "quando foi", "onde fica",
            "preço de", "preco de", "cotação", "cotacao", "clima", "tempo hoje",
        )
        if any(kw in text.lower() for kw in web_info_kw) and not _is_local_action(text):
            search_data = self._quick_fact_check(text)
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
        talk_about_state = any(w in tl for w in [
            "timer", "alarme", "lembrete", "lembra", "compras",
            "foco", "pomodoro", "status", "o que tem", "o que está",
            "o que esta", "notificação", "notificacao", "aviso",
            "meu dia", "minhas coisas",
        ])
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

    def _quick_fact_check(self, query: str) -> str:
        """Busca rápida via Tavily AI (primário) com fallback Wikipedia + DuckDuckGo."""
        import urllib.request, urllib.parse, re, json, sqlite3, os
        from pathlib import Path

        # ── Cache SQLite ──────────────────────────────────────
        db_path = Path(__file__).parent / "brain" / "facts_cache.db"
        os.makedirs(db_path.parent, exist_ok=True)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS cache (query TEXT PRIMARY KEY, result TEXT, ts REAL)")

        stopwords = {"o","que","você","acha","do","da","de","um","uma","para","como",
                     "qual","quais","me","mim","eu","ele","ela","nós","é","foi","vai",
                     "ser","tem","por","sobre","ao","aos","das","dos","na","no","nas",
                     "nos","com","sem","isso","a","e","i"}
        words = re.findall(r'\b\w+\b', query.lower())
        clean_query = " ".join([w for w in words if len(w) > 1 and w not in stopwords])
        if not clean_query.strip():
            clean_query = query

        # Cache hit (TTL 6h)
        import time as _time
        cur.execute("SELECT result, ts FROM cache WHERE query=?", (clean_query,))
        row = cur.fetchone()
        if row and (_time.time() - row[1]) < 21600:
            conn.close()
            print(f"[🔍 Pesquisa] Cache hit: '{clean_query}'")
            return row[0]

        result_text = ""
        headers = {"User-Agent": "LunaAI/1.0", "Content-Type": "application/json"}

        # ── Primário: Tavily AI Search ────────────────────────
        try:
            from config import TAVILY_API_KEY
        except ImportError:
            TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

        if TAVILY_API_KEY:
            try:
                payload = json.dumps({
                    "api_key":        TAVILY_API_KEY,
                    "query":          query,
                    "search_depth":   "basic",
                    "max_results":    3,
                    "include_answer": True,
                }).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.tavily.com/search",
                    data=payload,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                answer = data.get("answer", "").strip()
                results = data.get("results", [])
                parts = []
                if answer:
                    parts.append(answer)
                for r in results[:2]:
                    content = r.get("content", "").strip()
                    if content:
                        parts.append(content[:300])
                if parts:
                    result_text = " | ".join(parts)
                    print(f"[🔍 Tavily] ✓ {len(results)} resultado(s)")
            except Exception as e:
                print(f"[🔍 Tavily] falhou: {e}")

        # ── Fallback: Wikipedia ───────────────────────────────
        if not result_text:
            wiki_url = (
                f"https://pt.wikipedia.org/w/api.php?action=query&list=search"
                f"&srsearch={urllib.parse.quote(clean_query)}&utf8=&format=json"
            )
            try:
                req = urllib.request.Request(wiki_url, headers={"User-Agent": "LunaAI/1.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                    items = data.get("query", {}).get("search", [])
                    if items:
                        snippets = [
                            f"{i['title']}: {re.sub(r'<[^>]+>', '', i['snippet'])}"
                            for i in items[:2]
                        ]
                        result_text = " | ".join(snippets)
                        print(f"[🔍 Wikipedia] {len(items)} resultado(s)")
            except Exception as e:
                print(f"[🔍 Wikipedia] falhou: {e}")

        # ── Fallback: DuckDuckGo ──────────────────────────────
        if not result_text:
            ddg_url = (
                f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_query)}"
                f"&format=json&no_html=1&skip_disambig=1"
            )
            try:
                req = urllib.request.Request(ddg_url, headers={"User-Agent": "LunaAI/1.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                parts = []
                if data.get("Answer"):
                    parts.append(data["Answer"])
                if data.get("AbstractText"):
                    parts.append(data["AbstractText"][:300])
                for r in data.get("RelatedTopics", [])[:2]:
                    if isinstance(r, dict) and r.get("Text"):
                        parts.append(r["Text"][:150])
                if parts:
                    result_text = " | ".join(parts)
                    print("[🔍 DuckDuckGo] resultado encontrado")
            except Exception as e:
                print(f"[🔍 DuckDuckGo] falhou: {e}")

        # Cache e retorno
        if result_text:
            try:
                cur.execute(
                    "INSERT OR REPLACE INTO cache (query, result, ts) VALUES (?, ?, ?)",
                    (clean_query, result_text, _time.time()),
                )
                conn.commit()
            except Exception:
                pass
        conn.close()
        return result_text


    def _filter_tools(self, prompt_text: str, context_text: str, all_tools: list) -> list:
        """
        Filtra dinamicamente a lista de ferramentas (LUNA_TOOLS) com base na intenção do usuário,
        evitando desperdício de tokens nos modelos gratuitos (Gemini/OpenRouter) e contornando
        o limite de TPM da Groq (6000 tokens).
        """
        if not all_tools:
            return []
            
        p_lower = prompt_text.lower()
        c_lower = context_text.lower() if context_text else ""
        full_text = f"{p_lower} {c_lower}"
        
        # Lista de verbos/ações que indicam que o usuário quer uma interação
        action_keywords = [
            "abre", "abrir", "inicia", "iniciar", "pesquisa", "pesquisar", "busca", "buscar", 
            "procura", "procurar", "clica", "clicar", "digita", "digitar", "roda", "rodar", 
            "executa", "executar", "comando", "terminal", "mostra", "mostrar", "veja", "ver", 
            "olha", "olhar", "clique", "spotify", "toca", "tocar", "musica", "música", 
            "playlist", "pausa", "parar", "luz", "lâmpada", "lampada", "desliga", "liga", 
            "temperatura", "clima", "tempo", "chove", "chuva", "previsão", "previsao", 
            "timer", "cronometro", "cronômetro", "minutos", "segundos", "lembrete", "lembrar", 
            "lembra", "anota", "anotar", "bloco", "nota", "compras", "compra", "mercado", 
            "planilha", "excel", "pdf", "briefing", "resumo", "hoje", "print", "screenshot", 
            "tela", "copia", "copiar", "colar", "email", "gmail", "agenda", "compromisso", 
            "evento", "drive", "pasta", "upload", "baixar", "download", "arquivo", 
            "escreva", "escrever", "crie", "criar", "desenvolva", "desenvolver", 
            "programe", "programar", "codigo", "código", "browser", "navegador", 
            "site", "url", "http", "www.", "janela", "maximize", "minimize", "fechar",
            "clipboard", "copie", "foco", "pomodoro"
        ]
        
        # Se não houver absolutamente nenhuma keyword de ação, assumimos conversa pura
        has_action = any(kw in full_text for kw in action_keywords)
        if not has_action:
            # Se for curto e sem ação, retorna lista vazia (sem ferramentas)
            # Poupa 7000 tokens por chat para Gemini/OpenRouter/Groq!
            if len(p_lower.split()) < 10 or any(p_lower.startswith(w) for w in ["oi", "olá", "como", "tudo", "quem"]):
                print("[Core Router] 🧠 Intenção Conversacional Pura detectada. Omitindo todas as ferramentas (Economia de ~6500 tokens).")
                return []
                
        # Base de ferramentas essenciais para ações em desktop (sempre presentes se houver ação)
        base_tool_names = {
            "open_app",
            "open_url",
            "search_web",
            "see_screen",
            "click_on_screen",
            "run_bash_command",
            "run_terminal_command"
        }
        
        # Mapeamento de keywords para ferramentas especializadas
        specialized_mappings = [
            # Spotify
            (["spotify", "toca", "tocar", "musica", "música", "playlist", "pausa", "parar"], ["control_spotify"]),
            # Luzes
            (["luz", "lâmpada", "lampada", "sala", "iluminação"], ["control_lights"]),
            # Clima
            (["tempo", "clima", "chuva", "temperatura", "chove", "previsão", "previsao"], ["get_weather"]),
            # Timer e Alarmes
            (["timer", "cronometro", "cronômetro", "segundos"], ["set_timer"]),
            # Lembretes
            (["lembra", "lembrete", "avisa", "avisar"], ["manage_reminder"]),
            # Notas
            (["nota", "anota", "bloco", "anotação", "anotacao"], ["manage_notes"]),
            # Lista de Compras
            (["compra", "mercado", "compras", "lista de compra"], ["manage_shopping_list"]),
            # Foco / Pomodoro
            (["foco", "pomodoro", "estudar", "concentrar"], ["manage_focus"]),
            # Briefing
            (["briefing", "resumo", "hoje", "dia"], ["get_daily_briefing"]),
            # Planilhas e Documentos
            (["excel", "planilha", "xls"], ["create_excel"]),
            (["pdf"], ["create_pdf_drive"]),
            # Gmail / Email
            (["gmail", "email", "mande", "enviar", "envie", "assunto", "corpo", "destinatario", "destinatário"], 
             ["google_query", "google_send_email", "google_search_emails", "google_read_email", 
              "google_reply_email", "google_forward_email", "google_mark_read", "google_delete_email", "google_list_files"]),
            # Calendar / Agenda
            (["agenda", "calendar", "compromisso", "evento", "data", "calendario", "calendário"], 
             ["google_query", "google_create_event", "google_edit_event", "google_delete_event", "google_events_by_date"]),
            # Google Drive / Arquivos em nuvem
            (["drive", "upload", "baixar", "pasta", "nuvem"], 
             ["google_drive_upload", "google_drive_list", "google_drive_search", "google_drive_create_folder", "google_drive_delete"]),
            # Screenshots
            (["print", "screenshot", "captura"], ["take_screenshot"]),
            # Clipboard
            (["copia", "copiar", "colar", "clipboard", "área de transferência", "area de transferencia"], ["clipboard_action"]),
            # Filesystem local
            (["arquivo", "txt", "ler", "salvar", "escrever", "escreva", "crie um arquivo", "pasta", "pastas", "home", "diretório", "diretorio", "workspace"], 
             ["read_file", "save_file", "filesystem", "google_list_files"]),
            # Window control
            (["janela", "maximize", "minimize", "workspace", "fechar janela"], ["control_window"]),
            # Browser task complexa
            (["browser", "navegador", "site", "url", "automatize", "clique no link", "clique no resultado"], ["run_browser_task", "click_web_result", "read_webpage"])
        ]
        
        selected_tool_names = set(base_tool_names)
        
        # Varre os mapeamentos e adiciona ferramentas extras se bater com a palavra-chave
        for keywords, tools in specialized_mappings:
            if any(kw in full_text for kw in keywords):
                selected_tool_names.update(tools)
                
        # Filtra a lista de ferramentas real com base nos nomes selecionados
        filtered = [t for t in all_tools if t.get("function", {}).get("name", "") in selected_tool_names]
        
        # Exibe métricas de otimização
        import json
        savings = len(all_tools) - len(filtered)
        print(f"[Core Router] 🔧 Otimização de Ferramentas: {len(filtered)} ativas (omitidas {savings}). Reduziu tokens de tools de ~6200 para ~{len(json.dumps(filtered)) // 4}!")
        
        return filtered


    def _auto_extract_facts(self, user_text: str, response: str) -> None:
        """Extrai fatos memoráveis via LLM em thread background."""
        if not user_text or len(user_text.strip()) < 10:
            return
        threading.Thread(
            target=self._llm_extract_facts_bg,
            args=(user_text,),
            daemon=True
        ).start()

    def _llm_extract_facts_bg(self, user_text: str) -> None:
        """
        Usa o modelo rápido para extrair fatos importantes do que o usuário disse.
        Roda em background para não atrasar a resposta.
        Só salva fatos com importance >= 0.85 para evitar poluição da memória.
        """
        try:
            from brain.llm import GROQ_MODELS, MODELS
            prompt = f"""Analise a mensagem do usuário e extraia APENAS informações factuais importantes sobre ele.
Ignore perguntas, pedidos, comandos, e conteúdo que não seja sobre o usuário em si.

REGRAS:
- Só extraia um fato se for uma INFORMAÇÃO PERMANENTE sobre o usuário (hardware, sistema, profissão, onde mora, preferências fortes, nome de projetos pessoais).
- NUNCA extraia: perguntas, comandos, conversas casuais, saudações, feedback, confirmações ("sim", "ok").
- NUNCA extraia explicações técnicas genéricas (ex: "ls lista arquivos").
- Se não houver NENHUM fato permanente, retorne {{"facts": []}}.

Mensagem do usuário: "{user_text}"

Responda APENAS com JSON. Se não houver fatos, retorne {{"facts": []}}.
Formato:
{{"facts": [
  {{"fact": "descrição clara do fato", "category": "hardware|preferencias|perfil|projeto|habitos|historia", "importance": 0.0-1.0}}
]}}

Importância: APENAS use 0.95 para informações técnicas críticas, 0.85 para preferências fortes e projetos pessoais. Ignore importance < 0.85."""

            fast_model = MODELS.get("fast", "qwen2.5:0.5b-instruct-fp16")
            # Força Ollama local — não consome quota do Gemini/Groq para tarefa de background
            raw = self._llm._generate_ollama(prompt, task_type="command", model=fast_model,
                                              stream=False, max_retries=1)

            if not raw:
                return

            import json as _json, re as _re
            # Extrai JSON da resposta
            json_match = _re.search(r'\{.*\}', str(raw), _re.DOTALL)
            if not json_match:
                return

            data = _json.loads(json_match.group())
            facts = data.get("facts", [])

            for item in facts:
                fact = item.get("fact", "").strip()
                category = item.get("category", "geral").strip()
                importance = float(item.get("importance", 0.5))

                # Ignora fatos de baixa importância ou genéricos
                if not fact or importance < 0.85:
                    continue
                # Ignora fatos que parecem perguntas, comandos ou conversas
                lower = fact.lower()
                if any(w in lower for w in ["?", "comando", "pergunta", "pedido", "ok ", "sim", "não"]):
                    continue

                self._memory.remember(fact, category=category, importance=importance)
                tag = "🔴" if importance >= 0.85 else "🟡"
                print(f"[Memory] {tag} Fato salvo ({category}, {importance:.2f}): {fact[:60]}")

        except Exception as e:
            # Não interfere na experiência do usuário
            pass


    # ── Interface de voz ──────────────────────────────────────

    def speak(self, text: str) -> None:
        """Fala o texto (não bloqueia). Permite interrupção por voz."""
        self._tts.speak(
            text, blocking=False,
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

    def _dialog_step(self, user_input: str) -> Optional[str]:
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
        from datetime import datetime as _dt, timedelta as _td
        import re as _re

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
                m = _re.search(r'(\d{1,2})[/\-](\d{1,2})', tl)
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
            m = _re.search(r'(\d{1,2})[h:](\d{0,2})', tl)
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
            import time; time.sleep(0.5)
            self._llm._stop_flag = False
        threading.Thread(target=_reset, daemon=True).start()

    def listen(self) -> Optional[str]:
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

_luna_instance: Optional[LunaCore] = None
_luna_lock = threading.Lock()


def get_luna() -> LunaCore:
    """Retorna a instância singleton de LunaCore."""
    global _luna_instance
    if _luna_instance is None:
        with _luna_lock:
            if _luna_instance is None:
                _luna_instance = LunaCore()
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
    for text, expected_action in tests:
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
    print(f"   LUNA — Sistema Autônomo Inteligente")
    print("=" * 60)
    print("  Comandos: 'status', 'apps', 'ouvir', 'falar', 'sair'")
    print("=" * 60 + "\n")
    
    luna.speak("Sistemas online. Pronta para ajudar.", )

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
