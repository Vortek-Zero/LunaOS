#!/usr/bin/env python3
"""
voice/stt.py — STT híbrido:
  Wakeword: energy gate local (zero latência) + Groq Whisper para transcrição
  Comando:  Groq Whisper Large v3 (200ms latência, perfeito em PT-BR)
  Fallback: faster-whisper local (se sem API key)
"""
import threading
import time
import os
import sys
import struct
import math
import subprocess
import uuid
import wave
from pathlib import Path
from typing import Optional

os.environ["LC_ALL"] = "C.UTF-8"
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

# ── Dependências ───────────────────────────────────────────────
try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False
    print("[STT] ⚠ pyaudio não instalado.")

try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False

try:
    from groq import Groq as GroqClient
    HAS_GROQ_LIB = True
except ImportError:
    HAS_GROQ_LIB = False

# ── Constantes ─────────────────────────────────────────────────
LANGUAGE    = "pt"
MODEL_SIZE  = "base"   # usado apenas no fallback local
SAMPLE_RATE = 16000
CHUNK       = 1024

_VOICE_DIR      = Path(__file__).parent
_ACTIVATE_SOUND = Path(__file__).parent.parent / "sounds" / "Beepvisual.mp3"

WAKEWORD = "luna"   # único — sem variações, Groq vai acertar


def _load_env():
    """Lê .env e retorna dict."""
    env_file = Path(__file__).parent.parent / ".env"
    env = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


_ENV = _load_env()
GROQ_API_KEY = _ENV.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "")
HAS_GROQ = HAS_GROQ_LIB and bool(GROQ_API_KEY)


# ── PyAudio singleton ──────────────────────────────────────────
_pa_instance = None

def _get_pa():
    global _pa_instance
    if not HAS_PYAUDIO:
        return None
    if _pa_instance is None:
        _pa_instance = pyaudio.PyAudio()
    return _pa_instance


# ── Utilidades de áudio ────────────────────────────────────────
def _play_activation_sound() -> None:
    if not _ACTIVATE_SOUND.exists():
        print("\a", end="", flush=True)
        return
    for player, args in [
        ("mpg123", ["-q", str(_ACTIVATE_SOUND)]),
        ("paplay", [str(_ACTIVATE_SOUND)]),
    ]:
        try:
            subprocess.Popen([player] + args,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            continue
    print("\a", end="", flush=True)


def _pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> str:
    """Salva PCM16 como WAV em /tmp e retorna o path."""
    path = f"/tmp/luna_stt_{uuid.uuid4().hex}.wav"
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return path


def _record_until_silence(
    max_seconds: float = 12,
    silence_threshold: int = 500,
    silence_duration: float = 0.8,
) -> Optional[bytes]:
    """Grava até silêncio ou max_seconds. Retorna PCM16 ou None."""
    pa = _get_pa()
    if not pa:
        return None
    try:
        stream = pa.open(
            format=pyaudio.paInt16, channels=1,
            rate=SAMPLE_RATE, input=True,
            frames_per_buffer=CHUNK,
        )
        frames = []
        silent_chunks = 0
        silent_limit = int(SAMPLE_RATE / CHUNK * silence_duration)
        max_chunks   = int(SAMPLE_RATE / CHUNK * max_seconds)
        started = False

        for _ in range(max_chunks):
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)
            shorts = struct.unpack(f"{len(data)//2}h", data)
            rms = math.sqrt(sum(s*s for s in shorts) / len(shorts)) if shorts else 0
            if rms > silence_threshold:
                started = True
                silent_chunks = 0
            elif started:
                silent_chunks += 1
                if silent_chunks >= silent_limit:
                    break

        stream.stop_stream()
        stream.close()
        return b"".join(frames) if started else None
    except Exception as e:
        print(f"[STT] Erro ao gravar: {e}")
        return None


# ══════════════════════════════════════════════════════════════
#  TRANSCRIÇÃO
# ══════════════════════════════════════════════════════════════

def _transcribe_groq(wav_path: str) -> str:
    """Transcreve com Groq Whisper Large v3 (~200ms)."""
    try:
        client = GroqClient(api_key=GROQ_API_KEY)
        with open(wav_path, "rb") as f:
            result = client.audio.transcriptions.create(
                file=(wav_path, f.read()),
                model="whisper-large-v3-turbo",
                language=LANGUAGE,
                response_format="text",
            )
        return str(result).strip()
    except Exception as e:
        print(f"[STT] Erro Groq: {e}")
        return ""
    finally:
        try:
            os.unlink(wav_path)
        except Exception:
            pass


def _transcribe_local(model, wav_path: str) -> str:
    """Fallback: transcreve com faster-whisper local."""
    try:
        segments, _ = model.transcribe(
            wav_path,
            language=LANGUAGE,
            beam_size=1,
            vad_filter=False,
        )
        return " ".join(s.text for s in segments).strip()
    except Exception as e:
        print(f"[STT] Erro Whisper local: {e}")
        return ""
    finally:
        try:
            os.unlink(wav_path)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
#  STT ENGINE
# ══════════════════════════════════════════════════════════════

