import os
import requests

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

headers = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
}

for model in ["google/gemini-2.5-flash", "google/gemini-1.5-flash", "google/gemini-2.0-flash-001"]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 10
    }
    resp = requests.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=10)
    print(f"{model}: {resp.status_code}")
