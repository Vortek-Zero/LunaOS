import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import PUTER_BASE_URL, PUTER_MODEL, PUTER_SPEED, PUTER_TOKEN, PUTER_VOICE

print(f"Puter Token: {PUTER_TOKEN[:10]}...{PUTER_TOKEN[-10:] if PUTER_TOKEN else ''}")
print(f"Voice: {PUTER_VOICE}, Model: {PUTER_MODEL}, Base URL: {PUTER_BASE_URL}")

payload = json.dumps(
    {
        "interface": "puter-tts",
        "method": "synthesize",
        "args": {
            "text": "Olá, isto é um teste da voz da Luna.",
            "model": PUTER_MODEL,
            "voice": PUTER_VOICE,
            "speed": PUTER_SPEED,
        },
    }
).encode()

req = Request(
    f"{PUTER_BASE_URL}/drivers/call",
    data=payload,
    headers={"Authorization": f"Bearer {PUTER_TOKEN}", "Content-Type": "application/json"},
)

try:
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
        print("Resposta recebida com sucesso:")
        print("Chaves no resultado:", data.get("result", {}).keys() if "result" in data else data.keys())
        audio_b64 = data.get("result", {}).get("audio", "") or data.get("audio", "")
        if audio_b64:
            print("Audio b64 obtido (tamanho):", len(audio_b64))
        else:
            print("Nenhum áudio encontrado na resposta:", data)
except Exception as e:
    print("Erro ao chamar Puter TTS:", e)
    if hasattr(e, "read"):
        print("Corpo do erro:", e.read().decode())
