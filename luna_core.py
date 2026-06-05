#!/usr/bin/env python3
"""
luna_core.py — Cérebro central da Luna (Singleton)

Arquitetura limpa:
  - Uma única instância global (sem duplicação)
  - Pipeline: Input → Intenção → Plano → Ações → Resposta
  - ReAct loop real para agente autônomo
  - Sem gambiarras: cada módulo tem responsabilidade única
"""
import json
import re
import time
import threading
import sys
from typing import Optional
from pathlib import Path

# ── Módulos internos ──────────────────────────────────────────
from brain.planner import generate_plan, format_plan_for_prompt
from brain.scheduler import select_tools
from brain.llm import get_llm, MODELS, GROQ_MODELS, GEMINI_MODELS
from brain.memory import get_memory
from voice.tts import get_tts
from voice.stt import get_stt
from actions.executor import get_executor
from actions.writer import get_writer
from brain.dictionary import get_dictionary
from vision.screen import get_vision
from performance_cache import SmartCache, PerformanceMonitor
from output_parser import OutputParser


# ── Personalidade da Luna ─────────────────────────────────────
PERSONALITY_FILE = Path(__file__).parent / "personality.json"
USER_PROFILE_FILE = Path(__file__).parent / "user_profile.json"

# Comandos locais — não disparam fact-check web nem extração de memória
_LOCAL_ACTION_KEYWORDS = (
    "print", "screenshot", "captura", "tira um print", "tira print",
    "timer", "toca", "abre", "fecha", "clica", "digita", "whatsapp",
    "manda", "envia", "pesquisa", "busca", "lista", "lembret", "nota",
    "luz", "volume", "workspace", "mata", "processo", "brilho", "copia",
    "clipboard", "arquivo", "pasta", "screenshot", "print da tela",
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

    t = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", t, flags=re.DOTALL).strip()
    return t.strip() or "Pronto."


def _extract_tool_calls_from_text(raw: str) -> list:
    """Recupera tool_calls quando o modelo vaza JSON no texto em vez de usar a API nativa."""
    if not raw or "tool_calls" not in raw:
        return []
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
    # Fallback regex quando JSON está malformado
    names = re.findall(r'"name"\s*:\s*"(\w+)"', raw)
    if not names:
        return []
    args_m = re.search(r'"arguments"\s*:\s*"(\{.*?\})"', raw)
    args = args_m.group(1).replace('\\"', '"') if args_m else "{}"
    return [{
        "id": f"parsed_{int(time.time())}",
        "type": "function",
        "function": {"name": names[0], "arguments": args},
    }]

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
3. Para interagir com o sistema, abrir sites, e-mails, arquivos, agenda ou tocar música, VOCÊ DEVE USAR A FERRAMENTA (TOOL) correta fornecida. Não explique que vai usar a ferramenta, apenas use.
4. Não invente informações. Se não souber, diga claramente. Para cálculos, CALCULE E MOSTRE o número imediatamente.
5. Respostas de voz devem ser curtas e naturais (máx 2-3 frases). Não use listas complexas quando puder evitar.
6. Sugira um próximo passo útil quando fizer sentido (proatividade).
7. Você é um AGENTE AUTÔNOMO: recebeu uma tarefa → use a ferramenta certa → reporte o resultado concreto. Nunca diga "vou fazer" sem executar.
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

        # Carrega personalidade
        self._persona_name = self._load_persona()

        # Limpa cache expirado ao iniciar
        expired = self._cache.clear_expired()
        if expired > 0:
            print(f"[Luna] Cache: {expired} entradas expiradas removidas")

        cache_count = len(self._cache.cache.get("entries", {}))
        print(f"[Luna] ✓ Sistema pronto. Modelos: {', '.join(MODELS.values())}")
        print(f"[Luna] ✓ Cache: {cache_count} entradas | Memória: {self._memory.stats()}")

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

    def process(self, text: str, progress_callback=None) -> str:
        """
        Processa uma entrada do usuário e retorna a resposta.
        Pipeline: texto → intenção → plano → ações → resposta
        progress_callback: fn(dict) para eventos em tempo real (SSE/desktop).
        """
        if not text or not text.strip():
            return ""

        # Sanitização: colapsa espaços, remove caracteres de controle invisíveis
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        text = re.sub(r'[ \t]+', ' ', text).strip()
        if not text:
            return ""

        # Segurança cognitiva: filtra inputs perigosos antes de processar
        from brain.safety import check_safety
        safety_response = check_safety(text)
        if safety_response:
            return safety_response

        with self._lock:
            self.processing = True
            self._progress_callback = progress_callback
            self._emit_progress("thinking", label="Pensando...")
            try:
                return self._run_pipeline(text)
            except Exception as e:
                print(f"[Luna] Erro no pipeline: {e}")
                import traceback; traceback.print_exc()
                return "Ocorreu um erro interno. Tente novamente."
            finally:
                self.processing = False
                self.current_action = None
                self._progress_callback = None

    def _run_pipeline(self, text: str) -> str:
        """Pipeline completo de processamento. Fases numeradas para clareza."""
        self._last_was_cached = False
        timer_start = self._perf.start_timer()

        # ══ FASE -1: Diálogo guiado (formulários multi-turno — ainda usa LLM no fim) ══
        if hasattr(self, '_dialog') and self._dialog:
            result = self._dialog_step(text)
            if result:
                elapsed = self._perf.end_timer(timer_start, "request_times")
                self.last_metrics = {"time_ms": elapsed, "model": "Dialog", "tails": 0}
                return result

        # ══ Clique pendente → agente (não executa OCR sem pensar) ══
        if self._pending_click:
            target = self._pending_click
            self._pending_click = None
            text = (
                f"[Clique pendente] Elemento: «{target}». "
                f"O usuário indicou app/janela: «{text.strip()}». "
                f"Use focus_window e click_on_screen para concluir."
            )

        # ══ Meta/admin local (sem ação no PC — só dados da Luna) ══
        internal, conv_signal = self._handle_internal_command(text)
        if internal is not None:
            elapsed = self._perf.end_timer(timer_start, "request_times")
            self.last_metrics = {"time_ms": elapsed, "model": "Interno", "tails": 0,
                                 "conv": conv_signal}
            return internal

        # ══ FASE 1: Escritor (usa LLM dedicado) ══
        if self._writer.is_writing_request(text):
            print(f"[Router] FASE 1 — Escritor Engine ativado! Modelo: {self._writing_model}")
            response = self._run_writer_stream(text)
            self._memory.add_exchange(text, response)
            elapsed = self._perf.end_timer(timer_start, "request_times")
            self.last_metrics = {"time_ms": elapsed, "model": "Escritor", "tails": 4}
            return response

        # ══ FASE 2: (desativada) ══

        # ══ FASE 4: Cache desativado ══
        cached = None
        if cached:
            print(f"[Cache] ⚡ HIT! Resposta cacheada.")
            response = cached["response"]
            self._memory.add_exchange(text, response)
            self._last_was_cached = True
            self._perf.record_cache_event(hit=True)
            elapsed = self._perf.end_timer(timer_start, "request_times")
            self.last_metrics = {"time_ms": elapsed, "model": "Cache", "tails": 0}
            return response
        self._perf.record_cache_event(hit=False)

        # ══ FASE 5: Agente — toda ação no PC passa pelo LLM + ferramentas ══
        if not self._llm.is_ready():
            elapsed = self._perf.end_timer(timer_start, "request_times")
            self.last_metrics = {"time_ms": elapsed, "model": "offline", "tails": 0, "conv": None}
            return (
                "Não consigo agir agora: o modelo de IA não está disponível. "
                "Verifique Ollama (localhost:11434) ou a chave Groq no .env."
            )

        if not self.in_conversation_mode:
            self.in_conversation_mode = True
            print("[Router] Modo conversa — agente com ferramentas.")
        context = self._build_context(text)
        model_tier = self._classify_model_tier(text)
        print(f"[Router] FASE 5 — Modelo: {model_tier['name']}")

        model_timer = self._perf.start_timer()
        llm_result = self._call_llm(text, context, **model_tier["flags"])
        self._perf.end_timer(model_timer, "model_times")

        llm_result["_user_text"] = text

        response = self._finalize_response(llm_result)
        response = _sanitize_user_response(response)
        self._memory.add_exchange(text, response)

        elapsed = self._perf.end_timer(timer_start, "request_times")
        print(f"[Perf] Total: {elapsed:.0f}ms")
        self.last_metrics = {
            "time_ms": elapsed,
            "model": model_tier["name"],
            "tails": model_tier["tails"],
            "conv": self.in_conversation_mode
        }
        return response

    def _classify_model_tier(self, text: str) -> dict:
        """
        Classifica qual tier/modelo usar baseado no conteúdo do texto.
        Retorna dict com: name, tails, flags (use_fast, use_heavy, use_basic).
        """
        from config import MODELS
        tl = text.lower()

        # 4 Caudas — Pesado (7B): código, análise, desenvolvimento
        heavy_kw = [
            "código", "programe", "analise", "resumo detalhado", "resuma", "explique detalhadamente",
            "traduza", "html", "python", "script", "desenvolva", "crie um arquivo",
            "javascript", "css", "aplicativo", "refatore",
        ]
        # "jogo", "site", "calculadora" só ativam heavy se há intenção clara de desenvolvimento
        heavy_dev_kw = ["jogo", "site", "calculadora"]
        is_dev_request = len(text) > 40 and any(
            w in tl for w in ["crie", "faça", "desenvolva", "programe", "escreva", "construa"]
        )
        if (
            any(w in tl for w in heavy_kw) or
            (is_dev_request and any(w in tl for w in heavy_dev_kw))
        ):
            return {"name": MODELS["heavy"], "tails": 4,
                    "flags": {"use_fast": False, "use_heavy": True, "use_basic": False}}

        # 3 Caudas (3B): conversa e agente — padrão equilibrado
        return {"name": MODELS["main"], "tails": 3,
                "flags": {"use_fast": False, "use_heavy": False, "use_basic": False}}

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
        """Briefing diário estilo Jarvis: clima, lembretes, notas e frase do dia."""
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
{notes_text}

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

    def _build_context(self, text: str) -> str:
        """Monta contexto enxuto — memória + estado; vision/web só quando pedido."""
        parts = []

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

        system_state = self._get_system_state_context()
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

    def _get_system_state_context(self) -> str:
        """Retorna estado atual do sistema (timers, lembretes, lista) para o contexto do LLM."""
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
            (["arquivo", "txt", "ler", "salvar", "escrever", "escreva", "crie um arquivo", "pasta local", "workspace"], 
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


    def _call_llm(self, text: str, context: str, use_fast: bool = False, use_heavy: bool = False, use_basic: bool = False) -> dict:
        """
        ARQUITETURA HIERÁRQUICA (3 Camadas):
        1. Planner (Llama 70B): Gera o plano estratégico.
        2. Scheduler (Llama 70B/8B): Escolhe as ferramentas.
        3. Executor (Gemini 2.5 Flash): Executa e responde.
        """
        # Verifica se é estritamente uma solicitação de programação
        is_coding_file = use_heavy and any(w in text.lower() for w in ["código", "programe", "script", "desenvolva", "crie um arquivo", "html", "javascript", "python", "css", "aplicativo", "jogo", "site"])

        if is_coding_file:
            return self._run_coding_bypass(text)

        # ══ FASE 1: Planner (Llama 70B) ══
        self._emit_progress("thinking", label="Planejando estratégia...")
        plan_json = generate_plan(text, context)
        print(f"[Planner] Plano: {plan_json.get('goal')}")
        
        # Se não precisa de ferramentas, vai direto para o Executor
        if not plan_json.get("needs_tools", True):
            print("[Planner] Conversa pura detectada. Pulando ferramentas.")
            return self._run_executor_layer(text, context, plan_json, tool_results=[])

        # ══ FASE 2: Scheduler (Llama 70B/8B) ══
        self._emit_progress("thinking", label="Selecionando ferramentas...")
        scheduler_json = select_tools(plan_json, text, context)
        tools_to_call = scheduler_json.get("tools_to_call", [])
        
        if not tools_to_call:
            print("[Scheduler] Nenhuma ferramenta selecionada.")
            return self._run_executor_layer(text, context, plan_json, tool_results=[])

        # ══ FASE 3: Execução de Ferramentas ══
        from brain.agent_tools import execute_tool_call, is_tool_success, tool_call_id
        
        tool_results = []
        tools_executed_count = 0
        
        print(f"[Scheduler] Executando {len(tools_to_call)} ferramentas em modo {scheduler_json.get('execution_mode', 'sequential')}...")
        
        for t_info in tools_to_call:
            name = t_info["tool_name"]
            params = t_info.get("parameters", {})
            explanation = t_info.get("explanation", "")
            
            label = _tool_progress_label(name, params)
            self._emit_progress("tool_start", name=name, label=label)
            
            # Mock de NormalizedToolCall para compatibilidade com execute_tool_call
            class MockTC:
                def __init__(self, n, a):
                    self.id = f"call_{int(time.time())}_{n}"
                    self.function = type('obj', (object,), {'name': n, 'arguments': json.dumps(a)})
            
            tc = MockTC(name, params)
            res = execute_tool_call(self._executor, tc)
            
            tool_results.append({
                "tool": name,
                "params": params,
                "result": str(res),
                "success": is_tool_success(res)
            })
            
            self._emit_progress("tool_done", name=name, label=label, ok=is_tool_success(res))
            if is_tool_success(res):
                tools_executed_count += 1

        # ══ FASE 4: Executor (Gemini 2.5 Flash) ══
        self._emit_progress("thinking", label="Sintetizando resposta...")
        return self._run_executor_layer(text, context, plan_json, tool_results, tools_executed_count)

    def _run_coding_bypass(self, text: str) -> dict:
        """Mantém a funcionalidade original de bypass de código via stream."""
        print("[Router] Bypass de JSON Ativado: Redirecionando saída bruta para o disco via Stream!")
        prompt = f"""Você é um Programador Nível Sênior Absoluto. Cumpra com o pedido fornecendo APENAS E RESTRITAMENTE O CÓDIGO FONTE FINAL. Sem textos de introdução, sem markdown (```), apenas código rodável.
Regra Magna: Sua PRIMEIRA LINHA OBRIGATÓRIA escrita deve ser exata e unicamente neste formato: [FILE: nomedoarquivo.extensao]
A partir da segunda linha, todo o código.

Pedido do usuário: {text}"""

        coder_model = MODELS["heavy"]
        if self._llm._use_groq("coding"):
            coder_model = GROQ_MODELS["heavy"]
            print(f"[Coder] Usando Groq: {coder_model}")
        else:
            print(f"[Coder] Usando Ollama: {coder_model} (Aguarde o modelo aquecer...)")

        stream_gen = self._llm.generate(prompt, task_type="coding", model=coder_model, stream=True)

        buffer = ""
        first_line_done = False
        filename = "script_gerado_sem_nome.txt"
        f_handle = None

        for chunk in stream_gen:
            if str(chunk).startswith("[Erro"):
                return {"action": "conversar", "params": {}, "response": f"Falha na geração de código: {chunk}"}
            
            print(chunk, end="", flush=True)
            
            if not first_line_done:
                buffer += chunk
                if "\n" in buffer:
                    first_line, rest = buffer.split("\n", 1)
                    import re
                    m = re.search(r'\[FILE:\s*(.+)\]', first_line, re.IGNORECASE)
                    if m:
                        filename = m.group(1).strip()
                        filename = re.sub(r'[\\/\"\'\[\]\{\}]', '', filename)
                    
                    try:
                        f_handle, filepath = self._executor.open_code_file_stream(filename)
                        if rest and f_handle:
                            f_handle.write(rest)
                            f_handle.flush()
                    except Exception as e:
                        print(f"\n[Stream] Erro ao abrir arquivo: {e}")
                    first_line_done = True
            else:
                if f_handle:
                    chunk_limpo = chunk.replace("```html", "").replace("```python", "").replace("```", "")
                    f_handle.write(chunk_limpo)
                    f_handle.flush()
        
        print("\n[Coder] Streaming concluído!")
        if f_handle:
            f_handle.close()
            return {"action": "conversar", "params": {}, "response": f"Concluído! O código foi escrito em {filename}."}
        return {"action": "conversar", "params": {}, "response": "Erro ao abrir arquivo para escrita."}

    def _run_executor_layer(self, text: str, context: str, plan_json: dict, tool_results: list, tools_count: int = 0) -> dict:
        """Camada final: Gemini 2.5 Flash gera a resposta natural."""
        plan_block = format_plan_for_prompt(plan_json)
        results_block = "\n[RESULTADOS DAS FERRAMENTAS]\n"
        if not tool_results:
            results_block += "Nenhuma ferramenta foi executada.\n"
        else:
            for r in tool_results:
                status = "Sucesso" if r["success"] else "Falha"
                results_block += f"- {r['tool']}: {status}\n  Resultado: {r['result']}\n"

        user_name = self.user_profile.get("user_name", "você")
        system_prompt = (
            f"Você é Luna, uma assistente pessoal autônoma.\n"
            f"Sua tarefa é responder ao usuário de forma natural em português.\n"
            f"Use o PLANO e os RESULTADOS DAS FERRAMENTAS para compor sua resposta.\n"
            f"NUNCA responda com JSON ou nomes técnicos de ferramentas.\n"
            f"Seja concisa e prestativa.\n\n"
            f"{plan_block}\n"
            f"{results_block}\n"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Mensagem de {user_name}: \"{text}\"\nHistórico:\n{context}"}
        ]
        
        response = self._llm.generate(
            messages=messages,
            task_type="conversational",
            model=GEMINI_MODELS.get("main", "gemini-2.5-flash")
        )
        
        if isinstance(response, dict):
            response = response.get("message", {}).get("content", "")
            
        return _agent_result(
            {"action": "conversar", "params": {}, "response": _sanitize_user_response(response)},
            tools_count
        )

    def _parse_llm_response(self, raw: str, user_text: str = "") -> dict:
        """Parseia JSON da resposta do LLM com múltiplas tentativas."""
        if not raw:
            return self._fallback_response(user_text)

        # Tenta extrair JSON do texto bruto (modelo pode adicionar texto de markdown ao redor)
        attempts = [raw]
        
        # Tenta extrair explicitamente o bloco de código
        m = re.search(r'```(?:json)?\s*(\{.*\})\s*```', raw, re.DOTALL)
        if m:
            attempts.insert(0, m.group(1))

        # Pega do primeiro '{' até o último '}' para envolver tudo (mesmo se tiver código com chaves dentro)
        m2 = re.search(r'(\{.*\})', raw, re.DOTALL)
        if m2:
            attempts.insert(0, m2.group(1))

        for attempt in attempts:
            try:
                data = json.loads(attempt)
                # Valida estrutura mínima
                if "action" in data and "response" in data:
                    data.setdefault("params", {})
                    data["action"] = "conversar"
                    return data
                # JSON com action mas sem response — gera response padrão
                if "action" in data and "action" != "conversar":
                    data.setdefault("params", {})
                    data.setdefault("response", "")
                    return data
            except (json.JSONDecodeError, Exception):
                continue

        # Se nenhuma tentativa funcionou, trata como resposta de conversa
        # (modelo respondeu em texto puro, ainda é útil)
        if raw and len(raw) > 5:
            return {
                "action": "conversar",
                "params": {},
                "response": raw.strip()
            }

        return self._fallback_response(user_text)

    def _fallback_response(self, text: str) -> dict:
        """Resposta de fallback quando LLM falha."""
        if not self._llm.is_ready():
            return {
                "action": "conversar",
                "params": {},
                "response": "Não consigo me conectar ao LLM. Verifique se o Ollama está rodando."
            }
        return {
            "action": "conversar",
            "params": {},
            "response": "Desculpe, não entendi. Pode reformular?"
        }

    def _finalize_response(self, llm_result: dict) -> str:
        """Resposta final sanitizada — ações já foram executadas via ferramentas."""
        base_response = llm_result.get("response", "") or ""
        action = llm_result.get("action", "conversar")
        user_text = llm_result.get("_user_text", "")
        tools_ran = llm_result.get("tools_executed", 0) > 0

        if (
            action == "conversar"
            and base_response
            and not tools_ran
            and not _is_local_action(user_text)
            and len(user_text.strip()) >= 20
        ):
            self._auto_extract_facts(user_text, base_response)

        return _sanitize_user_response(base_response) or "Entendido."

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
        Usa o modelo rápido (8B) para extrair fatos importantes do que o usuário disse.
        Roda em background para não atrasar a resposta.
        """
        try:
            from brain.llm import GROQ_MODELS, MODELS
            prompt = f"""Analise a mensagem do usuário e extraia APENAS informações factuais importantes sobre ele.
Ignore perguntas, pedidos, e conteúdo que não seja sobre o usuário em si.

Exemplos de informações IMPORTANTES: hardware do PC, sistema operacional, onde mora, profissão, preferências, projetos, hábitos.
Exemplos de informações SEM IMPORTÂNCIA: perguntas genéricas, pedidos de ajuda, conversas normais.

Mensagem do usuário: "{user_text}"

Responda APENAS com JSON válido. Se não houver fatos relevantes, retorne {{"facts": []}}.
Formato:
{{"facts": [
  {{"fact": "descrição clara do fato", "category": "hardware|preferencias|perfil|projeto|habitos|historia", "importance": 0.0-1.0}}
]}}

Importância: 0.95 = informação técnica/pessoal crítica (hardware, sistema), 0.85 = preferência forte, 0.7 = informação útil"""

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
                importance = float(item.get("importance", 0.7))

                if not fact or importance < 0.65:
                    continue

                self._memory.remember(fact, category=category, importance=importance)
                tag = "🔴" if importance >= 0.85 else "🟡"
                print(f"[Memory] {tag} Fato salvo ({category}, {importance:.2f}): {fact[:60]}")

        except Exception as e:
            # Não interfere na experiência do usuário
            pass


    # ── Interface de voz ──────────────────────────────────────

    def speak(self, text: str) -> None:
        """Fala o texto (não bloqueia)."""
        self._tts.speak(text, blocking=False)

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
