import traceback

from voice.stt import _pcm_to_wav, _record_until_silence, get_stt

stt = get_stt()
try:
    pcm = _record_until_silence(2.0)
    wav = _pcm_to_wav(pcm)
    print("Transcribing:", wav)
    text = stt._transcribe(wav)
    print("Text:", text)
except Exception:
    traceback.print_exc()
