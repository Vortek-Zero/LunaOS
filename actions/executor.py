#!/usr/bin/env python3
"""
actions/executor.py — Executor unificado de ações (1 Cauda).
Roteia comandos naturais para os módulos corretos sem passar pelo LLM.
"""
import re
import unicodedata
from typing import Optional

from actions.apps import AppManager
from actions.web import WebManager
from actions.ui import UIManager
from actions.coder import CoderManager
from actions.timer import get_timer
from actions.shopping_list import get_shopping_list
from actions.reminders import get_reminders
from actions.notes import get_notes
from actions.media import get_media, get_radio
from actions.weather import get_weather
from actions.window_manager import get_window_manager
from actions.clipboard import get_clipboard
from actions.focus import get_focus
from actions.spotify import get_spotify
from actions.playlist_builder import get_playlist_builder, detect_playlist_intent
from actions.writing import get_writing_engine
from actions.math_board import get_math_board
from actions.bff import get_bff
from actions.automation import get_automation
from actions.eyes import get_eyes
from actions.lights import get_lights
from actions.morse import get_morse
from actions.party import get_party
from actions.google_services import get_google


# ── Resolução inteligente de cliques ─────────────────────────

# Mapa de ordinais em português e inglês → índice 0-based
_ORDINALS = {
    "primeiro": 0, "primeira": 0, "1o": 0, "1a": 0, "1º": 0, "1ª": 0, "um": 0, "uma": 0,
    "segundo": 1, "segunda": 1, "2o": 1, "2a": 1, "2º": 1, "2ª": 1, "dois": 1, "duas": 1,
    "terceiro": 2, "terceira": 2, "3o": 2, "3a": 2, "3º": 2, "3ª": 2, "tres": 2,
    "quarto": 3, "quarta": 3, "4o": 3, "4a": 3, "4º": 3, "4ª": 3,
    "quinto": 4, "quinta": 4, "5o": 4, "5a": 4, "5º": 4, "5ª": 4,
}

# Tipos de elemento que o usuário pode mencionar
_ELEMENT_TYPES = {
    "link":       "link",
    "links":      "link",
    "resultado":  "resultado",
    "resultados": "resultado",
    "video":      "video",
    "videos":     "video",
    "vídeo":      "video",
    "vídeos":     "video",
    "botao":      "botao",
    "botão":      "botao",
    "botoes":     "botao",
    "botões":     "botao",
    "imagem":     "imagem",
    "foto":       "imagem",
    "thumbnail":  "imagem",
    "aba":        "aba",
    "tab":        "aba",
    "opcao":      "opcao",
    "opção":      "opcao",
    "item":       "item",
    "notificacao":"notificacao",
    "notificação":"notificacao",
}

# Instruções para o browser agent por tipo de elemento
_ELEMENT_INSTRUCTIONS = {
    "link":       "Clique no {n}º link visível na página (ignore navegação/menu, foque no conteúdo principal).",
    "resultado":  "Clique no {n}º resultado de busca na página.",
    "video":      "Clique no {n}º vídeo ou thumbnail de vídeo visível na página.",
    "botao":      "Clique no {n}º botão visível na página.",
    "imagem":     "Clique na {n}ª imagem visível na página.",
    "aba":        "Clique na {n}ª aba visível na página.",
    "opcao":      "Clique na {n}ª opção visível na página.",
    "item":       "Clique no {n}º item visível na página.",
    "notificacao":"Clique na {n}ª notificação visível.",
}

