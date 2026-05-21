#!/usr/bin/env python3
import os
os.environ['PYTHONWARNINGS'] = 'ignore'

# Suprime spam do ALSA
from ctypes import cdll, c_char_p, c_int, CFUNCTYPE, cast
try:
    _h = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
    cdll.LoadLibrary('libasound.so.2').snd_lib_error_set_handler(cast(None, _h))
except OSError:
    pass

import speech_recognition as sr
import tinytuya

DEVICE_ID = "eb64a81b56fb8003dexqdd"
LOCAL_KEY  = "Ek&~Ah`=4s}5.'Z#"
IP_DEVICE  = "192.168.1.5"
MIC_INDEX  = 9

device = tinytuya.OutletDevice(
    dev_id=DEVICE_ID, address=IP_DEVICE, local_key=LOCAL_KEY, version=3.4
)
light_on = False

def set_light(state: bool):
    global light_on
    light_on = state
    try:
        device.set_status(state)
        print("💡 Luz", "LIGADA" if state else "DESLIGADA")
    except Exception as e:
        print(f"⚠️  Erro: {e}")

if __name__ == "__main__":
    r = sr.Recognizer()
    mic = sr.Microphone(device_index=MIC_INDEX)

    with mic as source:
        r.adjust_for_ambient_noise(source, duration=1)

    print("🎙️  Aguardando comandos... (ex: 'Luna, ligar luz da sala')")

    while True:
        with mic as source:
            try:
                audio = r.listen(source, timeout=5, phrase_time_limit=5)
                text = r.recognize_google(audio, language="pt-BR").lower()
                print(f"   ouvi: {text}")

                if "luna" not in text:
                    continue

                if "desligar" in text and "sala" in text:
                    set_light(False)
                elif "ligar" in text and "sala" in text:
                    set_light(True)

            except (sr.WaitTimeoutError, sr.UnknownValueError):
                pass
            except sr.RequestError as e:
                print(f"   erro: {e}")
