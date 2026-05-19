import os
import threading
import soundfile as sf
import sounddevice as sd
from pathlib import Path
import re

# Usa f5-tts
try:
    from f5_tts.api import F5TTS
    HAS_F5 = True
except ImportError:
    HAS_F5 = False

TEMP_DIR = Path(__file__).parent.parent / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
TTS_TEMP_FILE = str(TEMP_DIR / "f5_tts.wav")

class F5TTSEngine:
    def __init__(self, ref_audio_path: str):
        self.ref_audio_path = ref_audio_path
        self.ref_text = "" # Auto-transcribe via Whisper
        self._speaking = False
        self._lock = threading.Lock()
        
        if HAS_F5:
            print("[F5-TTS] Carregando motor de clonagem de voz (isso pode demorar na primeira vez)...")
            # Carrega o modelo na memória (Device auto-selecionado)
            self.model = F5TTS()
            print("[F5-TTS] ✓ Motor carregado!")
        else:
            self.model = None

    def speak(self, text: str, blocking: bool = False):
        if not self.model or not text.strip():
            return
            
        text = self._clean_text(text)
        if not text:
            return

        if blocking:
            self._speak_sync(text)
        else:
            t = threading.Thread(target=self._speak_sync, args=(text,), daemon=True)
            t.start()

    def _speak_sync(self, text: str):
        with self._lock:
            self._speaking = True
            try:
                print("[F5-TTS] Sintetizando voz clonada...")
                wav, sr, spect = self.model.infer(
                    ref_file=self.ref_audio_path,
                    ref_text=self.ref_text,
                    gen_text=text
                )
                
                sf.write(TTS_TEMP_FILE, wav, sr)
                
                # Play
                data, samplerate = sf.read(TTS_TEMP_FILE)
                sd.play(data, samplerate)
                sd.wait()
                
            except Exception as e:
                print(f"[F5-TTS] Erro: {e}")
            finally:
                self._speaking = False

    def _clean_text(self, text: str) -> str:
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
        return text.strip()

    def is_speaking(self) -> bool:
        return self._speaking

    def generate_to_file(self, text: str, filepath: str):
        if not self.model or not text.strip():
            return
            
        text = self._clean_text(text)
        if not text:
            return

        print("[F5-TTS] Sintetizando voz clonada...")
        wav, sr, spect = self.model.infer(
            ref_file=self.ref_audio_path,
            ref_text=self.ref_text,
            gen_text=text
        )
        sf.write(filepath, wav, sr)
