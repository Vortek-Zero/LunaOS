#!/usr/bin/env python3
"""
actions/spotify.py — Controle do Spotify via spotipy (Web API).

Configuração necessária (variáveis de ambiente ou config.py):
  SPOTIPY_CLIENT_ID     — Client ID do app no Spotify Developer Dashboard
  SPOTIPY_CLIENT_SECRET — Client Secret
  SPOTIPY_REDIRECT_URI  — ex: http://localhost:8888/callback

Na primeira execução, abrirá o browser para autorização OAuth.
O token é salvo em ~/.cache-luna_spotify para reutilização.

Comportamento:
  - Se o Spotify não estiver aberto, abre o app automaticamente e aguarda.
  - search_and_play faz uma busca real e força a reprodução da música pedida.
  - Volume, próxima, anterior, pausar e retomar funcionam sem Spotify aberto
    (o app é aberto se necessário).
"""
import os
import re
import json
import time
import subprocess
import threading
from pathlib import Path
from typing import Optional

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    HAS_SPOTIPY = True
except ImportError:
    HAS_SPOTIPY = False

SCOPE = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing "
    "app-remote-control "
    "streaming"
)

_CACHE_PATH = os.path.expanduser("~/.cache-luna_spotify")
_APPS_JSON  = Path(__file__).parent.parent / "config" / "apps.json"

# Tempo máximo para aguardar o Spotify abrir e aparecer como device (segundos)
_OPEN_TIMEOUT = 20


def _load_spotify_command() -> list[str]:
    """Lê o comando de abertura do Spotify direto do apps.json."""
    try:
        apps = json.loads(_APPS_JSON.read_text(encoding="utf-8"))
        cmd_str = apps.get("spotify", {}).get("command", "")
        if cmd_str:
            return cmd_str.split()  # ex: ["flatpak", "run", "com.spotify.Client"]
    except Exception as e:
        print(f"[Spotify] Aviso: não leu apps.json: {e}")
    # Fallbacks caso apps.json não tenha
    return ["flatpak", "run", "com.spotify.Client"]


def _make_sp() -> Optional["spotipy.Spotify"]:
    """Cria cliente Spotify autenticado. Retorna None se credenciais ausentes."""
    if not HAS_SPOTIPY:
        return None
    client_id = os.getenv("SPOTIPY_CLIENT_ID", "")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", "")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")
    if not client_id or not client_secret:
        return None
    try:
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=SCOPE,
            cache_path=_CACHE_PATH,
            open_browser=True,
        )
        return spotipy.Spotify(auth_manager=auth)
    except Exception as e:
        print(f"[Spotify] Erro de autenticação: {e}")
        return None


