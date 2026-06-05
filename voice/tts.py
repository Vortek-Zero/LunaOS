#!/usr/bin/env python3
"""
voice/tts.py — Text-to-Speech corrigido
Fix: asyncio em thread, fila de fala, fallback silencioso
"""
import asyncio
import threading
import queue
import os
import time
import re
from pathlib import Path
from typing import Optional

# Imports opcionais (podem não estar instalados ainda)
try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

try:
    import sounddevice as sd
    import soundfile as sf
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

import sys
sys.path.append(str(Path(__file__).parent.parent))
try:
    import config
    from config import VOICE_CONFIG, USE_LOCAL_XTTS, XTTS_SPEAKER_WAV
except ImportError:
    import types
    config = types.SimpleNamespace()
    config.USE_LOCAL_F5 = False
    config.F5_REF_AUDIO = ""
    VOICE_CONFIG = {
        "voice": "pt-BR-ThalitaMultilingualNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "volume": "+5%",
    }
    USE_LOCAL_XTTS = False
    XTTS_SPEAKER_WAV = ""

# Engine de voz inteligente (Yara)
try:
    from voice.voice_engine import get_voice_engine, VoiceEngine
    HAS_VOICE_ENGINE = True
except ImportError:
    try:
        from voice_engine import get_voice_engine, VoiceEngine
        HAS_VOICE_ENGINE = True
    except ImportError:
        HAS_VOICE_ENGINE = False

# Importa o Kokoro se disponível
try:
    from kokoro_onnx import Kokoro
    HAS_KOKORO = True
except ImportError:
    HAS_KOKORO = False


TEMP_DIR = Path(__file__).parent.parent / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
TTS_TEMP_FILE = str(TEMP_DIR / "luna_tts.mp3")


