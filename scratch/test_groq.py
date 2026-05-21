import os
import sys
from groq import Groq

# Load .env
from pathlib import Path
BASE_DIR = Path(__file__).parent.parent
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

api_key = os.getenv("GROQ_API_KEY")
print("API Key:", api_key[:12] + "..." if api_key else "None")

try:
    client = Groq(api_key=api_key)
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": "Diga 'Olá da LUNA!'",
            }
        ],
        model="llama-3.1-8b-instant",
    )
    print("Response:", chat_completion.choices[0].message.content)
except Exception as e:
    print("Error:", e)
