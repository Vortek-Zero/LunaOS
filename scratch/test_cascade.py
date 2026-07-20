import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from brain.llm import get_llm

llm = get_llm()
print("Provedores configurados e seu status:")
for p in llm.get_providers_status():
    print(
        f"- {p['name']}: active={p['active']}, available={p['available']}, models={p.get('models') or p.get('model')}"
    )

print("\nTestando gerações individuais:")
providers = [
    "mistral",
    "gemini",
    "openrouter",
    "completions",
    "chutes",
    "github",
    "naga",
    "bestai",
    "groq",
    "freetheai",
    "puter",
]

for provider in providers:
    try:
        print(f"Testando {provider}...")
        res = llm.generate(prompt="Olá, responda apenas OK.", model=f"{provider}/")
        print(f"-> Resposta de {provider}: {res}")
    except Exception as e:
        print(f"-> Erro no teste de {provider}: {e}")