class TTSEngine:
    """
    Motor TTS com:
    - asyncio correto (novo event loop por thread)
    - fila para evitar sobreposição
    - fallback silencioso se libs ausentes
    """

    def __init__(self):
        self.enabled = True
        self.voice = VOICE_CONFIG["voice"]
        self.rate = VOICE_CONFIG["rate"]
        self.pitch = VOICE_CONFIG["pitch"]
        self.volume = VOICE_CONFIG["volume"]
        self._speaking = False
        self._lock = threading.Lock()

        if not HAS_EDGE_TTS:
            print("[TTS] ⚠ edge-tts não instalado. Voz desabilitada.")
        if not HAS_AUDIO:
            print("[TTS] ⚠ sounddevice/soundfile não instalados. Áudio desabilitado.")
            
        self.kokoro = None
        if USE_LOCAL_XTTS and HAS_KOKORO:
            try:
                print("[TTS] Carregando modelo local AI (Kokoro v1.0)...")
                # Carrega o modelo apenas uma vez
                model_path = str(Path(__file__).parent / "models" / "kokoro-v1.0.onnx")
                voices_path = str(Path(__file__).parent / "models" / "voices-v1.0.bin")
                if os.path.exists(model_path) and os.path.exists(voices_path):
                    self.kokoro = Kokoro(model_path, voices_path)
                    print("[TTS] ✓ Modelo local AI carregado com sucesso!")
                else:
                    print(f"[TTS] ⚠ Modelos Kokoro não encontrados na pasta voice/models/. Usando Edge TTS.")
            except Exception as e:
                print(f"[TTS] ⚠ Erro ao carregar Kokoro: {e}")

        # Nova verificação para F5-TTS
        if getattr(config, "USE_LOCAL_F5", False):
            try:
                from voice.f5_tts_engine import F5TTSEngine
                print(f"[TTS] Carregando motor de clonagem de voz Zero-Shot F5-TTS...")
                ref_audio = getattr(config, "F5_REF_AUDIO", "")
                self.f5_engine = F5TTSEngine(ref_audio)
            except Exception as e:
                print(f"[TTS] ⚠ Erro ao carregar F5-TTS: {e}")

    def speak(self, text: str, blocking: bool = False) -> None:
        """
        Fala o texto. Por padrão, não bloqueia (thread separada).
        Se blocking=True, espera terminar.
        """
        if not self.enabled or not text or not text.strip():
            return
        if not HAS_EDGE_TTS or not HAS_AUDIO:
            return

        if blocking:
            self._speak_sync(text)
        else:
            t = threading.Thread(target=self._speak_sync, args=(text,), daemon=True)
            t.start()

    def _speak_sync(self, text: str) -> None:
        """Executa TTS de forma síncrona com event loop próprio."""
        with self._lock:
            self._speaking = True
            try:
                # Processa texto via VoiceEngine (Yara)
                if HAS_VOICE_ENGINE:
                    engine = get_voice_engine()
                    segments, params = engine.process(text, base_volume=self.volume)
                    final_text = engine.segments_to_text(segments)
                    rate  = params.rate
                    pitch = params.pitch
                else:
                    final_text = self._clean_text(text)
                    rate  = self.rate
                    pitch = self.pitch

                if not final_text:
                    return

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._generate_audio(final_text, rate, pitch))
                finally:
                    loop.close()

                if os.path.exists(TTS_TEMP_FILE):
                    data, samplerate = sf.read(TTS_TEMP_FILE)
                    # Pós-processamento de áudio (EQ + normalização LUFS)
                    if HAS_VOICE_ENGINE:
                        data, samplerate = VoiceEngine.postprocess_audio(data, samplerate)
                    try:
                        sd.play(data, samplerate)
                        sd.wait()
                    except Exception as e:
                        print(f"[TTS] ⚠ Falha no dispositivo de áudio: {e}")
                    try:
                        os.remove(TTS_TEMP_FILE)
                    except Exception:
                        pass

            except Exception as e:
                print(f"[TTS] Erro ao falar: {e}")
            finally:
                self._speaking = False

    async def _generate_audio(self, text: str, rate: str = None, pitch: str = None) -> None:
        """Gera o arquivo de áudio tentando os motores na ordem da prioridade configurada."""
        priority = getattr(config, "TTS_PRIORITY", ["google_cloud", "f5", "edge_tts", "elevenlabs", "azure", "pyttsx3"])
        
        for engine_name in priority:
            engine_name = engine_name.strip().lower()
            success = False
            
            if engine_name == "google_cloud":
                success = await self._play_google_cloud(text)
            elif engine_name == "f5":
                success = await self._play_f5(text)
            elif engine_name == "edge_tts":
                success = await self._play_edge_tts(text, rate, pitch)
            elif engine_name == "elevenlabs":
                success = await self._play_elevenlabs(text)
            elif engine_name == "azure":
                success = await self._play_azure(text)
            elif engine_name == "pyttsx3":
                success = await self._play_pyttsx3(text)
                
            if success and os.path.exists(TTS_TEMP_FILE) and os.path.getsize(TTS_TEMP_FILE) > 0:
                print(f"[TTS] ✓ Áudio gerado com sucesso usando o motor: {engine_name}")
                return
                
        print("[TTS] ❌ Falha crítica: Nenhum motor de voz conseguiu gerar o áudio.")

    async def _play_google_cloud(self, text: str) -> bool:
        try:
            from google.cloud import texttospeech
            creds = None
            try:
                from actions.google_services import get_google
                g = get_google()
                if g and g.available:
                    creds = g.creds
            except Exception:
                pass
            
            if creds:
                client = texttospeech.TextToSpeechClient(credentials=creds)
            else:
                client = texttospeech.TextToSpeechClient()
                
            input_text = texttospeech.SynthesisInput(text=text)
            voice_name = getattr(config, "GOOGLE_CLOUD_TTS_VOICE", "pt-BR-Neural2-A")
            voice = texttospeech.VoiceSelectionParams(
                language_code="pt-BR",
                name=voice_name
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )
            
            response = client.synthesize_speech(
                input=input_text, voice=voice, audio_config=audio_config
            )
            
            with open(TTS_TEMP_FILE, "wb") as out:
                out.write(response.audio_content)
            return True
        except Exception as e:
            # Silencioso se não configurado
            return False

    async def _play_f5(self, text: str) -> bool:
        if hasattr(self, 'f5_engine') and self.f5_engine is not None:
            try:
                self.f5_engine.generate_to_file(text, TTS_TEMP_FILE)
                return True
            except Exception as e:
                print(f"[TTS] ⚠ Erro no F5-TTS: {e}")
        return False

    async def _play_edge_tts(self, text: str, rate: str = None, pitch: str = None) -> bool:
        if not HAS_EDGE_TTS:
            return False
        try:
            rate = rate or self.rate
            pitch = pitch or self.pitch
            communicate = edge_tts.Communicate(
                text,
                self.voice,
                rate=rate,
                pitch=pitch,
                volume=self.volume,
            )
            await communicate.save(TTS_TEMP_FILE)
            return True
        except Exception as e:
            print(f"[TTS] ⚠ Erro no Edge TTS: {e}")
            return False

    async def _play_elevenlabs(self, text: str) -> bool:
        api_key = getattr(config, "ELEVENLABS_API_KEY", "")
        if not api_key:
            return False
        try:
            import requests
            voice_id = getattr(config, "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": api_key
            }
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
            resp = requests.post(url, json=data, headers=headers, timeout=10)
            if resp.status_code == 200:
                with open(TTS_TEMP_FILE, "wb") as f:
                    f.write(resp.content)
                return True
            else:
                print(f"[TTS] ⚠ ElevenLabs respondeu {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            print(f"[TTS] ⚠ Erro no ElevenLabs: {e}")
            return False

    async def _play_azure(self, text: str) -> bool:
        key = getattr(config, "AZURE_SPEECH_KEY", "")
        region = getattr(config, "AZURE_SPEECH_REGION", "eastus")
        if not key:
            return False
        try:
            import requests
            url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
            headers = {
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
                "User-Agent": "LunaTTS"
            }
            voice = getattr(config, "AZURE_SPEECH_VOICE", "pt-BR-ThalitaNeural")
            ssml = f"""<speak version='1.0' xml:lang='pt-BR'>
                <voice xml:lang='pt-BR' name='{voice}'>
                    {text}
                </voice>
            </speak>"""
            resp = requests.post(url, data=ssml.encode('utf-8'), headers=headers, timeout=10)
            if resp.status_code == 200:
                with open(TTS_TEMP_FILE, "wb") as f:
                    f.write(resp.content)
                return True
            else:
                print(f"[TTS] ⚠ Azure TTS respondeu {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            print(f"[TTS] ⚠ Erro no Azure: {e}")
            return False

    async def _play_pyttsx3(self, text: str) -> bool:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            for voice in voices:
                if 'pt' in voice.languages or 'brazil' in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    break
            
            wav_file = str(TEMP_DIR / "luna_pyttsx3.wav")
            engine.save_to_file(text, wav_file)
            engine.runAndWait()
            
            if os.path.exists(wav_file):
                if os.path.exists(TTS_TEMP_FILE):
                    try:
                        os.remove(TTS_TEMP_FILE)
                    except Exception:
                        pass
                os.rename(wav_file, TTS_TEMP_FILE)
                return True
            return False
        except Exception as e:
            print(f"[TTS] ⚠ Erro no pyttsx3: {e}")
            return False

    def _clean_text(self, text: str) -> str:
        """Remove markdown e símbolos antes de falar."""
        import re
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'`(.*?)`', r'\1', text)
        text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        # Remove emojis problemáticos para TTS
        text = re.sub(r'[🧠🎤✓⚠️🌹⏱️⚡🔔👁️🌐→←↑↓]', '', text)
        return text.strip()

    def is_speaking(self) -> bool:
        return self._speaking

    def stop(self) -> None:
        """Interrompe fala em andamento."""
        self._stop_requested = True
        try:
            import sounddevice as _sd
            _sd.stop()
        except Exception:
            pass
        self._speaking = False

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled

    def set_voice(self, voice: str) -> None:
        self.voice = voice


# Singleton
_tts_instance: Optional[TTSEngine] = None


def get_tts() -> TTSEngine:
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = TTSEngine()
    return _tts_instance


if __name__ == "__main__":
    tts = get_tts()
    print("Testando TTS...")
    tts.speak("Olá! Sistemas de voz online.", blocking=True)
    print("Teste concluído.")