class STTEngine:
    """
    Motor STT:
    - Wakeword: energy gate local + transcrição (Groq ou Whisper)
    - Comando:  Groq Whisper Large v3 (preferencial) ou Whisper local
    """

    def __init__(self):
        self.enabled = False
        self._local_model = None
        self._wake_event  = threading.Event()
        self._stop_bg     = threading.Event()
        self._lock        = threading.Lock()
        self._bg_thread: Optional[threading.Thread] = None

        if HAS_GROQ:
            print("[STT] ✓ Groq Whisper Large v3 ativo (online).")
        else:
            if not HAS_GROQ_LIB:
                print("[STT] ⚠ groq não instalado — usando Whisper local.")
            elif not GROQ_API_KEY:
                print("[STT] ⚠ GROQ_API_KEY não definida no .env — usando Whisper local.")
            if HAS_WHISPER and HAS_PYAUDIO:
                self._load_local_model()

    def _load_local_model(self):
        try:
            print(f"[STT] Carregando Whisper '{MODEL_SIZE}' (fallback)...")
            self._local_model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
            print(f"[STT] ✓ Whisper '{MODEL_SIZE}' carregado.")
        except Exception as e:
            print(f"[STT] ⚠ Erro ao carregar Whisper: {e}")
            self._local_model = None

    def _transcribe(self, wav_path: str) -> str:
        """Usa Groq se disponível, senão Whisper local."""
        if HAS_GROQ:
            return _transcribe_groq(wav_path)
        elif self._local_model:
            return _transcribe_local(self._local_model, wav_path)
        return ""

    # ── Wakeword loop (energy gate + transcrição) ──────────────

    def _wakeword_loop(self) -> None:
        """Detecta fala por energia e transcreve só quando necessário."""
        pa = _get_pa()
        if not pa:
            return

        ENERGY_THRESHOLD = 400  # RMS mínimo para considerar fala
        PRE_FRAMES       = 10   # frames de buffer pré-onset
        MAX_CHUNKS       = 80   # máx ~2.5s (80 × 512 / 16000)
        CHUNK_WAKE       = 512

        consecutive_errors = 0
        while not self._stop_bg.is_set():
            try:
                stream = pa.open(
                    format=pyaudio.paInt16, channels=1,
                    rate=SAMPLE_RATE, input=True,
                    frames_per_buffer=CHUNK_WAKE,
                )
                consecutive_errors = 0  # Reset upon success
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors == 1:
                    print(f"[STT] Erro ao abrir stream: {e}")
                
                if consecutive_errors >= 3:
                    print("\n[STT] ⚠ Microfone indisponível ou bloqueado. Desativando o modo de escuta automática (wakeword) para evitar spam de erros.")
                    self.stop_wakeword_listener()
                    break
                    
                time.sleep(2.0)
                continue

            ring_buf     = []
            speech_frames = []
            listening    = False

            try:
                while not self._stop_bg.is_set():
                    data = stream.read(CHUNK_WAKE, exception_on_overflow=False)
                    shorts = struct.unpack(f"{CHUNK_WAKE}h", data)
                    rms    = math.sqrt(sum(s*s for s in shorts) / CHUNK_WAKE)

                    if not listening:
                        ring_buf.append(data)
                        if len(ring_buf) > PRE_FRAMES:
                            ring_buf.pop(0)
                        if rms > ENERGY_THRESHOLD:
                            listening = True
                            speech_frames = list(ring_buf)
                    else:
                        speech_frames.append(data)
                        if rms < ENERGY_THRESHOLD or len(speech_frames) >= MAX_CHUNKS:
                            pcm  = b"".join(speech_frames)
                            wav  = _pcm_to_wav(pcm)
                            text = self._transcribe(wav).lower().strip()
                            if text:
                                print(f"[STT WAKE] ouvido: '{text}'")
                            if WAKEWORD in text:
                                print(f"[STT] 🔔 Wakeword 'Luna' detectado!")
                                stream.stop_stream()
                                stream.close()
                                self.stop_wakeword_listener()
                                self._wake_event.set()
                                return
                            ring_buf      = []
                            speech_frames = []
                            listening     = False
            except Exception as e:
                print(f"[STT] Erro no wakeword loop: {e}")
            finally:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass

    # ── API pública ────────────────────────────────────────────

    def start_wakeword_listener(self) -> None:
        if self._bg_thread and self._bg_thread.is_alive():
            return
        self._stop_bg.clear()
        self._bg_thread = threading.Thread(
            target=self._wakeword_loop, daemon=True
        )
        self._bg_thread.start()
        mode = "Groq" if HAS_GROQ else "Whisper local"
        print(f"[STT] ✓ Wakeword listener ativo ('Luna') — {mode}")

    def stop_wakeword_listener(self) -> None:
        self._stop_bg.set()

    def listen_once(self, timeout: int = 12, phrase_limit: int = 25) -> Optional[str]:
        if not self.enabled:
            return None
        if not HAS_GROQ and not self._local_model:
            return None

        _play_activation_sound()
        time.sleep(0.15)

        with self._lock:
            print("[STT] 🎤 Pode falar...")
            pcm = _record_until_silence(
                max_seconds=float(phrase_limit),
                silence_duration=0.8,
            )
            if not pcm:
                return None
            wav  = _pcm_to_wav(pcm)
            text = self._transcribe(wav)
            if text:
                print(f"[STT] Você: '{text}'")
            return text or None

    @property
    def wake_event(self) -> threading.Event:
        return self._wake_event

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        if self.enabled:
            self.start_wakeword_listener()
        else:
            self.stop_wakeword_listener()
        return self.enabled

    def is_available(self) -> bool:
        if HAS_GROQ and HAS_PYAUDIO:
            return True
        return HAS_WHISPER and HAS_PYAUDIO and self._local_model is not None


# Singleton
_stt_instance: Optional[STTEngine] = None

def get_stt() -> STTEngine:
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = STTEngine()
    return _stt_instance
