from faster_whisper import WhisperModel
import sys

print("Sys encoding:", sys.getdefaultencoding())
model = WhisperModel("tiny", device="cpu", compute_type="int8")
try:
    # Just run on a dummy file or something
    print("Model loaded")
except Exception as e:
    print(repr(e))