def _resolve_click(raw_target: str, cmd_norm: str, executor) -> dict | None:
    """
    Resolve clique em linguagem natural.
    Ordem: web (URL/teclado/Playwright) → OCR na tela (último recurso).
    """
    import unicodedata as _ud

    def _norm(s):
        return ''.join(c for c in _ud.normalize('NFD', s) if _ud.category(c) != 'Mn').lower()

    full_cmd = f"{cmd_norm} {raw_target}".strip()

    # ── Web: primeiro/segundo resultado, links de busca ──
    try:
        from actions.web_nav import try_click_web_result, is_web_result_click
        if is_web_result_click(full_cmd) or is_web_result_click(raw_target):
            web_res = try_click_web_result(
                full_cmd,
                executor,
                search_query=getattr(executor.web_manager, "last_search_query", ""),
            )
            if web_res and web_res.get("success"):
                return web_res
            print("[WebNav] Métodos web falharam — tentando OCR como fallback...")
    except Exception as e:
        print(f"[WebNav] Erro: {e}")

    words = _norm(raw_target).split()

    # Detecta ordinal
    ordinal_idx = None
    for w in words:
        if w in _ORDINALS:
            ordinal_idx = _ORDINALS[w]
            break
    # Também aceita número direto: "clica no 3 resultado"
    if ordinal_idx is None:
        num_m = re.search(r'\b(\d+)\b', raw_target)
        if num_m:
            ordinal_idx = int(num_m.group(1)) - 1  # converte para 0-based

    # Detecta tipo de elemento
    elem_type = None
    for w in words:
        if w in _ELEMENT_TYPES:
            elem_type = _ELEMENT_TYPES[w]
            break

    # ── Helper: tenta clicar via OCR na tela real ──
    def _try_ocr_click(search_text: str) -> dict | None:
        """Captura tela, faz OCR, e clica com xdotool se encontrar o texto."""
        if not search_text:
            return None
        result = executor.click_text(search_text)
        if result.get("success"):
            return result
        return None

    # ── Helper: clique posicional via OCR (N-ésimo elemento) ──
    def _try_nth_click(n_index: int, element_type: str = None) -> dict | None:
        """
        Tenta clicar no N-ésimo elemento visível via OCR.
        Captura tela, extrai todos os elementos, e clica no N-ésimo.
        """
        from vision.screen import get_vision
        vision = get_vision()
        if not vision.capture():
            return None
        
        elements = vision.get_elements_with_positions()
        if not elements:
            return None
        
        # Filtra elementos com confiança razoável e texto não-vazio
        good_elements = [e for e in elements if e.get("conf", 0) >= 40 and len(e.get("text", "").strip()) > 1]
        
        if not good_elements:
            return None

        # Se n_index está dentro do range, clica
        if n_index < len(good_elements):
            target = good_elements[n_index]
            print(f"[Click] Clicando no {n_index+1}º elemento: '{target['text']}' em ({target['x']}, {target['y']})")
            return executor.click_at(target["x"], target["y"])
        
        return None

    # ── Caso 1: ordinal + tipo → tenta OCR posicional ──
    if ordinal_idx is not None and elem_type is not None:
        n = ordinal_idx  # 0-based
        # Tenta click_text com palavras restantes (ex: "botão pesquisar")
        target_text = " ".join(w for w in words if w not in _ORDINALS and w not in _ELEMENT_TYPES)
        result = _try_ocr_click(target_text)
        if result:
            return result
        # Tenta clique posicional pelo índice
        result = _try_nth_click(n, elem_type)
        if result:
            return result
        return {"success": False, "message": f"Não encontrei o {ordinal_idx+1}º {elem_type} na tela via OCR."}

    # ── Caso 2: só ordinal sem tipo → assume resultado/link ──
    if ordinal_idx is not None:
        n = ordinal_idx  # 0-based
        target_text = " ".join(w for w in words if w not in _ORDINALS)
        result = _try_ocr_click(target_text)
        if result:
            return result
        result = _try_nth_click(n)
        if result:
            return result
        return {"success": False, "message": f"Não encontrei o {ordinal_idx+1}º elemento na tela via OCR."}

    # ── Caso 3: só tipo sem ordinal → clica no primeiro desse tipo ──
    if elem_type is not None:
        target_text = " ".join(w for w in words if w not in _ELEMENT_TYPES)
        result = _try_ocr_click(target_text)
        if result:
            return result
        result = _try_nth_click(0, elem_type)
        if result:
            return result
        return {"success": False, "message": f"Não encontrei {elem_type} na tela via OCR."}

    # ── Caso 4: texto literal → click_text na tela ──
    _noise = {"botao", "botão", "link", "o", "a", "os", "as", "no", "na", "nos", "nas",
              "em", "esse", "essa", "aquele", "aquela"}
    clean_words = [w for w in words if w not in _noise]
    target_text = " ".join(clean_words).strip()
    if target_text:
        result = executor.click_text(target_text)
        if result.get("success"):
            return result
        return {"success": False, "message": f"Não encontrei '{target_text}' na tela via OCR."}

    return None


