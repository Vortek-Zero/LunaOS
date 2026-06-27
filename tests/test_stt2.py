import wave
import uuid
import sys
from faster_whisper import WhisperModel

pcm = b'\x00\x00' * 16000 * 2  # 2 seconds of silence
sample_rate = 16000

path = f"/tmp/luna_stt_{uuid.uuid4().hex}.wav"
with wave.open(path, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sample_rate)
    wf.writeframes(pcm)

try:
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        path,
        language="pt",
        beam_size=1,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    text = " ".join(s.text for s in segments).strip()
    print("Transcribed:", text)
except Exception as e:
    import traceback
    traceback.print_exc()
    print("Error type:", type(e))
    print(f"[STT] Erro Whisper: {e}")