class SpotifyManager:
    """Controla o Spotify via Web API com auto-abertura do app e fallback gracioso."""

    def __init__(self):
        self._sp: Optional["spotipy.Spotify"] = None
        self._ready = False
        self._free_mode = False  # True quando conta é Free (sem API premium)
        self._open_lock = threading.Lock()
        self._autoplay_stop = threading.Event()  # cancela autoplay em andamento

        if not HAS_SPOTIPY:
            print("[Spotify] spotipy não instalado.")
            return
        if not os.getenv("SPOTIPY_CLIENT_ID"):
            print("[Spotify] ⚠ SPOTIPY_CLIENT_ID não definido. Spotify desabilitado.")
            return
        try:
            self._sp = _make_sp()
            if self._sp:
                try:
                    self._sp.current_user()
                    self._ready = True
                    print("[Spotify] ✓ Conectado à conta Spotify Premium.")
                except Exception as e:
                    err = str(e)
                    if "403" in err or "premium" in err.lower():
                        # Conta Free: ainda podemos abrir músicas via URI
                        self._ready = True
                        self._free_mode = True
                        print("[Spotify] ✓ Conectado (conta Free). Usando modo playerctl/xdg-open.")
                    else:
                        raise
        except Exception as e:
            print(f"[Spotify] ⚠ Não foi possível conectar: {e}")

    @property
    def available(self) -> bool:
        return self._ready and self._sp is not None

    # ── Gerenciamento de devices ───────────────────────────────

    def _is_spotify_running(self) -> bool:
        """Verifica se o processo do Spotify está rodando."""
        try:
            result = subprocess.run(
                ["pgrep", "-x", "spotify"],
                capture_output=True, timeout=2
            )
            return result.returncode == 0
        except Exception:
            return False

    def _open_spotify_app(self) -> bool:
        """
        Abre o Spotify usando o comando definido em apps.json.
        Aguarda até _OPEN_TIMEOUT segundos o device aparecer na API.
        Retorna True se um device ficou disponível.
        """
        with self._open_lock:
            # Já tem device disponível?
            if self._get_device_id() is not None:
                return True

            # Lê o comando do apps.json
            cmd = _load_spotify_command()
            print(f"[Spotify] Abrindo app: {' '.join(cmd)}")
            try:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except FileNotFoundError:
                print(f"[Spotify] ⚠ Comando não encontrado: {cmd[0]}")
                return False
            except Exception as e:
                print(f"[Spotify] ⚠ Falha ao abrir app: {e}")
                return False

            # Aguarda o device aparecer na API (polling)
            print(f"[Spotify] Aguardando device ficar disponível (até {_OPEN_TIMEOUT}s)...")
            deadline = time.time() + _OPEN_TIMEOUT
            while time.time() < deadline:
                time.sleep(1.5)
                device_id = self._get_device_id()
                if device_id:
                    print(f"[Spotify] ✓ Device disponível: {device_id}")
                    return True

            print("[Spotify] ⚠ Timeout: Spotify iniciou mas device não apareceu na API.")
            return False

    def _get_device_id(self) -> Optional[str]:
        """
        Retorna o ID do device Spotify ativo.
        Prioriza devices ativos (is_active=True), depois qualquer disponível.
        Retorna None se nenhum device estiver disponível.
        """
        try:
            devices = self._sp.devices()
            devs = devices.get("devices", [])

            # Primeiro: device marcado como ativo
            for d in devs:
                if d.get("is_active"):
                    return d["id"]

            # Segundo: qualquer device disponível (não restrito)
            for d in devs:
                if not d.get("is_restricted", False):
                    return d["id"]

            return None
        except Exception as e:
            print(f"[Spotify] Erro ao listar devices: {e}")
            return None

    def _ensure_device(self) -> Optional[str]:
        """
        Garante que existe um device disponível e ATIVO.
        Abre o Spotify se necessário e transfere a reprodução para ele.
        Retorna o device_id ou None.
        """
        device_id = self._get_device_id()

        if not device_id:
            # Tenta abrir o app e aguardar
            opened = self._open_spotify_app()
            if not opened:
                return None
            device_id = self._get_device_id()

        if not device_id:
            return None

        # Transfere reprodução para o device e o ativa
        # force_play=True garante que o device fica pronto para receber comandos
        try:
            self._sp.transfer_playback(device_id=device_id, force_play=False)
            time.sleep(1.0)  # dá tempo de o device processar a transferência
        except Exception as e:
            print(f"[Spotify] transfer_playback falhou (ignorado): {e}")

        return device_id

    # ── Controles básicos ─────────────────────────────────────

    def play(self) -> str:
        """Retoma a reprodução atual."""
        if not self.available:
            return self._unavailable()
        try:
            device_id = self._ensure_device()
            if not device_id:
                return "⚠ Spotify: nenhum dispositivo disponível. Abra o app primeiro."
            self._sp.start_playback(device_id=device_id)
            return "▶ Spotify: reproduzindo."
        except Exception as e:
            return f"[Spotify] Erro ao reproduzir: {e}"

    def pause(self) -> str:
        """Pausa a reprodução."""
        if not self.available:
            return self._unavailable()
        try:
            device_id = self._ensure_device()
            if not device_id:
                return "⚠ Spotify: nenhum dispositivo disponível."
            self._sp.pause_playback(device_id=device_id)
            return "⏸ Spotify: pausado."
        except Exception as e:
            return f"[Spotify] Erro ao pausar: {e}"

    def next_track(self) -> str:
        """Avança para a próxima faixa."""
        if not self.available:
            return self._unavailable()
        try:
            device_id = self._ensure_device()
            if not device_id:
                return "⚠ Spotify: nenhum dispositivo disponível."
            self._sp.next_track(device_id=device_id)
            time.sleep(0.5)
            return "⏭ Spotify: próxima faixa. " + self._current_track_info()
        except Exception as e:
            return f"[Spotify] Erro: {e}"

    def prev_track(self) -> str:
        """Volta para a faixa anterior."""
        if not self.available:
            return self._unavailable()
        try:
            device_id = self._ensure_device()
            if not device_id:
                return "⚠ Spotify: nenhum dispositivo disponível."
            self._sp.previous_track(device_id=device_id)
            time.sleep(0.5)
            return "⏮ Spotify: faixa anterior. " + self._current_track_info()
        except Exception as e:
            return f"[Spotify] Erro: {e}"

    def now_playing(self) -> str:
        """Informa a música que está tocando agora."""
        if not self.available:
            return self._unavailable()
        try:
            current = self._sp.current_playback()
            if not current or not current.get("item"):
                return "Nenhuma música tocando no Spotify no momento."
            info = self._current_track_info()
            is_playing = current.get("is_playing", False)
            icon = "▶" if is_playing else "⏸"
            return f"{icon} {info}"
        except Exception as e:
            return f"[Spotify] Erro: {e}"

    def set_volume(self, level: int) -> str:
        """Define o volume (0-100)."""
        if not self.available:
            return self._unavailable()
        level = max(0, min(100, level))
        try:
            device_id = self._ensure_device()
            if not device_id:
                return "⚠ Spotify: nenhum dispositivo disponível."
            self._sp.volume(level, device_id=device_id)
            return f"🔊 Spotify: volume {level}%."
        except Exception as e:
            return f"[Spotify] Erro ao ajustar volume: {e}"

    def search_and_play(self, query: str, autoplay: bool = False) -> str:
        """
        Busca uma música/artista e começa a tocar.
        Estratégia em camadas:
          1. Busca a faixa via API para obter o URI/track_id
          2. Tenta Web API (start_playback) com garantia de device
          3. Fallback: xdg-open spotify:track:ID — abre o app E toca a faixa diretamente
        """
        if not self.available:
            return self._unavailable()

        query = query.strip()
        print(f"[Spotify] Buscando: '{query}'")

        # ── Passo 1: Buscar a faixa pela API ──────────────────────────────────
        uri, label = self._search_best_match(query)
        if not uri:
            return f"🔍 Spotify: nenhum resultado encontrado para '{query}'."

        track_id = uri.split(":")[-1]

        # ── Passo 2: Tenta via Web API (melhor controle) ──────────────────────
        try:
            device_id = self._ensure_device()

            if device_id:
                result = self._start_playback_with_retry(device_id=device_id, uris=[uri])
                if result == "ok":
                    print(f"[Spotify] ✓ Web API: tocando {label}")
                    if autoplay:
                        self._autoplay_next(label, uri)
                    return f"▶ Tocando: {label}"
                print(f"[Spotify] Web API falhou após retries: {result}")
            else:
                print("[Spotify] Nenhum device disponível — usando fallback URI.")

        except Exception as e:
            print(f"[Spotify] Web API erro: {e} — tentando fallback URI.")

        # ── Passo 3: Fallback via URI scheme do Spotify ───────────────────────
        print(f"[Spotify] Fallback: spotify:track:{track_id}")
        try:
            subprocess.Popen(
                ["xdg-open", f"spotify:track:{track_id}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if autoplay:
                self._autoplay_next(query, uri)
            return f"▶ Abrindo Spotify e tocando: {label}"
        except Exception as e:
            return f"[Spotify] Erro ao abrir via URI: {e}"

        for attempt in range(max_retries):
            try:
                self._sp.start_playback(device_id=device_id, uris=uris)
                return "ok"
            except spotipy.SpotifyException as e:
                # Se der erro 403 Premium, usamos xdg-open para burlar a limitação da API
                if e.http_status == 403 and "premium" in str(e).lower():
                    print("[Spotify] Conta Free detectada (Erro 403). Usando xdg-open como fallback para tocar música!")
                    if uris:
                        try:
                            subprocess.Popen(["xdg-open", uris[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            return "ok (fallback free)"
                        except Exception as ex:
                            return f"Erro no fallback: {ex}"
                    return "Nenhuma música para o fallback."

                reason = getattr(e, 'reason', '') or ''
                is_no_device = (reason == 'NO_ACTIVE_DEVICE' or e.http_status == 404)

                if is_no_device and attempt < max_retries - 1:
                    print(f"[Spotify] NO_ACTIVE_DEVICE — aguardando 3s e tentando novamente... (tentativa {attempt + 1})")
                    time.sleep(3)
                    # Tenta reativar o device
                    try:
                        new_id = self._get_device_id()
                        if new_id:
                            device_id = new_id
                            self._sp.transfer_playback(device_id=device_id, force_play=False)
                            time.sleep(1)
                    except Exception:
                        pass
                    continue  # Tenta de novo
                raise  # Re-lança para o caller tratar
        return "⚠ Spotify: não foi possível iniciar reprodução após várias tentativas."

    def _search_best_match(self, query: str) -> tuple[Optional[str], str]:
        """
        Busca o melhor resultado para a query.
        Se conta for Free, usa playerctl para pesquisa local ou retorna URI genérico.
        """
        if self._free_mode:
            # Modo Free: abre a busca do Spotify via URI deep-link
            encoded = query.replace(" ", "%20")
            uri = f"spotify:search:{encoded}"
            print(f"[Spotify] Modo Free → buscando via URI: {uri}")
            try:
                subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            return None, f"🎵 Abrindo busca no Spotify por: {query}"

        # Busca por faixa (conta Premium)
        try:
            results = self._sp.search(q=query, limit=3, type="track")
            tracks = results.get("tracks", {}).get("items", [])
            if tracks:
                track = tracks[0]
                uri = track["uri"]
                title = track["name"]
                artist = track["artists"][0]["name"]
                label = f"{artist} — {title} [Spotify]"
                print(f"[Spotify] Faixa encontrada: {label}")
                return uri, label
        except Exception as e:
            print(f"[Spotify] Erro na busca por faixa: {e}")

        # Fallback: busca por artista → pega top track
        try:
            results = self._sp.search(q=query, limit=1, type="artist")
            artists = results.get("artists", {}).get("items", [])
            if artists:
                artist_id = artists[0]["id"]
                artist_name = artists[0]["name"]
                top = self._sp.artist_top_tracks(artist_id, country="BR")
                top_tracks = top.get("tracks", [])
                if top_tracks:
                    track = top_tracks[0]
                    uri = track["uri"]
                    title = track["name"]
                    label = f"{artist_name} — {title} (top track) [Spotify]"
                    print(f"[Spotify] Artista → top track: {label}")
                    return uri, label
        except Exception as e:
            print(f"[Spotify] Erro na busca por artista: {e}")

        return None, ""

    def _current_track_info(self) -> str:
        """Retorna 'Artista — Título' da música atual, ou string vazia."""
        try:
            current = self._sp.current_playback()
            if current and current.get("item"):
                item = current["item"]
                title = item["name"]
                artist = item["artists"][0]["name"]
                return f"{artist} — {title}"
        except Exception:
            pass
        return ""

    def _unavailable(self) -> str:
        if not HAS_SPOTIPY:
            return "spotipy não instalado. Execute: pip install spotipy"
        if not os.getenv("SPOTIPY_CLIENT_ID"):
            return "Configure SPOTIPY_CLIENT_ID e SPOTIPY_CLIENT_SECRET para usar o Spotify."
        return "Spotify não disponível no momento."

    # ── Autoplay inteligente ───────────────────────────────────

    def _llm_suggest_next(self, current_track: str) -> Optional[str]:
        """Pede ao LLM uma música que combine com a atual."""
        import requests as _req, json as _json
        from config import MODELS, OLLAMA_GENERATE_URL
        prompt = (
            f'A música "{current_track}" acabou de tocar. '
            f'Sugira UMA música diferente que combine com o mesmo ritmo/estilo. '
            f'Responda APENAS com: NOME DA MÚSICA - ARTISTA. Sem explicações.'
        )
        try:
            resp = _req.post(OLLAMA_GENERATE_URL, json={
                "model": MODELS["fast"],
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 30},
            }, timeout=15)
            suggestion = resp.json().get("response", "").strip()
            # Remove prefixos como "1.", "*", etc.
            suggestion = re.sub(r'^[\d\.\*\-\s]+', '', suggestion).strip()
            return suggestion if len(suggestion) > 3 else None
        except Exception:
            return None

    def _autoplay_next(self, current_track: str, current_uri: str):
        """Espera a faixa terminar via playerctl e toca uma sugestão do LLM."""
        self._autoplay_stop.clear()

        def _run():
            # Aguarda começar a tocar
            for _ in range(10):
                if self._autoplay_stop.is_set():
                    return
                if self._playerctl("status") == "Playing":
                    break
                time.sleep(1)

            initial_trackid = self._playerctl("metadata", "mpris:trackid")

            # Espera terminar usando posição/duração
            while not self._autoplay_stop.is_set():
                time.sleep(2)
                status = self._playerctl("status")
                if status in ("Stopped", ""):
                    break
                cur = self._playerctl("metadata", "mpris:trackid")
                if initial_trackid and cur and cur != initial_trackid:
                    return
                try:
                    length_s = int(self._playerctl("metadata", "mpris:length")) / 1_000_000
                    position_s = float(self._playerctl("position"))
                    if length_s > 0 and (length_s - position_s) <= 3:
                        time.sleep(3)
                        break
                except (ValueError, TypeError):
                    pass

            if self._autoplay_stop.is_set():
                return

            suggestion = self._llm_suggest_next(current_track)
            if not suggestion:
                return

            print(f"[Spotify] 🎵 Autoplay: {suggestion}")
            from voice.tts import get_tts
            get_tts().speak(f"Que tal: {suggestion}?", blocking=False)

            if self.available:
                self.search_and_play(suggestion)
            else:
                self.search_and_play_local(suggestion)

        threading.Thread(target=_run, daemon=True).start()

    # ── Modo local (sem API) via xdg-open + playerctl ─────────

    def _playerctl(self, *args) -> str:
        try:
            r = subprocess.run(
                ["playerctl", "--player=spotify"] + list(args),
                capture_output=True, text=True, timeout=3
            )
            return r.stdout.strip()
        except Exception:
            return ""

    def _open_spotify_if_needed(self):
        """Abre o Spotify via apps.json se não estiver rodando."""
        if self._is_spotify_running():
            return
        cmd = _load_spotify_command()
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
        except Exception as e:
            print(f"[Spotify] Falha ao abrir: {e}")

    def search_and_play_local(self, query: str, autoplay: bool = False) -> str:
        """Toca via URI spotify: usando o handler do sistema (xdg-open)."""
        import urllib.parse
        self._open_spotify_if_needed()
        encoded = urllib.parse.quote(query)
        subprocess.Popen(
            ["xdg-open", f"spotify:search:{encoded}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for _ in range(8):
            time.sleep(1.5)
            status = self._playerctl("status")
            if status in ("Playing", "Paused"):
                if status == "Paused":
                    self._playerctl("play")
                break
        if autoplay:
            self._autoplay_next(query, "")
        return f"▶ Buscando no Spotify: {query}"

    def handle_local(self, text: str) -> Optional[str]:
        """Controles básicos via playerctl quando API não está disponível."""
        tl = text.lower().strip()

        m = re.search(r'volume\s+(?:para\s+|em\s+|no\s+)?(\d+)', tl)
        if m:
            self._playerctl("volume", f"{int(m.group(1)) / 100:.2f}")
            return f"🔊 Volume {m.group(1)}%."

        if any(w in tl for w in ["pausa", "pause", "pausar", "para a música", "para a musica"]):
            self._playerctl("pause")
            return "⏸ Spotify pausado."

        if any(w in tl for w in ["próxima", "proxima", "next", "avança"]):
            self._playerctl("next")
            return "⏭ Próxima faixa."

        if any(w in tl for w in ["anterior", "voltar", "previous"]):
            self._playerctl("previous")
            return "⏮ Faixa anterior."

        if any(w in tl for w in ["continua", "retoma", "play", "toca música", "toca musica"]):
            self._open_spotify_if_needed()
            self._playerctl("play")
            return "▶ Reproduzindo."

        if any(w in tl for w in ["que música", "que musica", "o que está tocando", "música atual"]):
            title = self._playerctl("metadata", "title")
            artist = self._playerctl("metadata", "artist")
            if title:
                return f"▶ {artist} — {title}" if artist else f"▶ {title}"
            return "Nenhuma música tocando."

        search_pattern = re.search(
            r'(?:toca|coloca|play|reproduz|quero ouvir|bota|pe?de?)\s+'
            r'(?:a m[uú]sica\s+|a faixa\s+|o artista\s+|o album\s+)?(.+)',
            tl
        )
        if search_pattern:
            query = search_pattern.group(1).strip()
            generic = {"música", "musica", "uma música", "uma musica", "agora", "algo", "uma", "um"}
            if query and query not in generic and len(query) > 1:
                self._autoplay_stop.set()
                return self.search_and_play_local(query, autoplay=True)

        return None

    # ── Interface natural ──────────────────────────────────────

    def handle(self, text: str) -> Optional[str]:
        """Processa comandos de voz/texto relacionados ao Spotify."""
        if not self.available:
            return self.handle_local(text)

        tl = text.lower().strip()

        # Volume com valor numérico — vários formatos
        # Ex: "volume 70", "volume para 70", "coloca no volume 70", "volume em 70"
        m = re.search(r'volume\s+(?:para\s+|em\s+|no\s+)?(\d+)', tl)
        if m:
            return self.set_volume(int(m.group(1)))

        # Volume em formato alternativo: "coloca no 70"
        m = re.search(r'(?:coloca|deixa|bota)\s+(?:no|em)\s+(\d+)', tl)
        if m:
            return self.set_volume(int(m.group(1)))

        # Busca por nome específico — DEVE vir antes dos controles genéricos
        # Captura: "toca [nome]", "coloca [nome]", "play [nome]", "quero ouvir [nome]"
        search_pattern = re.search(
            r'(?:toca|coloca|play|reproduz|quero ouvir|bota|pe?de?)\s+'
            r'(?:a m[uú]sica\s+|a faixa\s+|o artista\s+|o album\s+)?(.+)',
            tl
        )
        if search_pattern:
            query = search_pattern.group(1).strip()
            # Remove palavras de controle que não são nomes de música
            generic = {"música", "musica", "uma música", "uma musica", "agora",
                       "algo", "uma", "um", "o", "a"}
            if query and query not in generic and len(query) > 1:
                self._autoplay_stop.set()  # cancela autoplay anterior
                return self.search_and_play(query, autoplay=True)

        # Controles de faixa — cancelam autoplay em andamento
        if any(w in tl for w in ["próxima música", "proxima musica", "próxima faixa",
                                   "proxima faixa", "next", "avança música"]):
            return self.next_track()

        if any(w in tl for w in ["música anterior", "musica anterior", "faixa anterior",
                                   "voltar música", "anterior"]):
            return self.prev_track()

        # Pausa (antes de "toca"/"play" para evitar conflito)
        if any(w in tl for w in ["pausa", "pause", "pausar", "para a música",
                                   "para a musica", "parar música", "parar musica"]):
            return self.pause()

        # Play genérico (retoma)
        if any(w in tl for w in ["toca música", "toca musica", "play", "reproduz",
                                   "continua", "continuar música", "retoma"]):
            return self.play()

        # Música atual
        if any(w in tl for w in ["que música", "que musica", "o que está tocando",
                                   "qual música", "música atual", "o que toca"]):
            return self.now_playing()

        return None


# Singleton
_spotify_instance: Optional[SpotifyManager] = None


def get_spotify() -> SpotifyManager:
    global _spotify_instance
    if _spotify_instance is None:
        _spotify_instance = SpotifyManager()
    return _spotify_instance
