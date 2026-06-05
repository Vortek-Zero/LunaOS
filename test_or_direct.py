import os
import requests
from brain.agent_tools import LUNA_TOOLS

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

headers = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://luna-ai.local",
    "X-Title": "Luna AI",
}
payload = {
    "model": "google/gemini-2.5-flash-preview-05-20",
    "messages": [{"role": "user", "content": "hello"}],
    "temperature": 0.7,
    "max_tokens": 1500,
    "top_p": 0.95,
    "tools": LUNA_TOOLS,
    "tool_choice": "auto"
}

resp = requests.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=60)
print(f"Status: {resp.status_code}")
print(f"Text: {resp.text}")
