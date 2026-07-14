import traceback

from voice.stt import _pcm_to_wav, _record_audio, get_stt

stt = get_stt()
stt._load_model()
try:
    pcm = _record_audio(2.0)
    wav = _pcm_to_wav(pcm)
    print("Transcribing:", wav)
    text = stt._transcribe(wav)
    print("Text:", text)
except Exception:
    traceback.print_exc()
