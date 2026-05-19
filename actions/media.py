#!/usr/bin/env python3
"""
actions/media.py — Controle de mídia via playerctl + pactl/amixer.
Controla qualquer player MPRIS (Spotify, VLC, navegadores, etc.)
"""
import re
import shutil
import subprocess
from typing import Optional


def _run(cmd: list[str], timeout: int = 3) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except Exception as e:
        return 1, str(e)


class MediaManager:
    def __init__(self):
        self._has_playerctl = bool(shutil.which("playerctl"))
        self._has_pactl = bool(shutil.which("pactl"))
        self._has_amixer = bool(shutil.which("amixer"))
        status = []
        if self._has_playerctl:
            status.append("playerctl")
        if self._has_pactl:
            status.append("pactl")
        elif self._has_amixer:
            status.append("amixer")
        print(f"[Media] Ferramentas: {', '.join(status) or 'nenhuma'}")

    # ── Playerctl ─────────────────────────────────────────────

    def _playerctl(self, *args) -> tuple[bool, str]:
        if not self._has_playerctl:
            return False, "playerctl não instalado. Execute: sudo pacman -S playerctl"
        code, out = _run(["playerctl"] + list(args))
        return code == 0, out

    def play(self) -> str:
        ok, _ = self._playerctl("play")
        return "▶ Reproduzindo." if ok else "Nenhum player ativo para reproduzir."

    def pause(self) -> str:
        ok, _ = self._playerctl("pause")
        return "⏸ Pausado." if ok else "Nenhum player ativo."

    def play_pause(self) -> str:
        ok, _ = self._playerctl("play-pause")
        return "⏯ Play/Pause alternado." if ok else "Nenhum player ativo."

    def next_track(self) -> str:
        ok, _ = self._playerctl("next")
        return "⏭ Próxima faixa." if ok else "Nenhum player ativo."

    def prev_track(self) -> str:
        ok, _ = self._playerctl("previous")
        return "⏮ Faixa anterior." if ok else "Nenhum player ativo."

    def stop(self) -> str:
        ok, _ = self._playerctl("stop")
        return "⏹ Parado." if ok else "Nenhum player ativo."

    def loop_track(self) -> str:
        ok, _ = self._playerctl("loop", "Track")
        return "🔁 Repetição ativada." if ok else "Nenhum player ativo para repetir."

    def seek(self, offset_seconds: int) -> str:
        sign = "+" if offset_seconds >= 0 else "-"
        ok, _ = self._playerctl("position", f"{abs(offset_seconds)}{sign}")
        return "⏩ Posição alterada." if ok else "Não foi possível alterar o tempo."

    def now_playing(self) -> str:
        ok, title = self._playerctl("metadata", "title")
        if not ok or not title:
            return "Nenhuma música tocando no momento."
        _, artist = self._playerctl("metadata", "artist")
        _, status = self._playerctl("status")
        status_icon = {"Playing": "▶", "Paused": "⏸", "Stopped": "⏹"}.get(status, "")
        if artist:
            return f"{status_icon} {artist} — {title}"
        return f"{status_icon} {title}"

    def get_status(self) -> str:
        ok, status = self._playerctl("status")
        if not ok:
            return "Nenhum player ativo."
        return self.now_playing()

    # ── Volume ─────────────────────────────────────────────────

    def set_volume(self, level: int) -> str:
        """Define volume absoluto (0-100)."""
        level = max(0, min(100, level))
        if self._has_pactl:
            code, _ = _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
            return f"🔊 Volume: {level}%" if code == 0 else "Erro ao ajustar volume."
        if self._has_amixer:
            code, _ = _run(["amixer", "-q", "sset", "Master", f"{level}%"])
            return f"🔊 Volume: {level}%" if code == 0 else "Erro ao ajustar volume."
        return "Nenhuma ferramenta de volume disponível (pactl/amixer)."

    def volume_up(self, step: int = 10) -> str:
        if self._has_pactl:
            code, _ = _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{step}%"])
            return f"🔊 Volume aumentado +{step}%." if code == 0 else "Erro."
        if self._has_amixer:
            code, _ = _run(["amixer", "-q", "sset", "Master", f"{step}%+"])
            return f"🔊 Volume aumentado." if code == 0 else "Erro."
        return "Nenhuma ferramenta de volume disponível."

    def volume_down(self, step: int = 10) -> str:
        if self._has_pactl:
            code, _ = _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{step}%"])
            return f"🔉 Volume reduzido -{step}%." if code == 0 else "Erro."
        if self._has_amixer:
            code, _ = _run(["amixer", "-q", "sset", "Master", f"{step}%-"])
            return f"🔉 Volume reduzido." if code == 0 else "Erro."
        return "Nenhuma ferramenta de volume disponível."

    def mute(self) -> str:
        if self._has_pactl:
            code, _ = _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
            return "🔇 Mudo alternado." if code == 0 else "Erro."
        return "pactl não disponível."

    # ── Interface natural ──────────────────────────────────────

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower()

        # Volume com valor específico
        m = re.search(r'volume\s+(?:para\s+)?(\d+)', tl)
        if m:
            return self.set_volume(int(m.group(1)))

        # Volume up/down com step
        m = re.search(r'(?:aumenta|sobe)\s+(?:o\s+)?volume\s+(?:em\s+)?(\d+)', tl)
        if m:
            return self.volume_up(int(m.group(1)))
        m = re.search(r'(?:diminui|baixa|reduz)\s+(?:o\s+)?volume\s+(?:em\s+)?(\d+)', tl)
        if m:
            return self.volume_down(int(m.group(1)))

        if any(w in tl for w in ["aumenta o volume", "sobe o volume", "mais volume"]):
            return self.volume_up()
        if any(w in tl for w in ["diminui o volume", "baixa o volume", "menos volume"]):
            return self.volume_down()
        if any(w in tl for w in ["muta", "mute", "silencia", "sem som"]):
            return self.mute()

        # Playback
        if any(w in tl for w in ["próxima música", "proxima musica", "próxima faixa", "next"]):
            return self.next_track()
        if any(w in tl for w in ["música anterior", "musica anterior", "faixa anterior", "voltar música"]):
            return self.prev_track()
        if any(w in tl for w in ["pausa", "pause", "pausar", "para a música", "para a musica"]):
            return self.pause()
        if any(w in tl for w in ["para tudo", "stop", "parar tudo"]):
            return self.stop()
        if any(w in tl for w in ["toca", "play", "reproduz", "continua", "retoma"]):
            return self.play()

        if any(w in tl for w in ["repetindo", "repete a", "toca de novo", "vezes"]):
            self.loop_track()
            return self.play()

        m_seek = re.search(r'(volta|avanca|avança)\s*(?:a\s+m[uú]sica\s+em\s+|o\s+tempo\s+em\s+|em\s+)?(\d+)\s*(segundo|minuto)', tl)
        if m_seek:
            direction, val, unit = m_seek.groups()
            secs = int(val) * (60 if unit.startswith('minuto') else 1)
            if direction == 'volta':
                secs = -secs
            return self.seek(secs)
        if any(w in tl for w in ["que música", "que musica", "o que está tocando", "qual música",
                                   "qual musica", "música atual", "musica atual"]):
            return self.now_playing()

        return None


