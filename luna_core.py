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
from brain.llm import get_llm, MODELS
from brain.memory import get_memory
from voice.tts import get_tts
from voice.stt import get_stt
from actions.executor import get_executor
from actions.writer import get_writer
from brain.dictionary import get_dictionary
from vision.screen import get_vision
from performance_cache import SmartCache, PerformanceMonitor
from output_parser import OutputParser
from config import AGENT_MODE


# ── Personalidade da Luna ─────────────────────────────────────
PERSONALITY_FILE = Path(__file__).parent / "personality.json"
USER_PROFILE_FILE = Path(__file__).parent / "user_profile.json"

SYSTEM_PROMPT = """Você é Luna, uma assistente pessoal brasileira autônoma inteligente criada pelo Pera.
Você é mulher, 28 anos, madura, calma, sincera e inteligente. Você fala de forma natural e espontânea, sem soar robótica.
Você responde SEMPRE em português brasileiro (pt-BR).
Você POSSUI acesso total ao sistema operacional e contas do usuário, mas depende EXCLUSIVAMENTE de ferramentas (tool calls) para interagir com eles.

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
        self.agent_mode = AGENT_MODE
        self.in_conversation_mode = False
        self.user_profile = self._load_user_profile()
        self._pending_click: Optional[str] = None  # alvo de clique aguardando app

        # Seletor de modelo: "main" (médio 3B) ou "heavy" (alto 7B)
        self._writing_model: str = "main"  # default: médio

        # Estado
        self.processing = False
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
        print(f"[Luna] ✓ Modo agente: {'ON' if self.agent_mode else 'OFF'} | Cache: {cache_count} entradas | Memória: {self._memory.stats()}")

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

    def process(self, text: str) -> str:
        """
        Processa uma entrada do usuário e retorna a resposta.
        Pipeline: texto → intenção → plano → ações → resposta
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
            try:
                return self._run_pipeline(text)
            except Exception as e:
                print(f"[Luna] Erro no pipeline: {e}")
                import traceback; traceback.print_exc()
                return "Ocorreu um erro interno. Tente novamente."
            finally:
                self.processing = False

    def _run_pipeline(self, text: str) -> str:
        """Pipeline completo de processamento. Fases numeradas para clareza."""
        self._last_was_cached = False
        timer_start = self._perf.start_timer()

        # ══ FASE -1: Diálogo guiado (coleta de dados passo a passo) ══
        if hasattr(self, '_dialog') and self._dialog:
            result = self._dialog_step(text)
            if result:
                elapsed = self._perf.end_timer(timer_start, "request_times")
                self.last_metrics = {"time_ms": elapsed, "model": "Dialog", "tails": 0}
                return result

        # ══ FASE 0: Comandos internos (sem LLM, instantâneo) ══
        # Resolve clique pendente: usuário respondeu com o nome do app
        if self._pending_click:
            target = self._pending_click
            self._pending_click = None
            app_name = text.strip()
            # Foca o app e clica
            import subprocess as _sp
            try:
                _sp.Popen(["wmctrl", "-a", app_name], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                import time; time.sleep(0.4)
            except Exception:
                pass
            result = self._executor.click_text(target)
            msg = result.get("message", f"Clicando em '{target}' no app '{app_name}'.")
            elapsed = self._perf.end_timer(timer_start, "request_times")
            self.last_metrics = {"time_ms": elapsed, "model": "Bypass", "tails": 1, "conv": None}
            return msg

        internal, conv_signal = self._handle_internal_command(text)
        if internal is not None:
            elapsed = self._perf.end_timer(timer_start, "request_times")
            self.last_metrics = {"time_ms": elapsed, "model": "Interno", "tails": 0,
                                 "conv": conv_signal}
            return internal

        # ══ FASE 1: Escritor Engine (pipeline criativo com streaming) ══
        if self._writer.is_writing_request(text):
            print(f"[Router] FASE 1 — Escritor Engine ativado! Modelo: {self._writing_model}")
            response = self._run_writer_stream(text)
            self._memory.add_exchange(text, response)
            elapsed = self._perf.end_timer(timer_start, "request_times")
            self.last_metrics = {"time_ms": elapsed, "model": "Escritor", "tails": 4}
            return response

        # ══ FASE 2: Ações diretas por palavra-chave (sem LLM) ══
        # Comandos de pesquisa e clique são tratados aqui diretamente —
        # isso garante execução REAL na tela sem overhead de LLM.
        # No modo agente/conversa, pula — deixa o LLM orquestrar via ferramentas.
        if not self.agent_mode and not self.in_conversation_mode:
            direct = self._executor.execute_natural(text)
            if direct.get("success"):
                response = direct.get("message", "Feito.")
                self._memory.add_exchange(text, response)
                elapsed = self._perf.end_timer(timer_start, "request_times")
                self.last_metrics = {"time_ms": elapsed, "model": "Executor Direto", "tails": 1,
                                     "conv": self.in_conversation_mode}
                return response

        # ══ FASE 3: Dicionário local (sem LLM) ══
        word = self._dictionary.is_dict_request(text)
        if word:
            print(f"[Router] FASE 3 — Dicionário: '{word}'")
            response = self._dictionary.lookup(word)
            # Se a API falhou (retornou fallback), usa modelo 0.5B para definir
            if "Não encontrei" in response or "dicionário online" in response:
                from config import MODELS
                prompt = (
                    f"Defina a palavra '{word}' em português de forma direta e concisa: "
                    f"significado, classe gramatical e um exemplo de uso. Máximo 3 linhas."
                )
                response = self._llm.generate(prompt, task_type="command", model=MODELS["fast"])
                response = re.sub(r'\{.*?\}', '', response, flags=re.DOTALL).strip() or response
            self._memory.add_exchange(text, response)
            elapsed = self._perf.end_timer(timer_start, "request_times")
            self.last_metrics = {"time_ms": elapsed, "model": "Dicionário", "tails": 1}
            return response

        # ══ FASE 4: Cache inteligente (desativado no modo agente — respostas dinâmicas) ══
        cached = None if self.agent_mode else self._cache.get(text)
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

        # ══ FASE 5: Contexto + Roteamento de Modelo + LLM ══
        context = self._build_context(text)
        model_tier = self._classify_model_tier(text)
        print(f"[Router] FASE 5 — Modelo selecionado: {model_tier}")

        model_timer = self._perf.start_timer()
        llm_result = self._call_llm(text, context, **model_tier["flags"])
        self._perf.end_timer(model_timer, "model_times")

        # Validar confiança da resposta
        confidence = self._parser.detect_confidence(llm_result.get("response", ""))
        print(f"[Parser] Confiança: {confidence.value}")

        # Executar ação
        action_result = self._execute_action(llm_result, text)

        # Finalizar resposta
        llm_result["_user_text"] = text
        response = self._finalize_response(llm_result, action_result)
        self._memory.add_exchange(text, response)

        # Cache apenas para conversa com alta confiança (e que não seja um fallback de erro)
        action = llm_result.get("action", "conversar")
        is_fallback = "desculpe" in response.lower() and "entendi" in response.lower()
        is_raw_json = response.strip().startswith("{") and response.strip().endswith("}")
        if action == "conversar" and response and len(response) > 10 and not is_fallback and not is_raw_json:
            cache_confidence = 0.9 if confidence.value == "high" else 0.6
            self._cache.set(text, response, confidence=cache_confidence)

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
        if not self.in_conversation_mode and (
            any(w in tl for w in heavy_kw) or
            (is_dev_request and any(w in tl for w in heavy_dev_kw))
        ):
            return {"name": MODELS["heavy"], "tails": 4,
                    "flags": {"use_fast": False, "use_heavy": True, "use_basic": False}}

        # 2 Caudas Rápidas (0.5B): ações de UI simples
        fast_kw = ["pesquise", "busque", "clique", "clica", "digite", "digita",
                   "ver a tela", "olhe a tela", "abra o site"]
        if any(w in tl for w in fast_kw) and not self.in_conversation_mode:
            return {"name": MODELS["fast"], "tails": 2,
                    "flags": {"use_fast": True, "use_heavy": False, "use_basic": False}}

        # 2 Caudas Básicas (0.5B): consultas factuais leves
        basic_kw = ["quem é", "quem foi", "o que é", "onde fica", "quando foi",
                    "história de", "wikipedia", "britanica"]
        if any(w in tl for w in basic_kw) and not self.in_conversation_mode:
            return {"name": MODELS.get("basic", "qwen2.5:0.5b"), "tails": 2,
                    "flags": {"use_fast": False, "use_heavy": False, "use_basic": True}}

        # Modo Conversa — Usa 8B para ser rápido e sem rate limit
        if self.in_conversation_mode:
            return {"name": MODELS["main"], "tails": 3,
                    "flags": {"use_fast": False, "use_heavy": False, "use_basic": False}}

        # 3 Caudas (3B): chat padrão equilibrado
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

    def _handle_internal_command(self, text: str) -> tuple[Optional[str], Optional[bool]]:
        """
        Comandos que não precisam do LLM.
        Retorna (resposta, conv_signal) onde conv_signal:
          True  → abrir painel de conversa
          False → fechar painel de conversa
          None  → sem mudança de modo
        """
        tl = text.lower().strip()

        if tl in ("sair", "exit", "tchau"):
            return "Até logo!", None

        # ── Clique inteligente — intercepta antes do LLM ──────
        import re as _re, unicodedata as _ud
        def _n(s):
            return ''.join(c for c in _ud.normalize('NFD', s) if _ud.category(c) != 'Mn').lower()

        _click_pat = _re.match(
            r'^(?:clique|clica|clicando|pressiona|seleciona|selecione|escolhe|escolha|abre|entra|entre)\s+'
            r'(?:em\s+|no\s+|na\s+|nos\s+|nas\s+|o\s+|a\s+|os\s+|as\s+)?(.+)',
            _n(tl)
        )
        if _click_pat:
            from actions.executor import _resolve_click
            result = _resolve_click(_click_pat.group(1).strip(), _n(tl), self._executor)
            if result:
                return result.get("message", "Clique executado."), None

        # Modo Joy — jogos com IA
        _joy_triggers = ("vamos nos divertir", "quero jogar", "bora jogar", "modo joy",
                         "vamos jogar", "jogar com você", "jogar com a luna")
        if any(tl == t or tl.startswith(t) for t in _joy_triggers):
            return "🎮 Modo Joy ativado! Abrindo a interface de jogos... Acesse /joy no navegador ou clique em 'Joy' no menu!", None

        # Modo Conversa — ativa painel lateral
        if tl in ("vamos conversar", "conversar", "bora conversar"):
            self.in_conversation_mode = True
            return "Modo Conversa ativado! A partir de agora, sou toda ouvidos. Diga 'até mais' para voltarmos.", True

        # Modo agente / roteador
        if tl in ("modo agente", "ativar agente", "modo autonomo", "modo autônomo"):
            self.agent_mode = True
            return "Modo agente ativado. Vou orquestrar ferramentas e agir de forma autônoma.", None
        if tl in ("modo roteador", "modo rapido", "modo rápido", "desativar agente"):
            self.agent_mode = False
            return "Modo roteador ativado. Comandos diretos sem passar pelo LLM quando possível.", None

        # Desativa modo conversa — sinaliza False para fechar o painel
        if tl in ("ate mais", "até mais", "ate mais luna", "até mais luna"):
            if self.in_conversation_mode:
                self.in_conversation_mode = False
                return "Modo Conversa desativado. Voltando ao fluxo de roteamento padrão.", False
            return "Até logo!", None

        if tl == "apps":
            names = self._executor.get_app_names()
            return "Apps disponíveis: " + ", ".join(names[:15]), None

        if tl in ("o que você pode fazer", "o que vc pode fazer", "o que sabe fazer", "funções", "ajuda"):
            return (
                "Eu posso:\n\n"
                "• ⏱ Timers e alarmes — 'timer de 10 minutos', 'alarme às 14h'\n"
                "• 🛒 Lista de compras — 'adiciona leite na lista', 'ver lista'\n"
                "• 🔔 Lembretes — 'me lembra de tomar remédio às 20h'\n"
                "• 📝 Notas rápidas — 'anota: reunião às 15h', 'ver minhas notas'\n"
                "• 🎵 Música — 'toca música', 'próxima', 'volume 70'\n"
                "• 🌤 Clima — 'como está o tempo?', 'vai chover hoje?'\n"
                "• 🪟 Janelas — 'fecha essa janela', 'workspace 2', 'maximiza'\n"
                "• 📋 Clipboard — 'o que está na área de transferência?'\n"
                "• 🎯 Foco/Pomodoro — 'modo foco por 25 minutos'\n"
                "• ✍️ Textos criativos — 'escreva uma história sobre...'\n"
                "• 💻 Código — 'crie um script python que...'\n"
                "• 🔍 Dicionário — 'o que significa efêmero?'\n"
                "• 🖥 Tela — 'o que você está vendo?', 'tira um print'\n"
                "• 🌐 Web — 'pesquise sobre Python', 'abra o youtube.com'\n"
                "\n📌 Dica: use 'python luna_terminal.py' para ver TODOS os comandos."
            ), None

        if tl == "memoria":
            return self._memory.stats(), None
        if tl in ("limpar", "limpa memoria"):
            self._memory.clear_history()
            return "Histórico da conversa apagado.", None

        # Atalhos para módulos novos (evita cair na FASE 2 desnecessariamente)
        if tl in ("timers", "timers ativos", "timer ativo"):
            return self._executor.timer.status(), None
        if tl in ("lembretes", "meus lembretes"):
            return self._executor.reminders.list_reminders(), None

        # Inicia diálogo guiado de lembrete quando não há dados suficientes
        _reminder_triggers = ["adicionar lembrete", "adiciona lembrete", "novo lembrete",
                               "criar lembrete", "cria lembrete", "quero um lembrete"]
        if any(t in tl for t in _reminder_triggers):
            # Verifica se já tem hora no texto — se sim, deixa o executor resolver
            import re as _re
            if not _re.search(r'\d{1,2}[h:]\d{0,2}', tl):
                return self._start_dialog("reminder"), None
        if tl in ("lista", "lista de compras", "ver lista"):
            return self._executor.shopping.format_list(), None
        if tl in ("notas", "minhas notas", "ver notas"):
            return self._executor.notes.list_notes(), None
        if tl in ("foco", "status do foco"):
            return self._executor.focus.status(), None

        if tl == "status":
            llm_ok = "✓" if self._llm.is_ready() else "✗"
            stt_ok = "✓" if self._stt.is_available() else "✗"
            cache_count = len(self._cache.cache.get("entries", {}))
            timer_status = self._executor.timer.status()
            return (f"LLM: {llm_ok} | Agente: {'ON' if self.agent_mode else 'OFF'} | "
                    f"Conversa: {'ON' if self.in_conversation_mode else 'OFF'} | "
                    f"Microfone: {stt_ok} | Voz: ✓ | "
                    f"Cache: {cache_count} entradas | {self._memory.stats()}\n"
                    f"{timer_status}"), None
        if tl == "performance":
            avg_req = self._perf.get_average_time("request_times")
            avg_mdl = self._perf.get_average_time("model_times")
            hits = self._perf.metrics.get("cache_hits", 0)
            misses = self._perf.metrics.get("cache_misses", 0)
            return (f"Tempo médio: {avg_req:.0f}ms | Modelo: {avg_mdl:.0f}ms | "
                    f"Cache hits: {hits} | misses: {misses}"), None

        # ── Briefing diário ───────────────────────────────────
        _briefing_triggers = [
            "o que temos pra hoje", "o que temos para hoje",
            "briefing do dia", "resumo do dia", "como está o dia",
            "o que tem hoje", "me dá um resumo do dia",
        ]
        if any(t in tl for t in _briefing_triggers):
            return self._daily_briefing(), None

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
        """Monta contexto histórico + visual para o prompt."""
        parts = []

        # Memória
        mem_ctx = self._memory.get_context_for_prompt(text)
        if mem_ctx:
            parts.append(mem_ctx)

        # Contexto leve de tela em TODAS as requisições (janela ativa + janelas abertas, ~5ms)
        quick_ctx = self._vision.get_quick_context()
        if quick_ctx:
            parts.append(f"[Tela atual] {quick_ctx}")

        # Screenshot + OCR completo (apenas se o usuário pediu explicitamente)
        vision_triggers = ["tela", "vendo", "enxerga", "print", "screen", "vê", "monitor", "o que está aberto", "imagem", "gráfico", "video", "vídeo"]
        if any(w in text.lower() for w in vision_triggers):
            desc = self._vision.capture_and_describe()
            if desc:
                parts.append(f"[Captura de tela (Estrutura/Janelas)]\n{desc}")
            
            # Groq Vision extra description
            vision_desc = self._vision.describe_with_groq_vision(text)
            if vision_desc and not "falhou" in vision_desc and not "ausente" in vision_desc:
                parts.append(f"[Visão Computacional do Groq Llama 3.2 Vision]\n{vision_desc}")

        # Apps disponíveis
        apps = ", ".join(self._executor.get_app_names()[:20])
        parts.append(f"[Apps instalados]: {apps}")

        # Estado do sistema + contexto web (modo agente ou conversa)
        if self.agent_mode or self.in_conversation_mode:
            system_state = self._get_system_state_context()
            if system_state:
                parts.append(system_state)

            # URL Parsing (Jina AI)
            import re
            urls = re.findall(r'(https?://[^\s]+)', text)
            for url in urls[:1]:  # Pega o primeiro link da mensagem
                print(f"[Core] Lendo conteúdo da URL: {url}")
                page_content = self._executor.web_manager.read_page(url)
                if page_content:
                    parts.append(
                        f"[CONTEÚDO DA URL: {url}]\n"
                        f"Use esse texto para responder sobre o site ou link:\n"
                        f"{page_content[:6000]}"  # Extrai até 6000 caracteres pro LLM
                    )

            search_data = self._quick_fact_check(text)
            if search_data:
                parts.append(
                    "[FACT CHECK AUTOMÁTICO (Tavily/Web)]\n"
                    "Use as informações abaixo para complementar/verificar sua resposta:\n"
                    f"{search_data}"
                )

        return "\n\n".join(parts)

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


    def _call_llm(self, text: str, context: str, use_fast: bool = False, use_heavy: bool = False, use_basic: bool = False) -> dict:
        """
        Chama o LLM e parseia a resposta JSON. Se for tarefa de código maciço, usa streaming no disco.
        Retorna dict com {action, params, response}.
        """
        # Verifica se é estritamente uma solicitação de programação
        # (Desativado no modo papo para evitar que a palavra "jogo" ou "site" ative o código acidentalmente)
        is_coding_file = use_heavy and not self.in_conversation_mode and any(w in text.lower() for w in ["código", "programe", "script", "desenvolva", "crie um arquivo", "html", "javascript", "python", "css", "aplicativo", "jogo", "site"])

        if is_coding_file:
            print("[Router] Bypass de JSON Ativado: Redirecionando saída bruta para o disco via Stream!")
            prompt = f"""Você é um Programador Nível Sênior Absoluto. Cumpra com o pedido fornecendo APENAS E RESTRITAMENTE O CÓDIGO FONTE FINAL. Sem textos de introdução, sem markdown (```), apenas código rodável.
Regra Magna: Sua PRIMEIRA LINHA OBRIGATÓRIA escrita deve ser exata e unicamente neste formato: [FILE: nomedoarquivo.extensao]
A partir da segunda linha, todo o código.

Pedido do usuário: {text}"""

            # Usa Groq se disponível (muito mais rápido), senão Ollama heavy
            coder_model = MODELS["heavy"]
            if self._llm._use_groq("coding"):
                from brain.llm import GROQ_MODELS
                coder_model = GROQ_MODELS["heavy"]
                print(f"[Coder] Usando Groq: {coder_model}")
            else:
                print(f"[Coder] Usando Ollama: {coder_model} (Aguarde o modelo aquecer...)")

            stream_gen = self._llm.generate(prompt, task_type="coding", model=coder_model, stream=True)

            buffer = ""
            first_line_done = False
            filename = "script_gerado_sem_nome.txt"
            f_handle = None
            filepath = None

            for chunk in stream_gen:
                if str(chunk).startswith("[Erro"):
                    print("\n[Erro de Stream]", chunk)
                    return {"action": "conversar", "params": {}, "response": f"Falha na geração de código: {chunk}"}
                
                # Feedback visual tipo Matrix no terminal
                print(chunk, end="", flush=True)
                
                if not first_line_done:
                    buffer += chunk
                    if "\n" in buffer:
                        first_line, rest = buffer.split("\n", 1)
                        import re
                        m = re.search(r'\[FILE:\s*(.+)\]', first_line, re.IGNORECASE)
                        if m:
                            filename = m.group(1).strip()
                            # remove sujeira como chaves ou aspas acidentais
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
                        # Substitui aspas triplas ou markdown perdido
                        chunk_limpo = chunk.replace("```html", "").replace("```python", "").replace("```", "")
                        f_handle.write(chunk_limpo)
                        f_handle.flush()
            
            print("\n[Coder] Streaming concluído com sucesso!")
            
            if f_handle:
                f_handle.close()
                return {"action": "conversar", "params": {}, "response": f"Concluído! Todo o código foi escrito ao vivo dentro do arquivo {filename}."}
            else:
                return {"action": "conversar", "params": {}, "response": "Houve um problema de permissão e o arquivo não abriu para a escrita do stream."}


        # ── Fluxo Normal JSON (Conversa e Ações) ──
        actions_desc = "\n".join(f"- {k}: {v}" for k, v in ACTIONS.items())
        
        # Injeta perfil do usuário
        profile_context = ""
        if self.user_profile:
            name = self.user_profile.get("user_name", "Usuário")
            pref = self.user_profile.get("preferences", "")
            notes = self.user_profile.get("notes", "")
            profile_context = f"\n[PERFIL DO USUÁRIO]\nNome: {name}\nPreferências: {pref}\nNotas: {notes}\n"

        # Modo agente/conversa: prompt com instruções de orquestração
        if self.agent_mode or self.in_conversation_mode:
            user_name = self.user_profile.get("user_name", "você")
            conv_prompt = (
                f"Você é Luna, uma assistente de IA feminina, inteligente e natural.\n"
                f"Você NÃO é '{user_name}' — '{user_name}' é o usuário.\n"
                f"Você tem acesso direto às funções do sistema através das ferramentas 'run_luna_command', 'google_query', 'google_send_email', 'google_create_event' e 'crew_run'.\n"
                f"\n"
                f"🚨 AVISO CRÍTICO DE INTEGRAÇÃO DO GOOGLE:\n"
                f"- A integração com o Google (Calendar e Gmail) está TOTALMENTE ATIVA, configurada e autenticada com sucesso! Você já tem as credenciais necessárias. NUNCA diga ao usuário que precisa adicionar 'credentials.json' ou 'token.json'.\n"
                f"- Se o usuário pedir para listar e-mails ou compromissos, use 'google_query'.\n"
                f"- Se o usuário pedir para enviar um e-mail, use 'google_send_email'.\n"
                f"- Se o usuário pedir para marcar/criar um compromisso ou evento na agenda, use 'google_create_event'.\n"
                f"\n"
                f"REGRAS ABSOLUTAS DE COMPORTAMENTO:\n"
                f"1. NUNCA exiba nomes de comandos ou ferramentas (run_luna_command, google_query etc) na fala. Fale como humana.\n"
                f"2. NUNCA use luna-lights a não ser que o usuário fale explicitamente 'luz', 'lâmpada', 'sala', 'iluminação'.\n"
                f"3. Quando o resultado de uma ferramenta tiver a informação pedida (ex: o conteúdo de uma nota, e-mail ou agenda), LEIA para o usuário na sua resposta.\n"
                f"4. NUNCA pergunte o que fazer se já souber o que o usuário quer. Execute e informe.\n"
                f"5. REGRA CRÍTICA: Se pedir cálculo, calcule agora. Se pedir informação salva, leia ela.\n"
                f"6. REGRA DE TOM: Adapte seu tom ao contexto emocional do usuário. Se for triste, doente ou luto, seja calma, respeitosa e empática. Se for feliz, comemore moderadamente. Nunca use 'ahah!', 'hahaha', 'kkk' ou rir de situações sérias ou normais.\n"
                f"\n"
                f"Comandos disponíveis via 'run_luna_command' (APENAS quando solicitado explicitamente):\n"
                f"- Música/playlist: luna-spotify\n"
                f"- LUZ DA SALA (só quando pedirem luz/lâmpada/sala): luna-lights\n"
                f"- Pesquisa web: luna-search\n"
                f"- Abrir apps: luna-app\n"
                f"- Timers, notas, lembretes, clima, lista de compras: luna-router\n"
                f"\n"
                f"Ferramentas Google dedicadas (preferencial para Google Workspace):\n"
                f"- google_query: Ler calendário ('calendar') ou e-mails ('gmail')\n"
                f"- google_send_email: Enviar e-mails (com ou sem anexos da pasta Luna-programming)\n"
                f"- google_create_event: Criar eventos/compromissos na agenda\n"
                f"- google_edit_event: Editar compromissos existentes\n"
                f"- google_delete_event: Deletar compromissos\n"
                f"- google_events_by_date: Buscar compromissos por data (YYYY-MM-DD)\n"
                f"- google_search_emails: Pesquisar emails usando a busca do Gmail\n"
                f"- google_read_email: Ler o conteúdo completo de um e-mail específico pelo ID\n"
                f"- google_reply_email: Responder a um e-mail específico\n"
                f"- google_forward_email: Encaminhar um e-mail para alguém\n"
                f"- google_mark_read / google_delete_email: Marcar como lido ou lixeira\n"
                f"- google_list_files: Listar arquivos da pasta Luna-programming para anexar/subir\n"
                f"- google_drive_upload: Enviar qualquer arquivo do workspace/sistema para o Google Drive com link compartilhável\n"
                f"- google_drive_list: Listar seus arquivos salvos no Google Drive\n"
                f"- google_drive_search: Pesquisar arquivos no Google Drive\n"
                f"- google_drive_create_folder: Criar uma pasta no Google Drive\n"
                f"- google_drive_delete: Deletar/Mover para lixeira arquivo ou pasta no Google Drive pelo ID\n"
                f"- create_excel: Criar uma planilha Excel a partir de dados (JSON)\n"
                f"- create_pdf_drive: Gerar um PDF exportado via Google Drive\n"
                f"- read_file: Ler/extrair o texto de arquivos locais (.txt, .csv, .xlsx, .pdf)\n"
                f"- save_file: Salvar dados/conteúdo em arquivos locais no workspace\n"
                f"- get_system_status: Verificar status de hardware do sistema\n"
                f"- get_running_processes: Listar processos em execução com maior consumo\n"
                f"- run_bash_command: Executar comandos no terminal bash com segurança\n"
                f"- save_home_info: Salvar informação sobre a casa (wifi, chaves, rotinas, receitas)\n"
                f"- search_home_info: Buscar informações salvas sobre a casa\n"
                f"{profile_context}\n"
                f"Histórico recente:\n{context}\n\n"
                f"Mensagem de {user_name}: \"{text}\"\n"
            )
            prompt = conv_prompt
        else:
            prompt = f"""Você é Luna, a assistente autônoma inteligente criada pelo Pera.
Personalidade: natural, precisa, proativa — fala como uma pessoa real, não como um robô.

{profile_context}

Você possui ferramentas de ação no sistema ('run_luna_command'), ferramentas Google dedicadas ('google_query', 'google_send_email', 'google_create_event', 'google_edit_event', 'google_delete_event', 'google_events_by_date', 'google_search_emails', 'google_read_email', 'google_reply_email', 'google_forward_email', 'google_mark_read', 'google_delete_email', 'google_list_files', 'google_drive_upload', 'google_drive_list', 'google_drive_search', 'google_drive_create_folder', 'google_drive_delete'), ferramentas de documentos ('create_excel', 'create_pdf_drive', 'read_file', 'save_file'), ferramentas de sistema ('get_system_status', 'get_running_processes', 'run_bash_command') e ferramentas de memória da casa ('save_home_info', 'search_home_info').

🚨 INTEGRACÃO GOOGLE ATIVA 🚨
A integração com o Google (Gmail, Calendar e Drive) está TOTALMENTE ATIVA, configurada e autenticada! Você já possui as credenciais necessárias. Nunca diga que precisa de credentials.json ou token.json. Use as ferramentas do Google diretamente!

📜 MANUAL DE ORQUESTRAÇÃO 📜

Use a ferramenta certa para o trabalho:

[FERRAMENTAS GOOGLE DEDICADAS] (SEMPRE que for interagir com Gmail, Google Calendar ou Google Drive):
  ▸ google_query → Buscar compromissos da agenda ou e-mails não lidos.
  ▸ google_send_email → Enviar e-mails via Gmail (com ou sem anexos da pasta Luna-programming).
  ▸ google_create_event → Criar um novo compromisso na agenda Google.
  ▸ google_edit_event → Editar compromisso na agenda.
  ▸ google_delete_event → Deletar compromisso.
  ▸ google_events_by_date → Ver agenda de um dia específico.
  ▸ google_search_emails → Buscar e-mails antigos/específicos.
  ▸ google_read_email → Ler conteúdo completo de um email específico pelo ID.
  ▸ google_reply_email → Responder a um email específico pelo ID.
  ▸ google_forward_email → Encaminhar email pelo ID.
  ▸ google_mark_read → Marcar email como lido.
  ▸ google_delete_email → Deletar email (lixeira).
  ▸ google_list_files → Listar arquivos da pasta Luna-programming (imagens, códigos, textos) para que você saiba o nome exato a ser anexado ou enviado ao Drive.
  ▸ google_drive_upload → Enviar um arquivo do workspace/sistema para o Google Drive e gerar um link compartilhável público.
  ▸ google_drive_list → Listar arquivos salvos no seu Google Drive.
  ▸ google_drive_search → Buscar arquivos no Google Drive por trecho do nome.
  ▸ google_drive_create_folder → Criar uma pasta no Google Drive.
  ▸ google_drive_delete → Excluir/Mover para lixeira arquivo ou pasta no Drive por ID.
  
[DOCUMENTOS & PLANILHAS] (para manipular planilhas, PDFs e arquivos locais):
  ▸ create_excel → Criar uma planilha Excel (.xlsx) a partir de uma lista de dados/objetos JSON.
  ▸ create_pdf_drive → Criar um documento PDF exportado e compartilhado via Google Drive.
  ▸ read_file → Ler arquivos do workspace (.txt, .csv, .xlsx, .pdf).
  ▸ save_file → Salvar arquivos locais de texto no workspace.
  
[FERRAMENTAS DE SISTEMA] (para monitoramento e terminal):
  ▸ get_system_status → Verificar uso de CPU, memória RAM e espaço em disco.
  ▸ get_running_processes → Listar os processos mais pesados que estão rodando.
  ▸ run_bash_command → Executar um comando síncrono seguro no terminal bash.
  
[MEMÓRIA DA CASA] (para lembrar e buscar informações do lar):
  ▸ save_home_info → Salvar uma informação sobre a casa (wifi, chaves, rotinas, receitas).
  ▸ search_home_info → Buscar informações já salvas sobre a casa.


[LUNA-SPOTIFY] (via run_luna_command) → Tocar música/playlist/artista.
  Use quando: o usuário pedir música, playlist, artista, "toca", "coloca".
  Ex: luna-spotify "the weeknd"

[LUNA-LIGHTS] (via run_luna_command) → Controlar a LUZ FÍSICA da sala.
  Use SOMENTE quando o usuário mencionar: "luz", "lâmpada", "sala", "iluminação", "acende", "apaga".
  NUNCA use para pesquisa, notas, música, web ou qualquer outro pedido.

[LUNA-SEARCH] (via run_luna_command) → Pesquisar algo na web e ABRIR o browser com os resultados.
  Use quando: o usuário pedir para pesquisar, buscar, googlar, procurar algo.

[LUNA-APP] (via run_luna_command) → Abrir um programa instalado.
  Ex: luna-app firefox

[LUNA-ROUTER] (via run_luna_command) → Funções nativas do sistema. Associe intenções aos subcomandos certos:
  ▸ TIMER: contagem regressiva, cronometrar, avisar depois de X tempo.
  ▸ LEMBRETE: horários absolutos ou datas do sistema (sem ser na agenda Google).
  ▸ NOTAS: anotar informações locais, recuperar o que foi salvo localmente.
  ▸ LISTA DE COMPRAS: itens de mercado locais.
  ▸ CLIMA: temperatura, previsão do tempo.

[LUNA-BROWSER] (via run_luna_command) → Agente autônomo para automações web complexas em URLs específicas (formulários, logins programáticos).

[LUNA-CLICK] (via run_luna_command) → Clica em elemento na TELA REAL do usuário via OCR + xdotool.

REGRAS ABSOLUTAS:
1. NUNCA mencione nomes de comandos ou ferramentas na fala (luna-router, google_query etc). Fale naturalmente.
2. Se usar ferramentas e receber dados de volta (notas, lista, e-mails), INCLUA esse conteúdo na sua resposta.
3. NUNCA pergunte o que fazer se souber a intenção. Execute e informe o resultado.
4. Para conversa, cálculo ou pergunta geral, responda SEM usar ferramenta.
5. Para tarefas múltiplas, use a ferramenta VÁRIAS VEZES em sequência.
6. ADAPTE SEU TOM: Adapte seu tom ao contexto emocional do usuário. Se for triste, doente ou luto, seja calma, respeitosa e empática. Se for feliz, comemore moderadamente. Nunca use 'ahah!', 'hahaha' ou rir em situações sérias ou normais. Seja madura, sincera e empática.

{context}

Mensagem do usuário: "{text}"
"""

        # Kitsuune Router Engine
        if self.agent_mode or self.in_conversation_mode:
            task_type = "conversational"
            model = MODELS["main"]
            if use_heavy:
                model = MODELS["heavy"]
                task_type = "planning"
        else:
            task_type = "planning"
            model = MODELS["main"]
            if use_fast:
                model = MODELS["fast"]
                task_type = "command"
            elif use_basic:
                model = MODELS.get("basic", "llama3.2:1b")
                task_type = "planning"
            elif use_heavy:
                model = MODELS["heavy"]

        print(f"[LLM] Usando modelo: {model} (Task: {task_type})")
        
        try:
            from brain.agent_tools import LUNA_TOOLS, execute_tool_call
            tools_to_use = LUNA_TOOLS if self._llm.supports_native_tools() else None

        except ImportError as ie:
            print(f"[Core] ⚠ Erro de importação em agent_tools: {ie}")
            import traceback; traceback.print_exc()
            tools_to_use = None
            execute_tool_call = None

        # ── SISTEMA DE SEQUÊNCIA (MAX 3 PASSOS) ──
        # Regra: 1 pedido = 1 ferramenta. Para múltiplos pedidos, executa em sequência.
        max_steps = 5
        current_step = 0
        # Separa o prompt em system + user para melhor compreensão do modelo 8B
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        executed_commands = set()  # evita repetir o mesmo comando
        tools_executed = 0  # quantas ferramentas foram chamadas com sucesso
        
        # Timeout de segurança para o loop total (45 segundos)
        loop_start_time = time.time()
        MAX_LOOP_TIME = 90.0

        while current_step < max_steps:
            current_step += 1
            
            # Verifica se estourou o tempo total do loop
            if (time.time() - loop_start_time) > MAX_LOOP_TIME:
                print(f"[Router] ⚠ Timeout de {MAX_LOOP_TIME}s atingido no loop de ferramentas. Abortando.")
                break

            raw = self._llm.generate(
                prompt=None,
                task_type=task_type,
                model=model,
                tools=tools_to_use,
                messages=messages,
            )
            
            # Detecta se é uma resposta com ferramentas (independente do shape do objeto)
            is_tool_call = False
            tool_calls = None
            assistant_msg = None

            if isinstance(raw, dict):
                tool_calls = raw.get("tool_calls")
                assistant_msg = raw.get("message")
                if tool_calls:
                    is_tool_call = True

            if is_tool_call:
                print(f"[Router] 🛠️ O Agente decidiu orquestrar ferramentas! (Passo {current_step}/{max_steps})")
                
                # Normaliza a mensagem do assistente para o histórico
                msg_dict = {"role": "assistant", "content": ""}
                if assistant_msg:
                    msg_dict["content"] = getattr(assistant_msg, "content", "") or ""
                    
                    # Tenta extrair tool_calls de forma segura
                    tc_list = []
                    raw_tc = getattr(assistant_msg, "tool_calls", None) or tool_calls
                    if isinstance(raw_tc, list):
                        for tc in raw_tc:
                            try:
                                tc_item = {
                                    "id": getattr(tc, "id", f"call_{int(time.time())}"),
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name if hasattr(tc, "function") else tc.get("function", {}).get("name"),
                                        "arguments": tc.function.arguments if hasattr(tc, "function") else tc.get("function", {}).get("arguments")
                                    }
                                }
                                tc_list.append(tc_item)
                            except Exception:
                                continue
                    if tc_list:
                        msg_dict["tool_calls"] = tc_list
                
                messages.append(msg_dict)
                
                all_done = True  # assume que todos terminaram com sucesso
                for tc in raw["tool_calls"]:
                    import json as _json
                    # Deduplicação robusta: usa hash do JSON raw completo
                    raw_args_str = getattr(tc.function, "arguments", "") if hasattr(tc, "function") else ""
                    cmd_sig = raw_args_str  # fallback: usa o JSON inteiro como chave
                    try:
                        parsed_args = _json.loads(raw_args_str)
                        cmd_sig = parsed_args.get("command", raw_args_str)
                    except Exception:
                        pass

                    # Ignora comandos repetidos
                    if cmd_sig and cmd_sig in executed_commands:
                        print(f"[Router] ⚠ Comando duplicado ignorado: {cmd_sig}")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "IGNORADO: Este comando já foi executado nesta sequência."
                        })
                        continue

                    tool_res = execute_tool_call(self._executor, tc)
                    if cmd_sig:
                        executed_commands.add(cmd_sig)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(tool_res)
                    })

                    if str(tool_res).startswith("SUCESSO"):
                        tools_executed += 1
                    else:
                        all_done = False

                # Encerra se todos os comandos desse passo foram SUCESSO
                if all_done and tools_executed > 0:
                    print("[Router] ✓ Ferramentas executadas com sucesso. Gerando resposta final...")
                    break
            else:
                # Retorno final sem ferramentas
                if current_step > 1:
                    print("[Router] 🛠️ Gerando resposta final após ferramentas...")

                if isinstance(raw, dict) and "response" in raw:
                    return {"action": "conversar", "params": {}, "response": raw["response"]}

                if isinstance(raw, str):
                    parsed_final = self._parse_llm_response(raw, text)
                    if parsed_final.get("action") == "fallback":
                        return {"action": "conversar", "params": {}, "response": raw}
                    return parsed_final

                return {"action": "conversar", "params": {}, "response": str(raw)}

        # Gera resposta final com base no histórico de ferramentas
        print("[Router] 🛠️ Gerando resposta final após ferramentas...")
        raw_final = self._llm.generate(prompt="", task_type=task_type, model=model,
                                        tools=None, messages=messages)
        if isinstance(raw_final, dict) and "response" in raw_final:
            return {"action": "conversar", "params": {}, "response": raw_final["response"]}
        if isinstance(raw_final, str):
            parsed = self._parse_llm_response(raw_final, text)
            if parsed.get("action") != "fallback":
                return parsed
            return {"action": "conversar", "params": {}, "response": raw_final}
        return {"action": "conversar", "params": {}, "response": str(raw_final)}

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

    def _execute_action(self, llm_result: dict, original_text: str = "") -> Optional[dict]:
        """Executa a ação indicada pelo LLM."""
        action = llm_result.get("action", "conversar")
        params = llm_result.get("params", {})

        print(f"[Luna] Ação: {action} | Params: {params}")

        try:
            if action == "open_app":
                app = params.get("app", "")
                best = self._executor.find_best_app(app) or app
                prev_window = self._vision.get_active_window()
                result = self._executor.open_app(best)
                if result.get("success"):
                    feedback = self._vision.verify_action_result(f"abrir {best}", prev_window)
                    result["feedback"] = feedback
                return result

            elif action == "open_url":
                return self._executor.open_url(params.get("url", ""))

            elif action == "search_web":
                return self._executor.search_web(params.get("query", ""))

            elif action == "ui_click":
                target = params.get("target", "")
                x, y = params.get("x"), params.get("y")
                prev_window = self._vision.get_active_window()
                if x is not None and y is not None:
                    result = self._executor.click_at(int(x), int(y))
                else:
                    # Tenta resolução inteligente (ordinais, tipos, texto literal)
                    from actions.executor import _resolve_click
                    import unicodedata as _ud
                    def _n(s):
                        return ''.join(c for c in _ud.normalize('NFD', s) if _ud.category(c) != 'Mn').lower()
                    result = _resolve_click(target, _n(target), self._executor) or self._executor.click_text(target)
                if result.get("success"):
                    result["feedback"] = self._vision.verify_action_result(f"clicar em {target}", prev_window)
                return result

            elif action == "ui_type":
                return self._executor.type_text(params.get("text", ""))

            elif action == "ui_key":
                return self._executor.press_key(params.get("key", ""))

            elif action == "ui_scroll":
                return self._executor.scroll(params.get("direction", "down"))

            elif action == "see_screen":
                desc = self._vision.capture_and_describe()
                return {"success": True, "screen_desc": desc}

            elif action == "write_code":
                filename = params.get("filename", "script.txt")
                content = params.get("content", "")
                return self._executor.write_code(filename, content)

            elif action == "write_text":
                msg = self._run_writer_stream(original_text)
                return {"success": True, "message": msg}

            elif action == "conversar":
                return {"success": True}

            elif action == "run_luna_command":
                # Roteamento de comandos do modo conversa para o executor
                command = params.get("command", "")
                argument = params.get("argument", params.get("query", params.get("app", "")))
                full_cmd = f"{command} {argument}".strip() if argument else command
                result = self._executor.execute_natural(full_cmd)
                if result.get("success"):
                    return result
                # Tenta como texto natural
                return self._executor.execute_natural(original_text) or {"success": True}

            elif action == "controlar_luz":
                state = params.get("state", "")
                from actions.lights import handle as _lights_handle
                result = _lights_handle(state)
                return {"success": True, "message": result} if result else {"success": False}

            elif action == "google_query":
                service = params.get("service")
                max_results = params.get("max_results", 5)
                from actions.google_services import get_google
                gm = get_google()
                if service == "calendar":
                    res = gm.get_calendar_events(max_results)
                elif service == "gmail":
                    res = gm.get_unread_emails(max_results)
                else:
                    res = f"Serviço desconhecido '{service}'"
                return {"success": True, "message": res}

            elif action == "google_send_email":
                from actions.google_services import get_google
                res = get_google().send_email(
                    params.get("to"), params.get("subject"), params.get("body"),
                    params.get("attachments", ""))
                return {"success": True, "message": res}

            elif action == "google_create_event":
                from actions.google_services import get_google
                res = get_google().create_calendar_event(
                    params.get("summary"), params.get("start_time"),
                    params.get("end_time"), params.get("description", ""),
                    params.get("location", ""), params.get("attendees", ""))
                return {"success": True, "message": res}

            elif action == "google_edit_event":
                from actions.google_services import get_google
                res = get_google().edit_calendar_event(
                    params.get("event_id"), params.get("summary"),
                    params.get("start_time"), params.get("end_time"),
                    params.get("description"), params.get("location"))
                return {"success": True, "message": res}

            elif action == "google_delete_event":
                from actions.google_services import get_google
                res = get_google().delete_calendar_event(params.get("event_id"))
                return {"success": True, "message": res}

            elif action == "google_events_by_date":
                from actions.google_services import get_google
                res = get_google().get_events_by_date(params.get("date"), params.get("max_results", 20))
                return {"success": True, "message": res}

            elif action == "google_search_emails":
                from actions.google_services import get_google
                res = get_google().search_emails(params.get("query"), params.get("max_results", 5))
                return {"success": True, "message": res}

            elif action == "google_read_email":
                from actions.google_services import get_google
                res = get_google().read_email(params.get("message_id"))
                return {"success": True, "message": res}

            elif action == "google_reply_email":
                from actions.google_services import get_google
                res = get_google().reply_email(params.get("message_id"), params.get("body"))
                return {"success": True, "message": res}

            elif action == "google_forward_email":
                from actions.google_services import get_google
                res = get_google().forward_email(
                    params.get("message_id"), params.get("to"), params.get("extra_text", ""))
                return {"success": True, "message": res}

            elif action == "google_mark_read":
                from actions.google_services import get_google
                res = get_google().mark_as_read(params.get("message_id"))
                return {"success": True, "message": res}

            elif action == "google_delete_email":
                from actions.google_services import get_google
                res = get_google().delete_email(params.get("message_id"))
                return {"success": True, "message": res}

            elif action == "google_list_files":
                from actions.google_services import get_google
                res = get_google().list_workspace_files(params.get("pattern", "*"))
                return {"success": True, "message": res}

            elif action == "google_drive_upload":
                from actions.google_services import get_google
                res = get_google().google_drive_upload(params.get("filepath_or_name"), params.get("folder_id"))
                return {"success": True, "message": res}

            elif action == "google_drive_list":
                from actions.google_services import get_google
                res = get_google().google_drive_list(params.get("max_results", 10))
                return {"success": True, "message": res}

            elif action == "google_drive_search":
                from actions.google_services import get_google
                res = get_google().google_drive_search(params.get("query"), params.get("max_results", 10))
                return {"success": True, "message": res}

            elif action == "google_drive_create_folder":
                from actions.google_services import get_google
                res = get_google().google_drive_create_folder(params.get("folder_name"), params.get("parent_id"))
                return {"success": True, "message": res}

            elif action == "google_drive_delete":
                from actions.google_services import get_google
                res = get_google().google_drive_delete(params.get("file_id"))
                return {"success": True, "message": res}

            elif action == "create_excel":
                from actions.document_services import get_doc_services
                res = get_doc_services().create_excel(params.get("data"), params.get("filename"))
                return {"success": True, "message": res}

            elif action == "create_pdf_drive":
                from actions.document_services import get_doc_services
                res = get_doc_services().create_pdf_drive(params.get("content"), params.get("title"))
                return {"success": True, "message": res}

            elif action == "read_file":
                from actions.document_services import get_doc_services
                res = get_doc_services().read_file(params.get("filepath_or_name"))
                return {"success": True, "message": res}

            elif action == "save_file":
                from actions.document_services import get_doc_services
                res = get_doc_services().save_file(params.get("content"), params.get("filepath_or_name"))
                return {"success": True, "message": res}

            elif action == "get_system_status":
                from actions.system_tools import get_system_tools
                res = get_system_tools().get_system_status()
                return {"success": True, "message": res}

            elif action == "get_running_processes":
                from actions.system_tools import get_system_tools
                res = get_system_tools().get_running_processes(params.get("limit", 10))
                return {"success": True, "message": res}

            elif action == "run_bash_command":
                from actions.system_tools import get_system_tools
                res = get_system_tools().run_bash_command(params.get("command"))
                return {"success": True, "message": res}

            elif action == "save_home_info":
                from brain.memory import get_memory
                rag = get_memory().rag
                if rag:
                    res = rag.remember_home_info(params.get("text", ""), params.get("category", "geral"))
                    return {"success": True, "message": res}
                return {"success": False, "message": "RAG não está disponível."}

            elif action == "search_home_info":
                from brain.memory import get_memory
                rag = get_memory().rag
                if rag:
                    res = rag.retrieve_home_info(params.get("query", ""))
                    return {"success": True, "message": res if res else "Nenhuma informação encontrada."}
                return {"success": False, "message": "RAG não está disponível."}

        except Exception as e:
            print(f"[Luna] Erro ao executar ação '{action}': {e}")
            return {"success": False, "message": str(e)}

        return None

    def _finalize_response(self, llm_result: dict, action_result: Optional[dict]) -> str:
        """Ajusta a resposta com base no resultado da ação."""
        base_response = llm_result.get("response", "")
        action = llm_result.get("action", "conversar")

        # Erro na ação
        if action_result and not action_result.get("success", True):
            msg = action_result.get("message", "")
            if msg and action != "conversar":
                return f"{base_response} (Aviso: {msg})"

        # Feedback pós-ação de UI (janela mudou, etc.)
        if action_result and action_result.get("feedback"):
            base_response = f"{base_response}\n{action_result['feedback']}"

        # Sucesso no Modo Escritor lançado via LLM
        if action == "write_text" and action_result and action_result.get("success"):
            return action_result.get("message", base_response)

        # Sucesso nas ações do Google
        if action and action.startswith("google_") and action_result and action_result.get("success"):
            google_msg = action_result.get("message", "")
            if google_msg:
                return f"{base_response}\n\n{google_msg}" if base_response else google_msg

        # Descrição de tela
        if action == "see_screen" and action_result:
            desc = action_result.get("screen_desc", "")
            if desc:
                return f"{base_response}\n\n{desc}"

        # Sucesso em outras ações genéricas (sistema, documentos, RAG, etc.) que retornam uma mensagem de resultado
        if action_result and action_result.get("success"):
            action_msg = action_result.get("message", "")
            if action_msg and action not in ["conversar", "write_text", "see_screen"] and not action.startswith("google_"):
                return f"{base_response}\n\n{action_msg}" if base_response else action_msg

        # Auto-extração de fatos da conversa
        if action == "conversar" and base_response:
            self._auto_extract_facts(llm_result.get("_user_text", ""), base_response)

        return base_response or "Entendido."

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