class ActionExecutor:
    """
    Orquestrador central de todas as ações da Luna.
    Rotaciona funções brutas de 1 Cauda (Sem IA) baseado no JSON.
    """

    def __init__(self):
        self.app_manager = AppManager()
        self.web_manager = WebManager(self.app_manager)
        self.ui_manager = UIManager()
        self.coder_manager = CoderManager()
        # Módulos novos (lazy via singletons)
        self._timer = None
        self._shopping = None
        self._reminders = None
        self._notes = None
        self._media = None
        self._weather = None
        self._wm = None
        self._clipboard = None
        self._focus = None
        self._spotify = None
        self._playlist = None
        self._writing = None
        self._math = None
        self._bff = None
        self._automation = None
        self._eyes = None
        self._lights = None
        self._morse = None
        self._party = None
        self._google = None
        self._browser_agent = None
        print(f"[Executor] ✓ {len(self.app_manager.apps)} apps disponíveis")

    # ── Lazy loaders ──────────────────────────────────────────
    @property
    def timer(self):
        if not self._timer:
            self._timer = get_timer()
        return self._timer

    @property
    def shopping(self):
        if not self._shopping:
            self._shopping = get_shopping_list()
        return self._shopping

    @property
    def reminders(self):
        if not self._reminders:
            self._reminders = get_reminders()
        return self._reminders

    @property
    def notes(self):
        if not self._notes:
            self._notes = get_notes()
        return self._notes

    @property
    def media(self):
        if not self._media:
            self._media = get_media()
        return self._media

    @property
    def weather(self):
        if not self._weather:
            self._weather = get_weather()
        return self._weather

    @property
    def wm(self):
        if not self._wm:
            self._wm = get_window_manager()
        return self._wm

    @property
    def clipboard(self):
        if not self._clipboard:
            self._clipboard = get_clipboard()
        return self._clipboard

    @property
    def focus(self):
        if not self._focus:
            self._focus = get_focus()
        return self._focus

    @property
    def spotify(self):
        if not self._spotify:
            self._spotify = get_spotify()
        return self._spotify

    @property
    def playlist(self):
        if not self._playlist:
            self._playlist = get_playlist_builder()
        return self._playlist

    @property
    def writing(self):
        if not self._writing:
            self._writing = get_writing_engine()
        return self._writing

    @property
    def math(self):
        if not self._math:
            self._math = get_math_board()
        return self._math

    @property
    def bff(self):
        if not self._bff:
            self._bff = get_bff()
        return self._bff

    @property
    def automation(self):
        if not self._automation:
            self._automation = get_automation()
        return self._automation

    @property
    def eyes(self):
        if not self._eyes:
            self._eyes = get_eyes()
        return self._eyes

    @property
    def lights(self):
        if not self._lights:
            self._lights = get_lights()
        return self._lights

    @property
    def morse(self):
        if not self._morse:
            self._morse = get_morse()
        return self._morse

    @property
    def party(self):
        if not self._party:
            self._party = get_party()
        return self._party

    @property
    def google(self):
        if not self._google:
            self._google = get_google()
        return self._google

    @property
    def browser_agent(self):
        if not self._browser_agent:
            from actions.browser_agent import get_browser_agent
            self._browser_agent = get_browser_agent()
        return self._browser_agent

    # ── Apps ──────────────────────────────────────────────────
    def open_app(self, name: str) -> dict:
        return self.app_manager.open_app(name)

    def get_app_names(self) -> list[str]:
        return self.app_manager.get_app_names()

    def find_best_app(self, query: str) -> Optional[str]:
        return self.app_manager.find_best_app(query)

    # ── Web ────────────────────────────────────────────────────
    def open_url(self, url: str, browser: str = "firefox") -> dict:
        return self.web_manager.open_url(url, browser)

    def search_web(self, query: str, browser: str = "firefox") -> dict:
        return self.web_manager.search_web(query, browser)

    # ── UI Automation ──────────────────────────────────────────
    def click_at(self, x: int, y: int) -> dict:
        return self.ui_manager.click_at(x, y)

    def click_text(self, text: str) -> dict:
        return self.ui_manager.click_text(text)

    def type_text(self, text: str) -> dict:
        return self.ui_manager.type_text(text)

    def press_key(self, key: str) -> dict:
        return self.ui_manager.press_key(key)

    def scroll(self, direction: str, amount: int = 3) -> dict:
        return self.ui_manager.scroll(direction, amount)

    # ── Code Environment ───────────────────────────────────────
    def write_code(self, filename: str, content: str) -> dict:
        return self.coder_manager.write_code(filename, content)

    def open_code_file_stream(self, filename: str):
        return self.coder_manager._open_file_for_stream(filename)

    # ── Natural language command parsing ──────────────────────
    def execute_natural(self, cmd: str) -> dict:
        """
        Tenta resolver o comando sem LLM.
        Ordem: novos módulos especializados → ações de sistema básicas.
        Regra: keywords ambíguas (ex: "tempo") só disparam módulo se houver
        contexto suficiente — evita falsos positivos.
        """
        cmd_clean = re.sub(r"^(?:luna)[,:\s]+", "", cmd.lower().strip()).strip()
        
        def _norm(s):
            return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

        # cmd_norm: sem acento, para matching robusto
        cmd_norm = _norm(cmd_clean)
        
        has_duration = bool(re.search(r'\d+\s*(?:minuto|segundo|hora|min|seg|h\b)', cmd_norm))

        # ── Playlist inteligente (LLM 3B) ─────────────────────
        playlist_builder = self.playlist
        _skip_kw = ["pula", "pular", "proxima musica", "proxima faixa", "skip"]
        _is_skip = any(w in cmd_norm for w in _skip_kw)
        _is_stop = any(w in cmd_norm for w in ["para playlist", "cancela playlist", "stop playlist", "para a playlist"])

        if playlist_builder._active or playlist_builder._pending_genre or _is_stop or (
            not _is_skip and detect_playlist_intent(cmd)
        ):
            result = playlist_builder.handle(cmd)
            if result:
                return {"success": True, "message": result}

        # Pular só roteia para playlist se ela estiver ativa
        if _is_skip and playlist_builder._active:
            result = playlist_builder.handle(cmd)
            if result:
                return {"success": True, "message": result}

        # ── Timer — só dispara com intenção explícita de contagem regressiva ──
        timer_keywords = ["timer", "alarme", "cronometro", "me avisa em",
                          "avisa em", "conta regressiva", "daqui a", "daqui em"]
        if any(w in cmd_norm for w in timer_keywords) and has_duration:
            result = self.timer.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Lista de compras ───────────────────────────────────
        shopping_kw = ["lista de compras", "lista de compra",
                       "adiciona", "adicione", "coloca na lista",
                       "ver lista", "leia a lista", "ja comprei",
                       "limpa a lista", "remove da lista"]
        if any(w in cmd_norm for w in shopping_kw):
            result = self.shopping.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Lembretes ──────────────────────────────────────────
        reminder_kw = ["me lembra", "me lembre", "lembra de",
                       "criar lembrete", "lembretes", "meus lembretes"]
        if any(w in cmd_norm for w in reminder_kw):
            result = self.reminders.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Notas ──────────────────────────────────────────────
        notes_kw = ["anota", "anote", "nota:", "minhas notas",
                    "ver notas", "leia as notas", "apaga a nota"]
        if any(w in cmd_norm for w in notes_kw):
            result = self.notes.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Balada / modos de luz ──────────────────────────────
        _party_kw = ["balada", "festa", "discoteca", "disco", "pisca louca",
                     "sos", "emergencia", "emergência", "socorro",
                     "metronomo", "metrônomo", "bpm", "pisca no ritmo",
                     "contagem regressiva", "countdown", "conta regressiva",
                     "timer de luz", "apaga a luz em", "apaga em", "luz por", "luz durante",
                     "para balada", "para festa", "para tudo", "cancela"]
        if any(w in cmd_norm for w in _party_kw):
            result = self.party.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Morse ──────────────────────────────────────────────
        from actions.morse import _pending as _morse_pending
        if "morse" in cmd_norm or _morse_pending:
            result = self.morse.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Luz da sala ────────────────────────────────────────
        light_kw = ["luz", "luzes", "sala", "acende", "apaga", "ligar luz", "desligar luz"]
        if any(w in cmd_norm for w in light_kw):
            # Agendamento tem prioridade se houver horário no comando
            sched_kw = ["às", "as", "hora", "horario", "horário", "programar", "agendar",
                        "agendamento", "todo dia", "toda noite", "semana", "fim de semana"]
            has_time = bool(re.search(r'\d{1,2}[h:]\d{0,2}', cmd_norm))
            if has_time or any(w in cmd_norm for w in sched_kw):
                from actions.light_scheduler import get_light_scheduler
                result = get_light_scheduler().handle(cmd_clean)
                if result:
                    return {"success": True, "message": result}
            result = self.lights.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Rádio ──────────────────────────────────────────────
        if re.search(r'r[aá]dio', cmd_norm):
            result = get_radio().handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Mídia / Música ─────────────────────────────────────
        music_keywords = [
            "pausa", "pausar", "pause",
            "para a musica", "parar musica", "para tudo",
            "proxima musica", "proxima faixa", "proxima",
            "musica anterior", "faixa anterior", "voltar musica",
            "toca musica", "continua a musica", "retoma a musica",
            "continua", "retoma", "resume",
            "aumenta o volume", "diminui o volume",
            "sobe o volume", "baixa o volume",
            "que musica esta", "o que esta tocando", "musica atual",
            "repetindo", "repete a", "vezes", "volta a musica",
            "avanca a musica", "volta o tempo", "avanca o tempo"
        ]
        has_music_kw = any(w in cmd_norm for w in music_keywords)
        has_volume_num = bool(re.search(r'volume\s+(?:para\s+|em\s+|no\s+)?\d+', cmd_norm))

        is_favorite = any(w in cmd_norm for w in ["musica favorita", "minha musica favorita"])
        
        is_liked = any(w in cmd_norm for w in [
            "musicas que gostei", "musicas que eu gostei",
            "musicas curtidas", "liked songs"
        ])
        
        playlist_match = re.search(r'(?:abre|toca|coloca)\s+(?:a\s+)?minha playlist\s+(.+)', cmd_norm)
        has_playlist = bool(playlist_match)

        search_match = re.search(
            r'(?:toca|coloca|play|reproduz|quero ouvir|bota)\s+' +
            r'(?:a m[uú]sica\s+|a faixa\s+|o artista\s+)?(.+)',
            cmd_clean
        )
        generic_words = {"música", "musica", "uma música", "uma musica",
                         "agora", "algo", "uma", "um", "o", "a"}
        is_named_search = bool(
            search_match and
            search_match.group(1).strip() not in generic_words and
            len(search_match.group(1).strip()) > 1
        )

        if has_music_kw or has_volume_num or is_named_search or is_favorite or has_playlist or is_liked:
            if is_favorite:
                cmd_clean = "toca Montagem xonada"
                is_named_search = True
                search_match = re.search(r'toca\s+(.+)', cmd_clean)
                
            if is_liked:
                import subprocess as _sp
                import threading
                try:
                    _sp.Popen(["xdg-open", "spotify:collection:tracks"], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                    threading.Timer(1.5, lambda: _sp.Popen(["playerctl", "--player=spotify", "play"])).start()
                    return {"success": True, "message": "▶ Abrindo suas Músicas Curtidas 💚"}
                except Exception:
                    pass

            if has_playlist:
                playlist_name = playlist_match.group(1).strip().lower()
                import json
                from pathlib import Path
                import subprocess as _sp
                pl_file = Path(__file__).parent.parent / "playlists.json"
                uri = None
                if pl_file.exists():
                    try:
                        pls = json.loads(pl_file.read_text(encoding="utf-8"))
                        def norm_key(k):
                            return _norm(k.lower())
                        pls_lower = {norm_key(k): v for k, v in pls.items() if not k.startswith("_")}
                        uri = pls_lower.get(playlist_name)
                    except Exception:
                        pass
                
                if uri:
                    import threading
                    try:
                        _sp.Popen(["xdg-open", uri], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                        threading.Timer(1.5, lambda: _sp.Popen(["playerctl", "--player=spotify", "play"])).start()
                        return {"success": True, "message": f"▶ Abrindo playlist: {playlist_name.title()}"}
                    except Exception:
                        pass
                else:
                    cmd_clean = f"toca {playlist_name}"
                    is_named_search = True
                    search_match = re.search(r'toca\s+(.+)', cmd_clean)

            result = self.spotify.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

            result = self.media.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Clima — só com contexto explícito de meteorologia ──
        weather_explicit = any(w in cmd_norm for w in [
            "clima", "vai chover", "previsao", "chuva",
            "como esta o tempo", "tempo la em",
            "temperatura em", "temperatura de"
        ])
        if "temperatura" in cmd_norm and not has_duration:
            weather_explicit = True
        if weather_explicit:
            result = self.weather.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Google (Agenda / Gmail) ────────────────────────────
        google_kw = ["compromisso", "compromissos", "calendário", "calendario",
                     "agenda", "reunião", "reuniao", "email", "emails", "e-mail"]
        if any(w in cmd_norm for w in google_kw):
            result = self.google.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Janelas ────────────────────────────────────────────
        window_kw = ["fecha essa janela", "fecha a janela", "minimiza",
                     "maximiza", "workspace", "tela cheia", "fullscreen",
                     "janela para esquerda", "janela para direita"]
        if any(w in cmd_norm for w in window_kw):
            result = self.wm.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Clipboard ──────────────────────────────────────────
        clipboard_kw = ["area de transferencia", "clipboard", "o que tem no clipboard"]
        if any(w in cmd_norm for w in clipboard_kw):
            result = self.clipboard.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Screenshot ─────────────────────────────────────────
        screenshot_kw = ["screenshot", "tira print", "tira um print",
                         "captura a tela", "print screen"]
        if any(w in cmd_norm for w in screenshot_kw):
            import subprocess, datetime
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"/home/pera/Pictures/luna_screenshot_{ts}.png"
            try:
                subprocess.run(["scrot", path], check=True, timeout=5)
                return {"success": True, "message": f"📸 Screenshot salvo em {path}"}
            except FileNotFoundError:
                try:
                    subprocess.run(["gnome-screenshot", "-f", path], check=True, timeout=5)
                    return {"success": True, "message": f"📸 Screenshot salvo em {path}"}
                except Exception as e:
                    return {"success": True, "message": f"Não foi possível tirar o print: {e}"}
            except Exception as e:
                return {"success": True, "message": f"Erro ao capturar tela: {e}"}

        # ── Foco / Pomodoro ────────────────────────────────────
        focus_kw = ["modo foco", "pomodoro", "iniciar foco",
                    "sessao de foco", "sessão de foco", "foco por", "cancela o foco"]
        if any(w in cmd_norm for w in focus_kw):
            result = self.focus.handle(cmd_clean)
            if result:
                return {"success": True, "message": result}

        # ── Luna Writing ───────────────────────────────────────
        writing_kw = ["modo escrita", "luna writing", "corrige o texto", "corrige esse texto",
                      "resume o texto", "resume esse texto", "melhora o texto", "melhora esse texto"]
        if any(w in cmd_norm for w in writing_kw):
            m_fix = re.search(r'(?:corrige|melhora)\s+(?:o\s+|esse\s+)?texto[:\s]+(.+)', cmd_clean, re.I)
            m_sum = re.search(r'resume\s+(?:o\s+|esse\s+)?texto[:\s]+(.+)', cmd_clean, re.I)
            if m_fix:
                result = self.writing.fix_text(m_fix.group(1).strip())
                return {"success": True, "message": result}
            if m_sum:
                result = self.writing.summarize(m_sum.group(1).strip())
                return {"success": True, "message": result}
            return {"success": True, "message": "✍ Modo escrita ativo. Dite o texto e eu sugiro melhorias."}

        # ── Luna Math ──────────────────────────────────────────
        math_kw = ["calcula", "calcule", "quanto e", "quanto é", "quanto da", "quanto dá",
                   "lousa matematica", "luna math", "resolve", "resolva"]
        if any(w in cmd_norm for w in math_kw):
            # Tenta extrair expressão numérica
            expr_m = re.search(r'(?:calcula|calcule|resolve|resolva)\s+(.+)', cmd_clean, re.I)
            if expr_m:
                expr = expr_m.group(1).strip()
                result_val, ok = self.math.evaluate(expr)
                if ok:
                    explanation = self.math.explain(expr, result_val)
                    return {"success": True, "message": f"🧮 {expr} = {result_val}\n{explanation}"}
                return {"success": True, "message": f"🧮 {result_val}"}
            # Pergunta matemática em linguagem natural
            q_m = re.search(r'(?:quanto e|quanto é|quanto da|quanto dá|me explica|explica)\s+(.+)', cmd_clean, re.I)
            if q_m:
                answer = self.math.ask(q_m.group(1).strip())
                return {"success": True, "message": f"🧮 {answer}"}
            return {"success": True, "message": "🧮 Modo matemática ativo. Me diga o cálculo ou a pergunta."}

        # ── Luna BFF ───────────────────────────────────────────
        bff_kw = ["modo bff", "luna bff", "meu hobby", "meus hobbys", "meus hobbies",
                  "adiciona hobby", "adiciona meu hobby", "me explica", "o que e", "o que é",
                  "estou triste", "estou feliz", "estou ansioso", "me sinto", "preciso desabafar",
                  "me anima", "me ajuda", "tô mal", "to mal", "tô bem", "to bem"]
        if any(w in cmd_norm for w in bff_kw):
            # Hobby
            h_m = re.search(r'(?:adiciona|meu)\s+hobby[:\s]+(.+)', cmd_clean, re.I)
            if h_m:
                return {"success": True, "message": self.bff.add_hobby(h_m.group(1).strip())}
            if any(w in cmd_norm for w in ["meus hobbys", "meus hobbies", "meu hobby"]):
                return {"success": True, "message": self.bff.list_hobbies()}
            # Wiki
            wiki_m = re.search(r'(?:me explica|o que e|o que é|explica)\s+(.+)', cmd_clean, re.I)
            if wiki_m:
                return {"success": True, "message": self.bff.wiki(wiki_m.group(1).strip())}
            # Apoio emocional / chat
            return {"success": True, "message": self.bff.chat(cmd_clean)}

        # ── Luna Automation ────────────────────────────────────
        auto_kw = ["automacao", "automação", "luna automation", "casa inteligente",
                   "liga a luz", "desliga a luz", "liga o ar", "desliga o ar", "esp32"]
        if any(w in cmd_norm for w in auto_kw):
            dev_m = re.search(r'(?:liga|desliga)\s+(?:a\s+|o\s+)?(.+)', cmd_clean, re.I)
            if dev_m:
                return {"success": True, "message": self.automation.toggle_device(dev_m.group(1).strip())}
            return {"success": True, "message": self.automation.status()}

        # ── Luna Eyes ──────────────────────────────────────────
        eyes_kw = ["luna eyes", "modo camera", "modo câmera", "vigilancia", "vigilância",
                   "ativa camera", "ativa câmera", "para vigilancia", "para vigilância",
                   "cameras ativas", "câmeras ativas", "status das cameras"]
        if any(w in cmd_norm for w in eyes_kw):
            if any(w in cmd_norm for w in ["ativa camera", "ativa câmera", "inicia vigilancia", "inicia vigilância"]):
                cam_m = re.search(r'camera\s+(\d+)', cmd_norm)
                cam_id = int(cam_m.group(1)) if cam_m else 0
                return {"success": True, "message": self.eyes.start_watch(cam_id)}
            if any(w in cmd_norm for w in ["para vigilancia", "para vigilância", "desativa camera"]):
                return {"success": True, "message": self.eyes.stop_watch()}
            if any(w in cmd_norm for w in ["cameras ativas", "câmeras ativas", "status das cameras"]):
                return {"success": True, "message": self.eyes.list_cameras()}
            return {"success": True, "message": self.eyes.status()}

        # ── Pesquisa Web ───────────────────────────────────────
        web_match = re.match(
            r'^(?:pesquise|busque|pesquisa|busca|pesquisar|buscar)\s+(?:sobre\s+|por\s+)?(.+)',
            cmd_norm
        )
        if web_match:
            query = web_match.group(1).strip()
            # Usa o texto original para preservar acentos na query
            orig_match = re.match(
                r'^(?:pesquise|busque|pesquisa|busca|pesquisar|buscar)\s+(?:sobre\s+|por\s+)?(.+)',
                cmd_clean
            )
            query = orig_match.group(1).strip() if orig_match else query
            result = self.search_web(query)
            if result.get("success"):
                return {"success": True, "message": f"🔍 Pesquisando: {query}"}
            return result

        # ── Ações de sistema básicas ───────────────────────────

        # Open App
        m = re.match(r"^(?:abra|abrir)\s+(?:o\s+|a\s+)?(.+)", cmd_norm)
        if m:
            app_name = re.sub(r"[\.\!\?].*$", "", m.group(1).strip()).strip()
            return self.open_app(app_name)

        # Scroll
        m = re.match(r"^(?:role|scroll|desce|sobe|rolar)(?:\s+(.*))?", cmd_norm)
        if m:
            direction = "up" if any(w in cmd_norm for w in ["cima", "up", "sobe"]) else "down"
            amount = 5 if any(w in cmd_norm for w in ["muito", "bastante"]) else 2
            return self.scroll(direction, amount)

        # ── Click inteligente ──────────────────────────────────
        # Detecta qualquer forma de "clicar em algo" incluindo ordinais e tipos
        _click_m = re.match(
            r"^(?:clique|clica|clicando|pressiona|seleciona|selecione|escolhe|escolha|entra|entre)\s+"
            r"(?:em\s+|no\s+|na\s+|nos\s+|nas\s+|o\s+|a\s+|os\s+|as\s+)?(.+)",
            cmd_norm
        )
        if _click_m:
            raw_target = _click_m.group(1).strip()
            result = _resolve_click(raw_target, cmd_norm, self)
            if result:
                return result

        # Type
        m = re.match(r"^(?:digite|digita|digitar)\s+(.+)", cmd_norm)
        if m:
            return self.type_text(m.group(1).strip())

        # Keys
        key_map = {
            ("enter", "da enter", "pressione enter", "aperta enter"): "enter",
            ("escape", "esc", "aperta esc", "pressione esc"): "escape",
            ("tab", "aperta tab", "pressione tab"): "tab",
        }
        for triggers, key in key_map.items():
            if cmd_norm in triggers:
                return self.press_key(key)

        # ── Browser Agent (AI Computer Agent) ─────────────────
        browser_kw = [
            "navega para", "navegar para", "abre o site", "abra o site",
            "vai para o site", "acessa o site", "acesse o site",
            "no browser", "no firefox", "no navegador",
            "faz no browser", "faz no firefox", "faz no navegador",
            "browser agent", "agente browser",
        ]
        if any(w in cmd_norm for w in browser_kw):
            url_m = re.search(r'https?://\S+', cmd_clean)
            if url_m:
                result = self.browser_agent.navigate(url_m.group())
            else:
                result = self.browser_agent.run(cmd_clean)
            return {"success": True, "message": result}

        return {"success": False, "message": f"Comando não reconhecido: '{cmd}'"}


# Singleton
_executor_instance: Optional[ActionExecutor] = None

def get_executor() -> ActionExecutor:
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = ActionExecutor()
    return _executor_instance