# Singleton
_media_instance: Optional[MediaManager] = None

def get_media() -> MediaManager:
    global _media_instance
    if _media_instance is None:
        _media_instance = MediaManager()
    return _media_instance


# ── Rádio ──────────────────────────────────────────────────────

import difflib

_RADIOS: dict[str, str] = {
    "metropolitana":  "https://ice.fabricahost.com.br/metropolitana985sp",
    "jovem pan":      "https://8062.brasilstream.com.br/stream",
    "band":           "https://stm28.xcast.com.br:11364/stream",
    "mix":            "https://stream-29.zeno.fm/na3vpvn10qruv",
    "antena 1":       "https://streamingcwsradio30.com:7093/;",
    "transamérica":   "http://9595.brasilstream.com.br/stream",
    "transamerica":   "http://9595.brasilstream.com.br/stream",
    "cultura":        "https://stream.zeno.fm/clxflencimitv",
    "cbn":            "http://209.126.124.126:8852/stream",
    "globo":          "http://178.33.72.12/globorm64",
}


def _search_radio_url(name: str) -> Optional[str]:
    """Busca URL de stream via radio-browser.info como fallback."""
    try:
        import urllib.parse, urllib.request, json as _json
        encoded = urllib.parse.quote(name)
        url = f"https://de1.api.radio-browser.info/json/stations/search?name={encoded}&countrycode=BR&limit=1"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = _json.loads(r.read())
            if data:
                return data[0].get("url_resolved") or data[0].get("url")
    except Exception:
        pass
    return None


class RadioManager:
    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._has_mpv  = bool(shutil.which("mpv"))
        self._has_cvlc = bool(shutil.which("cvlc"))

    def _player_cmd(self, url: str) -> list[str]:
        if self._has_mpv:
            return ["mpv", "--no-video", "--really-quiet",
                    "--stream-lavf-o=reconnect=1", url]
        if self._has_cvlc:
            return ["cvlc", "--intf", "dummy", "--no-video", url]
        return []

    def _find_radio(self, name: str) -> Optional[tuple[str, str]]:
        name = name.lower().strip()
        if name in _RADIOS:
            return name, _RADIOS[name]
        for key in _RADIOS:
            if name in key or key in name:
                return key, _RADIOS[key]
        matches = difflib.get_close_matches(name, _RADIOS.keys(), n=1, cutoff=0.5)
        if matches:
            return matches[0], _RADIOS[matches[0]]
        # Fallback: busca online via radio-browser.info
        url = _search_radio_url(name)
        if url:
            return name, url
        return None, None

    def play(self, name: str) -> str:
        cmd_base = self._player_cmd("")
        if not cmd_base:
            return "mpv ou cvlc não encontrado. Execute: sudo pacman -S mpv"
        key, url = self._find_radio(name)
        if not url:
            return f"Rádio '{name}' não encontrada. Disponíveis: {', '.join(_RADIOS.keys())}"
        self.stop()
        cmd = self._player_cmd(url)
        self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"📻 Tocando rádio {key.title()}."

    def stop(self) -> str:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc = None
        return "📻 Rádio parada."

    def handle(self, text: str) -> Optional[str]:
        tl = text.lower()
        m = re.search(r'(?:toca|abre|coloca|liga|inicia|sintoniza)\s+(?:a\s+)?r[aá]dio\s+(.+)', tl)
        if m:
            return self.play(m.group(1).strip())
        if re.search(r'(?:para|fecha|desliga|para a)\s+(?:a\s+)?r[aá]dio', tl):
            return self.stop()
        return None


_radio_instance: Optional[RadioManager] = None

def get_radio() -> RadioManager:
    global _radio_instance
    if _radio_instance is None:
        _radio_instance = RadioManager()
    return _radio_instance
