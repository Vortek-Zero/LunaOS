#!/usr/bin/env python3
"""
actions/playlist_builder.py — Playlist inteligente via LLM (Qwen 2.5 3B)

Detecção de intenção via LLM leve — aceita pedidos expressivos:
  "cria uma playlist para estudar calma pop"
  "toca top 10 melhores eletrônicas de 2026"
  "monta 20 músicas de jazz relaxante"

Pular: "pula", "próxima", "skip" → avança para a próxima da sequência gerada.
"""
import re
import threading
import time
from typing import Optional

from config import MODELS, OLLAMA_GENERATE_URL


# ── Detecção de intenção via LLM leve ────────────────────────

_INTENT_PROMPT = """Analise o texto e responda em JSON com exatamente estas chaves:
- "is_playlist": true se for pedido de playlist/músicas, false caso contrário
- "genre": descrição do estilo/humor/contexto (ex: "pop calmo para estudar", "eletrônica", "rock anos 80")
- "count": número de músicas pedido, ou null se não especificado

Texto: "{text}"

JSON:"""


def detect_playlist_intent(text: str) -> Optional[dict]:
    """
    Usa o modelo fast (0.5B) para detectar intenção de playlist.
    Retorna {genre, count} ou None.
    """
    import requests as _req
    import json as _json

    tl = re.sub(r'^(?:luna)[,:\s]+', '', text.lower().strip()).strip()

    # Pré-filtro rápido: se não tem nenhuma palavra-chave, nem chama o LLM
    _kw = ["playlist", "top ", "músicas", "musicas", "monta ", "cria ",
           "faz ", "quero ouvir"]
    if not any(k in tl for k in _kw):
        return None

    # Regex rápido para "top N gênero" e "toca top N gênero" (evita chamar LLM)
    m = re.match(r'(?:toca\s+)?top\s+(\d+)\s+(?:melhores?\s+)?(.+?)(?:\s+de\s+\d{4})?$', tl)
    if m:
        count = max(1, min(1000, int(m.group(1))))
        genre = re.sub(r'\b(?:musicas?|músicas?|melhores?|hits?)\b', '', m.group(2), flags=re.I).strip()
        if genre:
            return {"genre": genre, "count": count}

    payload = {
        "model": MODELS["main"],
        "prompt": _INTENT_PROMPT.format(text=tl),
        "stream": False,
        "format": "json",
        "keep_alive": "10m",
        "options": {"temperature": 0.1, "num_predict": 80},
    }

    try:
        resp = _req.post(OLLAMA_GENERATE_URL, json=payload, timeout=15)
        resp.raise_for_status()
        data = _json.loads(resp.json().get("response", "{}"))
        if not data.get("is_playlist"):
            return None
        genre = str(data.get("genre") or "").strip()
        count = data.get("count")
        if not genre:
            return None
        if count is not None:
            try:
                count = max(1, min(1000, int(count)))
            except (ValueError, TypeError):
                count = None
        return {"genre": genre, "count": count}
    except Exception:
        return None


# ── Geração de playlist via LLM ───────────────────────────────

_PLAYLIST_PROMPT = """Você é um especialista em música. Gere uma lista de {count} músicas reais e populares para: "{genre}".

REGRAS:
- Formato EXATO: NÚMERO. NOME DA MÚSICA - ARTISTA
- Sem explicações, cabeçalhos ou rodapés
- Apenas músicas reais
"""


def generate_playlist_with_llm(genre: str, count: int) -> list[str]:
    """Gera lista via streaming, imprimindo tokens em tempo real."""
    import requests as _req
    import json as _json

    prompt = _PLAYLIST_PROMPT.format(genre=genre, count=count)
    payload = {
        "model": MODELS["main"],
        "prompt": prompt,
        "stream": True,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.3,
            "top_p": 0.90,
            "num_predict": min(count * 35, 8000),
            "top_k": 40,
            "repeat_penalty": 1.1,
        },
    }

    print(f"\n[Playlist] 🎵 Montando {count} músicas de '{genre}'...\n")
    raw = ""
    try:
        resp = _req.post(OLLAMA_GENERATE_URL, json=payload, timeout=180, stream=True)
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = _json.loads(line.decode("utf-8")).get("response", "")
            print(chunk, end="", flush=True)
            raw += chunk
    except Exception as e:
        print(f"\n[Playlist] Erro LLM: {e}")
        return []

    print("\n")
    return _parse_track_list(raw, count)


def _parse_track_list(raw: str, max_count: int) -> list[str]:
    tracks = []
    for line in raw.splitlines():
        line = re.sub(r'^\d+[\.\)\-\s]+', '', line.strip()).strip()
        if len(line) > 3:
            tracks.append(line)
        if len(tracks) >= max_count:
            break
    return tracks


# ── PlaylistBuilder ───────────────────────────────────────────

