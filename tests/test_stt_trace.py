import sys
import os
import traceback
from voice.stt import get_stt, _record_audio, _pcm_to_wav

stt = get_stt()
stt._load_model()
try:
    pcm = _record_audio(2.0)
    wav = _pcm_to_wav(pcm)
    print("Transcribing:", wav)
    text = stt._transcribe(wav)
    print("Text:", text)
except Exception as e:
    traceback.print_exc()
