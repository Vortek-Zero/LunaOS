#!/usr/bin/env python3
"""
voice/tts.py — Text-to-Speech corrigido
Fix: asyncio em thread, fila de fala, fallback silencioso
"""
import asyncio
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
import os
import time
import re
from pathlib import Path
from typing import Optional

from error_codes import err

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
        self._stop_requested = False
        self._thread_pool = ThreadPoolExecutor(max_workers=1)

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
                print(err("TTS_KOKORO_FAILED", str(e)))

        # Nova verificação para F5-TTS
        if getattr(config, "USE_LOCAL_F5", False):
            try:
                from voice.f5_tts_engine import F5TTSEngine
                print(f"[TTS] Carregando motor de clonagem de voz Zero-Shot F5-TTS...")
                ref_audio = getattr(config, "F5_REF_AUDIO", "")
                self.f5_engine = F5TTSEngine(ref_audio)
            except Exception as e:
                print(err("TTS_F5_FAILED", str(e)))

    def speak(self, text: str, blocking: bool = False, barge_in_callback=None) -> None:
        """
        Fala o texto. Por padrão, não bloqueia (thread separada).
        Se blocking=True, espera terminar.
        barge_in_callback(texto) é chamado se o usuário interromper a fala.
        """
        if not self.enabled or not text or not text.strip():
            return
        if not HAS_EDGE_TTS or not HAS_AUDIO:
            return

        if blocking:
            self._speak_sync(text, barge_in_callback)
        else:
            self._thread_pool.submit(self._speak_sync, text, barge_in_callback)

    def _chunk_text(self, text: str, max_chars: int = 1500) -> list[str]:
        """Divide texto longo em chunks por quebra de frase."""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks, current = [], ""
        for s in sentences:
            if len(current) + len(s) > max_chars and current:
                chunks.append(current.strip())
                current = s
            else:
                current += " " + s if current else s
        if current.strip():
            chunks.append(current.strip())
        return chunks if len(chunks) > 1 else [text]

    def _process_text(self, text: str):
        """Processa texto pelo VoiceEngine (Yara) e retorna (final_text, rate, pitch)."""
        if HAS_VOICE_ENGINE:
            engine = get_voice_engine()
            segments, params = engine.process(text, base_volume=self.volume)
            final_text = engine.segments_to_text(segments)
            return final_text, params.rate, params.pitch
        return self._clean_text(text), self.rate, self.pitch

    def _generate_chunk_audio(self, text: str):
        """Gera áudio para um chunk e retorna (data, samplerate) ou (None, None)."""
        if not text or not text.strip():
            return None, None
        final_text, rate, pitch = self._process_text(text)
        if not final_text:
            return None, None

        out_path = f"/tmp/luna_tts_{os.getpid()}_{id(text)}.wav"
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._generate_audio(final_text, rate, pitch, out_path))
            finally:
                loop.close()

            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                data, sr = sf.read(out_path)
                if HAS_VOICE_ENGINE:
                    data, sr = VoiceEngine.postprocess_audio(data, sr)
                return data, sr
        except Exception as e:
            print(err("TTS_CHUNK_FAILED", str(e)))
        finally:
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except Exception:
                pass
        return None, None

    def _barge_in_monitor(self, barge_in_callback) -> None:
        """Monitora microfone durante TTS. Se detectar fala, interrompe e captura o comando."""
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16, channels=1,
                rate=16000, input=True,
                frames_per_buffer=1024,
            )
            speech_count = 0
            energy_threshold = 300
            while self._speaking and not self._stop_requested:
                try:
                    data = stream.read(1024, exception_on_overflow=False)
                    shorts = struct.unpack(f"{len(data)//2}h", data)
                    rms = math.sqrt(sum(s*s for s in shorts) / len(shorts)) if shorts else 0
                    if rms > energy_threshold:
                        speech_count += 1
                        if speech_count >= 4:  # ~256ms de fala sustentada = interrupção
                            self.stop()
                            from voice.stt import _record_until_silence, _pcm_to_wav, _transcribe_groq
                            pcm = _record_until_silence(max_seconds=15, silence_threshold=300)
                            if pcm:
                                wav = _pcm_to_wav(pcm)
                                text = _transcribe_groq(wav)
                                if text:
                                    print(f"[BARGE-IN] Usuário interrompeu: '{text}'")
                                    barge_in_callback(text)
                            break
                    else:
                        speech_count = 0
                except Exception:
                    break
                time.sleep(0.008)
            stream.close()
            pa.terminate()
        except Exception as e:
            print(err("TTS_BARGE_IN_FAILED", str(e)))

    def _speak_sync(self, text: str, barge_in_callback=None) -> None:
        """Executa TTS com pré-processamento: gera próximo chunk enquanto o atual toca."""
        with self._lock:
            self._stop_requested = False
            self._speaking = True
            from concurrent.futures import Future
            try:
                chunks = self._chunk_text(text)
                if not chunks:
                    return

                # Gera o primeiro chunk (bloqueante)
                data, sr = self._generate_chunk_audio(chunks[0])

                # Inicia monitor de interrupção se houver callback
                if barge_in_callback:
                    threading.Thread(
                        target=self._barge_in_monitor,
                        args=(barge_in_callback,),
                        daemon=True,
                    ).start()

                for i in range(len(chunks)):
                    if getattr(self, '_stop_requested', False):
                        break

                    # Pré-processa próximo chunk em background
                    prefetch: Future | None = None
                    if i + 1 < len(chunks):
                        prefetch = self._thread_pool.submit(self._generate_chunk_audio, chunks[i + 1])

                    # Toca o chunk atual (polling loop para respeitar stop_requested)
                    if data is not None:
                        try:
                            sd.play(data, sr)
                            while sd.get_stream().active and not self._stop_requested:
                                time.sleep(0.05)
                            if self._stop_requested:
                                sd.stop()
                        except Exception as e:
                            print(err("TTS_PLAYBACK_FAILED", str(e)))

                    if getattr(self, '_stop_requested', False):
                        break

                    # Pega o resultado do pré-processamento (já deve estar pronto)
                    if prefetch is not None:
                        try:
                            data, sr = prefetch.result()
                        except Exception as e:
                            print(err("TTS_PREFETCH_FAILED", str(e)))
                            data, sr = None, None
                    else:
                        data, sr = None, None

            except Exception as e:
                print(err("TTS_AUDIO_DEVICE_FAILED", f"Falar: {e}"))
            finally:
                self._speaking = False

    async def _generate_audio(self, text: str, rate: str = None, pitch: str = None,
                               output_path: str = None) -> None:
        """Gera o arquivo de áudio tentando os motores na ordem da prioridade configurada."""
        if output_path is None:
            output_path = TTS_TEMP_FILE
        priority = getattr(config, "TTS_PRIORITY", ["edge_tts", "google_cloud", "f5", "elevenlabs", "azure", "pyttsx3"])
        
        for engine_name in priority:
            engine_name = engine_name.strip().lower()
            success = False
            
            if engine_name == "google_cloud":
                success = await self._play_google_cloud(text, output_path)
            elif engine_name == "f5":
                success = await self._play_f5(text, output_path)
            elif engine_name == "edge_tts":
                success = await self._play_edge_tts(text, rate, pitch, output_path)
            elif engine_name == "elevenlabs":
                success = await self._play_elevenlabs(text, output_path)
            elif engine_name == "azure":
                success = await self._play_azure(text, output_path)
            elif engine_name == "pyttsx3":
                success = await self._play_pyttsx3(text, output_path)
                
            if success and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                print(f"[TTS] ✓ Áudio gerado com sucesso usando o motor: {engine_name}")
                return
                
        print(err("TTS_ALL_ENGINES_FAILED", "Nenhum motor de voz conseguiu gerar o áudio."))

    async def _play_google_cloud(self, text: str, output_path: str = None) -> bool:
        if output_path is None:
            output_path = TTS_TEMP_FILE
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
            
            with open(output_path, "wb") as out:
                out.write(response.audio_content)
            return True
        except Exception as e:
            return False

    async def _play_f5(self, text: str, output_path: str = None) -> bool:
        if output_path is None:
            output_path = TTS_TEMP_FILE
        if hasattr(self, 'f5_engine') and self.f5_engine is not None:
            try:
                self.f5_engine.generate_to_file(text, output_path)
                return True
            except Exception as e:
                print(err("TTS_F5_FAILED", str(e)))
        return False

    async def _play_edge_tts(self, text: str, rate: str = None, pitch: str = None,
                              output_path: str = None) -> bool:
        if output_path is None:
            output_path = TTS_TEMP_FILE
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
            await communicate.save(output_path)
            return True
        except Exception as e:
            print(err("TTS_EDGE_FAILED", str(e)))
            return False

    async def _play_elevenlabs(self, text: str, output_path: str = None) -> bool:
        if output_path is None:
            output_path = TTS_TEMP_FILE
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
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                return True
            else:
                print(err("TTS_ELEVENLABS_FAILED", f"HTTP {resp.status_code}: {resp.text[:200]}"))
                return False
        except Exception as e:
            print(err("TTS_ELEVENLABS_FAILED", str(e)))
            return False

    @staticmethod
    def _xml_escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")

    async def _play_azure(self, text: str, output_path: str = None) -> bool:
        if output_path is None:
            output_path = TTS_TEMP_FILE
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
                    {self._xml_escape(text)}
                </voice>
            </speak>"""
            resp = requests.post(url, data=ssml.encode('utf-8'), headers=headers, timeout=10)
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                return True
            else:
                print(err("TTS_AZURE_FAILED", f"HTTP {resp.status_code}: {resp.text[:200]}"))
                return False
        except Exception as e:
            print(err("TTS_AZURE_FAILED", str(e)))
            return False

    async def _play_pyttsx3(self, text: str, output_path: str = None) -> bool:
        if output_path is None:
            output_path = TTS_TEMP_FILE
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            for voice in voices:
                if 'pt' in voice.languages or 'brazil' in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    break
            
            wav_file = str(TEMP_DIR / f"luna_pyttsx3_{os.getpid()}.wav")
            engine.save_to_file(text, wav_file)
            engine.runAndWait()
            
            if os.path.exists(wav_file):
                import shutil
                shutil.move(wav_file, output_path)
                return True
            return False
        except Exception as e:
            print(err("TTS_PYTTSX3_FAILED", str(e)))
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