class PlaylistBuilder:

    def __init__(self):
        self._spotify = None
        self._current_thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._skip_flag = threading.Event()   # sinaliza pular para próxima
        self._pending_genre: Optional[str] = None
        self._active = False                  # True enquanto playlist roda

    @property
    def spotify(self):
        if self._spotify is None:
            from actions.spotify import get_spotify
            self._spotify = get_spotify()
        return self._spotify

    def handle(self, text: str) -> Optional[str]:
        tl = re.sub(r'^(?:luna)[,:\s]+', '', text.lower().strip()).strip()

        # ── Pular música (só quando playlist ativa) ───────────
        if self._active and any(w in tl for w in [
            "pula", "pular", "próxima", "proxima", "skip", "avança", "avanca",
            "próxima música", "proxima musica"
        ]):
            self._skip_flag.set()
            return "⏭ Pulando para a próxima da playlist..."

        # ── Parar playlist ────────────────────────────────────
        if any(w in tl for w in ["para playlist", "cancela playlist", "stop playlist", "para a playlist"]):
            return self.stop()

        # ── Resposta a pergunta de quantidade pendente ────────
        if self._pending_genre:
            m = re.search(r'(\d+)', tl)
            if m:
                count = max(1, min(1000, int(m.group(1))))
                genre = self._pending_genre
                self._pending_genre = None
                return self._start_playlist(genre, count)
            self._pending_genre = None
            return "Ok, cancelei a playlist."

        # ── Nova intenção de playlist ─────────────────────────
        intent = detect_playlist_intent(text)
        if intent is None:
            return None

        genre = intent["genre"]
        count = intent["count"]

        if count is None:
            self._pending_genre = genre
            return f"Quantas músicas quer que eu busque para: {genre}?"

        return self._start_playlist(genre, count)

    def _start_playlist(self, genre: str, count: int) -> str:
        self._stop_flag.set()
        if self._current_thread and self._current_thread.is_alive():
            self._current_thread.join(timeout=2)
        self._stop_flag.clear()
        self._skip_flag.clear()
        self._active = True

        self._current_thread = threading.Thread(
            target=self._run_playlist, args=(genre, count), daemon=True
        )
        self._current_thread.start()
        return f"🎵 Montando playlist de {count} músicas — {genre}... iniciando em breve!"

    def _run_playlist(self, genre: str, count: int):
        print(f"\n[Playlist] ▶ Gerando {count} músicas de '{genre}'...")
        tracks = generate_playlist_with_llm(genre, count)

        if not tracks:
            print("[Playlist] ✗ LLM não retornou músicas.")
            self._active = False
            return

        print(f"[Playlist] ✓ {len(tracks)} músicas. Iniciando reprodução...")

        from voice.tts import get_tts
        tts = get_tts()

        for i, track in enumerate(tracks):
            if self._stop_flag.is_set():
                break

            self._skip_flag.clear()
            pos_label = f"Top {i+1}"
            print(f"\n[Playlist] ▶ {i+1}/{len(tracks)}: {track}")

            # Fala o nome antes de tocar
            tts.speak(f"{pos_label}: {track}", blocking=False)

            if self.spotify.available:
                result = self.spotify.search_and_play(track)
                print(f"[Playlist] → {result}")
                self._wait_for_track_end(max_wait=600)
            else:
                self._play_fallback(track)
                self._wait_for_track_end(max_wait=600)

        print("[Playlist] ✓ Playlist concluída.")
        self._active = False

    def _play_fallback(self, track: str):
        import subprocess, urllib.parse
        query = urllib.parse.quote(track)
        subprocess.Popen(
            ["xdg-open", f"spotify:search:{query}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def _playerctl(self, *args) -> str:
        import subprocess
        try:
            r = subprocess.run(
                ["playerctl", "--player=spotify"] + list(args),
                capture_output=True, text=True, timeout=3
            )
            return r.stdout.strip()
        except Exception:
            return ""

    def _wait_for_track_end(self, max_wait: int):
        """
        Espera a faixa atual terminar usando playerctl (posição + duração).
        Funciona com ou sem API. Sai se: faixa termina, skip_flag, stop_flag.
        """
        # Aguarda o Spotify começar a tocar (até 10s)
        for _ in range(10):
            if self._stop_flag.is_set() or self._skip_flag.is_set():
                return
            if self._playerctl("status") == "Playing":
                break
            time.sleep(1)

        initial_trackid = self._playerctl("metadata", "mpris:trackid")

        waited = 0
        while waited < max_wait and not self._stop_flag.is_set():
            if self._skip_flag.is_set():
                return

            time.sleep(2)
            waited += 2

            status = self._playerctl("status")
            if status in ("Stopped", ""):
                return

            current_trackid = self._playerctl("metadata", "mpris:trackid")
            if initial_trackid and current_trackid and current_trackid != initial_trackid:
                return

            try:
                length_us = int(self._playerctl("metadata", "mpris:length"))
                position_s = float(self._playerctl("position"))
                length_s = length_us / 1_000_000
                remaining = length_s - position_s
                if length_s > 0 and remaining <= 3:
                    time.sleep(max(0, remaining))
                    return
            except (ValueError, TypeError):
                pass

    def stop(self) -> str:
        self._stop_flag.set()
        self._active = False
        self._pending_genre = None
        return "⏹ Playlist interrompida."


# Singleton
_instance: Optional[PlaylistBuilder] = None


def get_playlist_builder() -> PlaylistBuilder:
    global _instance
    if _instance is None:
        _instance = PlaylistBuilder()
    return _instance
